"""
Tests for the MCP server workflow composition tools.

Run with: uv run pytest tests/test_mcp_server.py -v
"""
import tempfile
from pathlib import Path

import pytest

from pynf.mcp_server import (
    save_process,
    list_saved_processes,
    export_workflow,
    _saved_processes,
    SavedProcess,
)


@pytest.fixture(autouse=True)
def clear_saved_processes():
    """Clear saved processes before and after each test."""
    _saved_processes.clear()
    yield
    _saved_processes.clear()


class TestSaveProcess:
    """Tests for the save_process tool."""

    def test_save_simple_process(self):
        """Test saving a simple process."""
        result = save_process(
            name="FASTQC",
            process_code="process FASTQC { input: tuple val(meta), path(reads) }",
        )

        assert result["success"] is True
        assert result["name"] == "FASTQC"
        assert result["module_ref"] is None
        assert result["total_processes"] == 1

    def test_save_process_with_module_ref(self):
        """Test saving a process with module reference."""
        result = save_process(
            name="FASTQC",
            process_code="process FASTQC { input: tuple val(meta), path(reads) }",
            module_ref="nf-core/fastqc",
        )

        assert result["success"] is True
        assert result["module_ref"] == "nf-core/fastqc"

    def test_save_multiple_processes(self):
        """Test saving multiple processes."""
        save_process(name="FASTQC", process_code="process FASTQC { }")
        result = save_process(name="MULTIQC", process_code="process MULTIQC { }")

        assert result["total_processes"] == 2

    def test_overwrite_existing_process(self):
        """Test that saving with the same name overwrites."""
        save_process(name="FASTQC", process_code="process FASTQC { version 1 }")
        result = save_process(name="FASTQC", process_code="process FASTQC { version 2 }")

        assert result["total_processes"] == 1
        assert "version 2" in _saved_processes["FASTQC"].code


class TestListSavedProcesses:
    """Tests for the list_saved_processes tool."""

    def test_list_empty(self):
        """Test listing when no processes are saved."""
        result = list_saved_processes()

        assert result["total"] == 0
        assert result["processes"] == []

    def test_list_single_process(self):
        """Test listing a single saved process."""
        save_process(
            name="FASTQC",
            process_code="process FASTQC { input: tuple val(meta), path(reads) }",
            module_ref="nf-core/fastqc",
        )

        result = list_saved_processes()

        assert result["total"] == 1
        assert len(result["processes"]) == 1

        proc = result["processes"][0]
        assert proc["name"] == "FASTQC"
        assert proc["module_ref"] == "nf-core/fastqc"
        assert "saved_at" in proc
        assert "code_preview" in proc

    def test_list_multiple_processes(self):
        """Test listing multiple saved processes."""
        save_process(name="FASTQC", process_code="process FASTQC { }")
        save_process(name="MULTIQC", process_code="process MULTIQC { }")
        save_process(name="BWA_MEM", process_code="process BWA_MEM { }")

        result = list_saved_processes()

        assert result["total"] == 3
        names = [p["name"] for p in result["processes"]]
        assert "FASTQC" in names
        assert "MULTIQC" in names
        assert "BWA_MEM" in names

    def test_code_preview_truncation(self):
        """Test that long code is truncated in preview."""
        long_code = "process FASTQC { " + "x" * 200 + " }"
        save_process(name="FASTQC", process_code=long_code)

        result = list_saved_processes()

        preview = result["processes"][0]["code_preview"]
        assert len(preview) <= 103  # 100 chars + "..."
        assert preview.endswith("...")


class TestExportWorkflow:
    """Tests for the export_workflow tool."""

    def test_export_empty_fails(self):
        """Test that export fails with no saved processes."""
        result = export_workflow(output_path="/tmp/test.nf")

        assert result["success"] is False
        assert "error" in result

    def test_export_single_process(self):
        """Test exporting a single process."""
        save_process(
            name="FASTQC",
            process_code="process FASTQC {\n    input:\n    tuple val(meta), path(reads)\n}",
            module_ref="nf-core/fastqc",
        )

        with tempfile.NamedTemporaryFile(suffix=".nf", delete=False) as f:
            output_path = f.name

        try:
            result = export_workflow(output_path=output_path)

            assert result["success"] is True
            assert result["processes_included"] == ["FASTQC"]
            assert result["workflow_name"] == "main"

            # Verify file content
            content = Path(output_path).read_text()
            assert "#!/usr/bin/env nextflow" in content
            assert "nextflow.enable.dsl = 2" in content
            assert "process FASTQC" in content
            assert "// Source: nf-core/fastqc" in content
            assert "workflow main {" in content
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_export_multiple_processes(self):
        """Test exporting multiple processes."""
        save_process(name="FASTQC", process_code="process FASTQC { }")
        save_process(name="MULTIQC", process_code="process MULTIQC { }")

        with tempfile.NamedTemporaryFile(suffix=".nf", delete=False) as f:
            output_path = f.name

        try:
            result = export_workflow(output_path=output_path)

            assert result["success"] is True
            assert "FASTQC" in result["processes_included"]
            assert "MULTIQC" in result["processes_included"]

            content = Path(output_path).read_text()
            assert "process FASTQC" in content
            assert "process MULTIQC" in content
            assert "// Available processes: FASTQC, MULTIQC" in content
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_export_custom_workflow_name(self):
        """Test exporting with custom workflow name."""
        save_process(name="FASTQC", process_code="process FASTQC { }")

        with tempfile.NamedTemporaryFile(suffix=".nf", delete=False) as f:
            output_path = f.name

        try:
            result = export_workflow(
                output_path=output_path,
                workflow_name="QC_PIPELINE",
            )

            assert result["workflow_name"] == "QC_PIPELINE"

            content = Path(output_path).read_text()
            assert "workflow QC_PIPELINE {" in content
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_export_without_stub(self):
        """Test exporting without workflow stub."""
        save_process(name="FASTQC", process_code="process FASTQC { }")

        with tempfile.NamedTemporaryFile(suffix=".nf", delete=False) as f:
            output_path = f.name

        try:
            result = export_workflow(
                output_path=output_path,
                include_stub=False,
            )

            assert result["success"] is True

            content = Path(output_path).read_text()
            assert "process FASTQC" in content
            assert "workflow" not in content
        finally:
            Path(output_path).unlink(missing_ok=True)


class TestWorkflowCompositionFlow:
    """Integration tests for the full workflow composition flow."""

    def test_full_composition_flow(self):
        """Test the complete flow: save -> list -> export."""
        # Step 1: Save processes
        save_process(
            name="FASTQC",
            process_code="""process FASTQC {
    input:
    tuple val(meta), path(reads)

    output:
    tuple val(meta), path("*.zip")

    script:
    \"\"\"
    fastqc ${reads}
    \"\"\"
}""",
            module_ref="nf-core/fastqc",
        )

        save_process(
            name="MULTIQC",
            process_code="""process MULTIQC {
    input:
    path(files)

    output:
    path("multiqc_report.html")

    script:
    \"\"\"
    multiqc .
    \"\"\"
}""",
            module_ref="nf-core/multiqc",
        )

        # Step 2: List and verify
        list_result = list_saved_processes()
        assert list_result["total"] == 2

        # Step 3: Export
        with tempfile.NamedTemporaryFile(suffix=".nf", delete=False) as f:
            output_path = f.name

        try:
            export_result = export_workflow(
                output_path=output_path,
                workflow_name="QC_PIPELINE",
            )

            assert export_result["success"] is True

            # Verify generated file is valid Nextflow structure
            content = Path(output_path).read_text()

            # Check DSL2 header
            assert "#!/usr/bin/env nextflow" in content
            assert "nextflow.enable.dsl = 2" in content

            # Check processes
            assert "process FASTQC" in content
            assert "process MULTIQC" in content
            assert "// Source: nf-core/fastqc" in content
            assert "// Source: nf-core/multiqc" in content

            # Check workflow block
            assert "workflow QC_PIPELINE {" in content
            assert "// TODO: Wire processes together" in content
        finally:
            Path(output_path).unlink(missing_ok=True)
