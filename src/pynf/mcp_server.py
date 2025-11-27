"""
Minimal MCP server for py-nf Nextflow execution.

Run with: pynf-mcp
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from .engine import NextflowEngine
from .tools import run_nfcore_module as _run_nfcore_module
from . import run_module as _run_module


@dataclass
class SavedProcess:
    """A process saved to the workflow session."""
    name: str
    code: str
    module_ref: str | None  # e.g., "nf-core/fastqc"
    saved_at: datetime


@dataclass
class AppContext:
    """Application context with pre-initialized Nextflow engine."""
    engine: NextflowEngine
    saved_processes: dict[str, SavedProcess] = field(default_factory=dict)


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Warm up JVM on startup to avoid cold start latency."""
    # Initialize Nextflow engine (starts JVM, loads classes)
    engine = NextflowEngine()
    yield AppContext(engine=engine)
    # JVM cleanup handled by jpype on process exit


mcp = FastMCP(
    "py-nf",
    instructions="Nextflow workflow execution. JVM is pre-warmed. Use docker_enabled=True for nf-core modules.",
    lifespan=app_lifespan,
)


@mcp.tool()
def run_module(
    script_path: str,
    inputs: list[dict[str, Any]] | None = None,
    params: dict[str, Any] | None = None,
    executor: str = "local",
    docker_enabled: bool = False,
) -> dict[str, Any]:
    """Run a local Nextflow .nf script."""
    docker_config = {"enabled": True} if docker_enabled else None
    result = _run_module(
        script_path,
        inputs=inputs,
        params=params,
        executor=executor,
        docker_config=docker_config,
    )
    return {
        "success": True,
        "output_files": result.get_output_files(),
        "execution_report": result.get_execution_report(),
    }


@mcp.tool()
def run_nfcore_module(
    module: str,
    inputs: list[dict[str, Any]] | None = None,
    params: dict[str, Any] | None = None,
    executor: str = "local",
    docker_enabled: bool = True,
) -> dict[str, Any]:
    """Run an nf-core community module (e.g., 'fastqc', 'samtools/view')."""
    result = _run_nfcore_module(
        module,
        inputs=inputs,
        params=params,
        executor=executor,
        docker_enabled=docker_enabled,
    )
    return {
        "success": True,
        "output_files": result.get_output_files(),
        "execution_report": result.get_execution_report(),
    }


# Global state for workflow composition (reset on server restart)
_saved_processes: dict[str, SavedProcess] = {}


@mcp.tool()
def save_process(
    name: str,
    process_code: str,
    module_ref: str | None = None,
) -> dict[str, Any]:
    """Save a tested process to the workflow session.

    Args:
        name: Process name (e.g., "FASTQC")
        process_code: Complete process { ... } block
        module_ref: Optional nf-core module reference (e.g., "nf-core/fastqc")
    """
    _saved_processes[name] = SavedProcess(
        name=name,
        code=process_code,
        module_ref=module_ref,
        saved_at=datetime.now(),
    )
    return {
        "success": True,
        "name": name,
        "module_ref": module_ref,
        "total_processes": len(_saved_processes),
    }


@mcp.tool()
def list_saved_processes() -> dict[str, Any]:
    """List all processes saved in the current workflow session."""
    processes = []
    for name, proc in _saved_processes.items():
        # Show first 100 chars of code as preview
        preview = proc.code[:100] + "..." if len(proc.code) > 100 else proc.code
        processes.append({
            "name": name,
            "module_ref": proc.module_ref,
            "saved_at": proc.saved_at.isoformat(),
            "code_preview": preview,
        })
    return {
        "total": len(processes),
        "processes": processes,
    }


@mcp.tool()
def export_workflow(
    output_path: str,
    workflow_name: str = "main",
    include_stub: bool = True,
) -> dict[str, Any]:
    """Export saved processes to a Nextflow file.

    Args:
        output_path: Where to write (e.g., "pipeline.nf")
        workflow_name: Name for the workflow block
        include_stub: Add workflow{} stub for wiring
    """
    if not _saved_processes:
        return {"success": False, "error": "No processes saved. Use save_process first."}

    # Build the file content
    lines = [
        "#!/usr/bin/env nextflow",
        "nextflow.enable.dsl = 2",
        "",
        "// Processes",
    ]

    process_names = []
    for name, proc in _saved_processes.items():
        process_names.append(name)
        if proc.module_ref:
            lines.append(f"// Source: {proc.module_ref}")
        lines.append(proc.code)
        lines.append("")

    if include_stub:
        lines.extend([
            f"workflow {workflow_name} {{",
            "    // TODO: Wire processes together",
            f"    // Available processes: {', '.join(process_names)}",
            "}",
        ])

    content = "\n".join(lines)

    # Write to file
    path = Path(output_path)
    path.write_text(content)

    return {
        "success": True,
        "path": str(path.absolute()),
        "processes_included": process_names,
        "workflow_name": workflow_name,
    }


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
