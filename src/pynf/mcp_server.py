"""
Minimal MCP server for py-nf Nextflow execution.

Run with: pynf-mcp
"""
from mcp.server.fastmcp import FastMCP
from typing import Any

from .tools import run_nfcore_module as _run_nfcore_module
from . import run_module as _run_module

mcp = FastMCP(
    "py-nf",
    instructions="""Nextflow workflow execution. First JVM call is slow (~5-10s).
For nf-core modules: use docker_enabled=True for proper containers.""",
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


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
