"""Tests for Nextflow auto-configuration and validation."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from pynf.config import (
    find_java,
    find_newest_jar,
    discover_nextflow_jar,
    parse_nextflow_wrapper_java,
    run_nextflow_smoke_test,
    validate_nextflow_setup,
    get_java_env,
    COMMON_JAVA_PATHS,
    ERROR_MSG_NO_JAVA,
    ERROR_MSG_NO_JAR,
    ERROR_MSG_JAR_NO_JAVA,
    ERROR_MSG_SMOKE_TEST_FAILED,
)


class TestFindJava:
    """Tests for find_java() multi-strategy Java detection."""

    def test_finds_java_via_nxf_java_home(self, tmp_path, monkeypatch):
        """NXF_JAVA_HOME takes highest priority."""
        java_home = tmp_path / "java"
        java_bin = java_home / "bin" / "java"
        java_bin.parent.mkdir(parents=True)
        java_bin.touch()
        java_bin.chmod(0o755)

        monkeypatch.setenv("NXF_JAVA_HOME", str(java_home))
        monkeypatch.delenv("JAVA_HOME", raising=False)

        result = find_java()
        assert result == java_bin

    def test_finds_java_via_java_home(self, tmp_path, monkeypatch):
        """JAVA_HOME is checked after NXF_JAVA_HOME."""
        java_home = tmp_path / "java"
        java_bin = java_home / "bin" / "java"
        java_bin.parent.mkdir(parents=True)
        java_bin.touch()
        java_bin.chmod(0o755)

        monkeypatch.delenv("NXF_JAVA_HOME", raising=False)
        monkeypatch.setenv("JAVA_HOME", str(java_home))

        result = find_java()
        assert result == java_bin

    def test_finds_java_via_macos_java_home_cmd(self, monkeypatch):
        """On macOS, /usr/libexec/java_home -v 17+ is checked."""
        monkeypatch.delenv("NXF_JAVA_HOME", raising=False)
        monkeypatch.delenv("JAVA_HOME", raising=False)

        with patch("platform.system", return_value="Darwin"):
            with patch("subprocess.run") as mock_run:
                # First call: java_home command
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = (
                    "/Library/Java/JavaVirtualMachines/openjdk-17.jdk/Contents/Home"
                )
                mock_run.return_value = mock_result

                with patch.object(Path, "exists", return_value=True):
                    result = find_java()
                    # Should have called java_home
                    assert mock_run.called
                    call_args = mock_run.call_args_list[0]
                    assert "/usr/libexec/java_home" in call_args[0][0]

    def test_finds_java_via_common_paths(self, tmp_path, monkeypatch):
        """Falls back to checking common installation paths."""
        monkeypatch.delenv("NXF_JAVA_HOME", raising=False)
        monkeypatch.delenv("JAVA_HOME", raising=False)

        # Create a fake java in a common path
        fake_java = (
            tmp_path / "opt" / "homebrew" / "opt" / "openjdk@17" / "bin" / "java"
        )
        fake_java.parent.mkdir(parents=True)
        fake_java.touch()

        # Patch COMMON_JAVA_PATHS to use our temp path
        with patch(
            "pynf.config.COMMON_JAVA_PATHS", {"Darwin": [fake_java], "Linux": []}
        ):
            with patch("platform.system", return_value="Darwin"):
                with patch(
                    "pynf.config.parse_nextflow_wrapper_java", return_value=None
                ):
                    result = find_java()
                    assert result == fake_java

    def test_returns_none_when_no_java_found(self, monkeypatch):
        """Returns None when Java cannot be found anywhere."""
        monkeypatch.delenv("NXF_JAVA_HOME", raising=False)
        monkeypatch.delenv("JAVA_HOME", raising=False)

        with patch("pynf.config.parse_nextflow_wrapper_java", return_value=None):
            with patch("pynf.config.COMMON_JAVA_PATHS", {"Darwin": [], "Linux": []}):
                result = find_java()
                assert result is None


class TestDiscoverNextflowJar:
    """Tests for discover_nextflow_jar() JAR discovery."""

    def test_finds_jar_via_env_var(self, tmp_path, monkeypatch):
        """NEXTFLOW_JAR_PATH environment variable takes priority."""
        jar_path = tmp_path / "nextflow-25.10.0-one.jar"
        jar_path.touch()

        monkeypatch.setenv("NEXTFLOW_JAR_PATH", str(jar_path))

        result = discover_nextflow_jar()
        assert result == jar_path

    def test_warns_when_env_var_path_not_found(self, tmp_path, monkeypatch, caplog):
        """Logs warning when NEXTFLOW_JAR_PATH points to nonexistent file."""
        monkeypatch.setenv("NEXTFLOW_JAR_PATH", "/nonexistent/path.jar")
        # Prevent fallback to real framework dir
        monkeypatch.setattr(
            "pynf.config.NEXTFLOW_FRAMEWORK_DIR", tmp_path / "nonexistent"
        )

        result = discover_nextflow_jar()
        assert result is None
        assert "NEXTFLOW_JAR_PATH set but file not found" in caplog.text

    def test_finds_jar_in_framework_dir(self, tmp_path, monkeypatch):
        """Finds JAR in ~/.nextflow/framework/ directory."""
        # Create fake framework directory structure
        framework_dir = tmp_path / ".nextflow" / "framework" / "25.10.2"
        framework_dir.mkdir(parents=True)
        jar_path = framework_dir / "nextflow-25.10.2-one.jar"
        jar_path.touch()

        monkeypatch.delenv("NEXTFLOW_JAR_PATH", raising=False)
        monkeypatch.setattr(
            "pynf.config.NEXTFLOW_FRAMEWORK_DIR", tmp_path / ".nextflow" / "framework"
        )

        result = discover_nextflow_jar()
        assert result == jar_path

    def test_finds_newest_jar_when_multiple_versions(self, tmp_path, monkeypatch):
        """When multiple versions exist, returns the newest (by mtime)."""
        framework_dir = tmp_path / ".nextflow" / "framework"

        # Create older version
        old_dir = framework_dir / "25.10.0"
        old_dir.mkdir(parents=True)
        old_jar = old_dir / "nextflow-25.10.0-one.jar"
        old_jar.touch()

        # Create newer version (touch with later time)
        import time

        time.sleep(0.01)  # Ensure different mtime

        new_dir = framework_dir / "25.10.2"
        new_dir.mkdir(parents=True)
        new_jar = new_dir / "nextflow-25.10.2-one.jar"
        new_jar.touch()

        monkeypatch.delenv("NEXTFLOW_JAR_PATH", raising=False)
        monkeypatch.setattr("pynf.config.NEXTFLOW_FRAMEWORK_DIR", framework_dir)

        result = discover_nextflow_jar()
        assert result == new_jar

    def test_returns_none_when_no_jar_found(self, tmp_path, monkeypatch):
        """Returns None when no JAR can be found."""
        monkeypatch.delenv("NEXTFLOW_JAR_PATH", raising=False)
        monkeypatch.setattr(
            "pynf.config.NEXTFLOW_FRAMEWORK_DIR", tmp_path / "nonexistent"
        )

        result = discover_nextflow_jar()
        assert result is None


class TestRunNextflowSmokeTest:
    """Tests for run_nextflow_smoke_test() validation."""

    def test_smoke_test_passes_with_valid_jar(self, tmp_path):
        """Smoke test passes when nextflow runs successfully."""
        jar_path = tmp_path / "nextflow.jar"
        jar_path.touch()
        java_path = Path("/usr/bin/java")  # Doesn't need to exist for mock

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = b"nextflow version 25.10.2"
            mock_run.return_value = mock_result

            success, message = run_nextflow_smoke_test(jar_path, java_path)

            assert success is True
            assert "25.10.2" in message

    def test_smoke_test_fails_with_broken_jar(self, tmp_path):
        """Smoke test fails when JAR is corrupted."""
        jar_path = tmp_path / "broken.jar"
        jar_path.touch()
        java_path = Path("/usr/bin/java")

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = b""
            mock_result.stderr = b"Error: Invalid or corrupt jarfile"
            mock_run.return_value = mock_result

            success, message = run_nextflow_smoke_test(jar_path, java_path)

            assert success is False
            assert "Invalid or corrupt jarfile" in message

    def test_smoke_test_fails_on_timeout(self, tmp_path):
        """Smoke test fails gracefully on timeout."""
        jar_path = tmp_path / "nextflow.jar"
        jar_path.touch()
        java_path = Path("/usr/bin/java")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="java", timeout=30)

            success, message = run_nextflow_smoke_test(jar_path, java_path)

            assert success is False
            assert "timed out" in message.lower()


class TestValidateNextflowSetup:
    """Tests for validate_nextflow_setup() full validation flow."""

    def test_success_with_java_and_jar_and_smoke_test(self, tmp_path, monkeypatch):
        """Full validation passes when everything works."""
        # Setup: Java found, JAR found, smoke test passes
        java_path = tmp_path / "java" / "bin" / "java"
        java_path.parent.mkdir(parents=True)
        java_path.touch()

        jar_path = tmp_path / "nextflow.jar"
        jar_path.touch()

        with patch("pynf.config.find_java", return_value=java_path):
            with patch("pynf.config.discover_nextflow_jar", return_value=jar_path):
                with patch(
                    "pynf.config.run_nextflow_smoke_test",
                    return_value=(True, "nextflow 25.10.2"),
                ):
                    success, message = validate_nextflow_setup()

                    assert success is True
                    assert "25.10.2" in message

    def test_fails_when_no_java(self):
        """Validation fails with helpful message when Java not found."""
        with patch("pynf.config.find_java", return_value=None):
            with patch("pynf.config.discover_nextflow_jar", return_value=None):
                success, message = validate_nextflow_setup()

                assert success is False
                assert "Java 17+ is required" in message
                assert "brew install openjdk@17" in message

    def test_fails_when_no_jar_but_java_available(self, tmp_path):
        """Validation fails with specific message when JAR missing but Java present."""
        java_path = tmp_path / "java" / "bin" / "java"
        java_path.parent.mkdir(parents=True)
        java_path.touch()

        with patch("pynf.config.find_java", return_value=java_path):
            with patch("pynf.config.discover_nextflow_jar", return_value=None):
                success, message = validate_nextflow_setup()

                assert success is False
                assert "JAR not found" in message
                assert "curl -s https://get.nextflow.io" in message

    def test_fails_when_jar_exists_but_no_java(self, tmp_path):
        """Validation fails with specific message when JAR found but Java missing."""
        jar_path = tmp_path / "nextflow.jar"
        jar_path.touch()

        with patch("pynf.config.find_java", return_value=None):
            with patch("pynf.config.discover_nextflow_jar", return_value=jar_path):
                success, message = validate_nextflow_setup()

                assert success is False
                assert "JAR found at" in message
                assert "Java 17+ is required" in message

    def test_fails_when_smoke_test_fails(self, tmp_path):
        """Validation fails with error details when smoke test fails."""
        java_path = tmp_path / "java" / "bin" / "java"
        java_path.parent.mkdir(parents=True)
        java_path.touch()

        jar_path = tmp_path / "nextflow.jar"
        jar_path.touch()

        with patch("pynf.config.find_java", return_value=java_path):
            with patch("pynf.config.discover_nextflow_jar", return_value=jar_path):
                with patch(
                    "pynf.config.run_nextflow_smoke_test",
                    return_value=(False, "Error: corrupt jarfile"),
                ):
                    success, message = validate_nextflow_setup()

                    assert success is False
                    assert "installation appears broken" in message
                    assert "corrupt jarfile" in message
                    assert "rm -rf ~/.nextflow/framework" in message


class TestGetJavaEnv:
    """Tests for get_java_env() environment setup."""

    def test_sets_java_home_from_java_path(self, tmp_path):
        """JAVA_HOME is set to parent of bin/ directory."""
        java_home = tmp_path / "jdk-17"
        java_bin = java_home / "bin" / "java"
        java_bin.parent.mkdir(parents=True)
        java_bin.touch()

        env = get_java_env(java_bin)

        assert env["JAVA_HOME"] == str(java_home)
        assert str(java_bin.parent) in env["PATH"]

    def test_auto_detects_java_when_not_provided(self, tmp_path):
        """Auto-detects Java when path not provided."""
        java_path = tmp_path / "java" / "bin" / "java"
        java_path.parent.mkdir(parents=True)
        java_path.touch()

        with patch("pynf.config.find_java", return_value=java_path):
            env = get_java_env()
            assert "JAVA_HOME" in env


class TestIntegration:
    """Integration tests that run with real system state."""

    @pytest.mark.integration
    def test_real_java_detection(self):
        """Test that find_java() works on real system (if Java installed)."""
        java_path = find_java()
        if java_path is None:
            pytest.skip("Java not installed on this system")

        assert java_path.exists()
        assert java_path.name == "java"

    @pytest.mark.integration
    def test_real_jar_discovery(self):
        """Test that discover_nextflow_jar() works on real system (if installed)."""
        jar_path = discover_nextflow_jar()
        if jar_path is None:
            pytest.skip("Nextflow not installed on this system")

        assert jar_path.exists()
        assert jar_path.suffix == ".jar"

    @pytest.mark.integration
    def test_real_full_validation(self):
        """Test full validation on real system."""
        success, message = validate_nextflow_setup()

        if not success:
            # If validation fails, make sure we get a helpful error message
            assert any(
                keyword in message
                for keyword in ["Java", "JAR", "install", "brew", "curl"]
            )
        else:
            # If validation passes, message should contain version info
            assert "nextflow" in message.lower() or "version" in message.lower()
