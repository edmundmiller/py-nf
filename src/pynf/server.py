"""
Minimal HTTP server for py-nf integration with opencode.

Run with: pynf-server
Or: python -m pynf.server
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uvicorn

from pynf import run_module
from pynf.tools import run_nfcore_module, list_modules, list_submodules, inspect_module, get_module_inputs

app = FastAPI(title="py-nf Server", version="0.1.0")


class RunModuleRequest(BaseModel):
    script_path: str
    inputs: Optional[List[Dict[str, Any]]] = None
    params: Optional[Dict[str, Any]] = None
    executor: str = "local"
    docker_enabled: bool = False
    verbose: bool = False


class RunNfCoreModuleRequest(BaseModel):
    module: str
    inputs: Optional[List[Dict[str, Any]]] = None
    params: Optional[Dict[str, Any]] = None
    executor: str = "local"
    docker_enabled: bool = False
    verbose: bool = False


class RunModuleResponse(BaseModel):
    success: bool
    output_files: List[str]
    execution_report: Dict[str, Any]
    error: Optional[str] = None


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/run_module", response_model=RunModuleResponse)
async def api_run_module(request: RunModuleRequest):
    """Run a Nextflow script with provided inputs and parameters."""
    try:
        docker_config = None
        if request.docker_enabled:
            docker_config = {"enabled": True, "registry": "quay.io"}

        result = run_module(
            request.script_path,
            inputs=request.inputs,
            params=request.params,
            executor=request.executor,
            docker_config=docker_config,
            verbose=request.verbose,
        )

        return RunModuleResponse(
            success=True,
            output_files=result.get_output_files(),
            execution_report=result.get_execution_report(),
        )
    except Exception as e:
        return RunModuleResponse(
            success=False,
            output_files=[],
            execution_report={},
            error=str(e),
        )


@app.post("/run_nfcore_module", response_model=RunModuleResponse)
async def api_run_nfcore_module(request: RunNfCoreModuleRequest):
    """Run an nf-core module (downloads if needed)."""
    try:
        result = run_nfcore_module(
            request.module,
            inputs=request.inputs,
            params=request.params,
            executor=request.executor,
            docker_enabled=request.docker_enabled,
            verbose=request.verbose,
        )

        return RunModuleResponse(
            success=True,
            output_files=result.get_output_files(),
            execution_report=result.get_execution_report(),
        )
    except Exception as e:
        return RunModuleResponse(
            success=False,
            output_files=[],
            execution_report={},
            error=str(e),
        )


@app.get("/list_modules")
async def api_list_modules():
    """List available nf-core modules."""
    try:
        modules = list_modules()
        return {"modules": modules}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/inspect_module/{module:path}")
async def api_inspect_module(module: str):
    """Inspect an nf-core module's metadata."""
    try:
        info = inspect_module(module)
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/list_submodules/{module}")
async def api_list_submodules(module: str):
    """List submodules available for a given nf-core module."""
    try:
        submodules = list_submodules(module)
        return {"module": module, "submodules": submodules}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_module_inputs/{module:path}")
async def api_get_module_inputs(module: str):
    """Extract input parameters from a module using Nextflow native API."""
    try:
        inputs = get_module_inputs(module)
        return {"module": module, "inputs": inputs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def main(host: str = "127.0.0.1", port: int = 8765):
    """Start the server."""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
