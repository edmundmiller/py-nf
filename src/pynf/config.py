"""
Auto-configuration for Nextflow JAR discovery and setup.

Search order:
1. NEXTFLOW_JAR_PATH environment variable
2. ~/.nextflow/framework/*/nextflow-*-one.jar (official installer location)
3. Auto-download via `nextflow -version` if Java available
"""

import os
import subprocess
import logging
from pathlib import Path
from glob import glob

logger = logging.getLogger(__name__)

NEXTFLOW_FRAMEWORK_DIR = Path.home() / ".nextflow" / "framework"


def find_newest_jar(pattern: str) -> Path | None:
    """Find the newest JAR matching pattern, sorted by version."""
    matches = glob(pattern)
    if not matches:
        return None
    # Sort by modification time, newest first
    matches.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
    return Path(matches[0])


def discover_nextflow_jar() -> Path | None:
    """
    Discover Nextflow JAR from standard locations.

    Returns:
        Path to the JAR file, or None if not found
    """
    # 1. Check environment variable
    env_path = os.getenv("NEXTFLOW_JAR_PATH")
    if env_path:
        jar_path = Path(env_path).expanduser()
        if jar_path.exists():
            logger.debug(f"Using JAR from NEXTFLOW_JAR_PATH: {jar_path}")
            return jar_path
        logger.warning(f"NEXTFLOW_JAR_PATH set but file not found: {env_path}")

    # 2. Check ~/.nextflow/framework/*/nextflow-*-one.jar
    if NEXTFLOW_FRAMEWORK_DIR.exists():
        pattern = str(NEXTFLOW_FRAMEWORK_DIR / "*" / "nextflow-*-one.jar")
        jar_path = find_newest_jar(pattern)
        if jar_path:
            logger.debug(f"Found JAR in framework dir: {jar_path}")
            return jar_path

    return None


def ensure_java_available() -> bool:
    """Check if Java is available in PATH or JAVA_HOME."""
    # Check JAVA_HOME first
    java_home = os.getenv("JAVA_HOME")
    if java_home:
        java_bin = Path(java_home) / "bin" / "java"
        if java_bin.exists():
            return True

    # Check PATH
    try:
        result = subprocess.run(["java", "-version"], capture_output=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def download_nextflow() -> Path | None:
    """
    Download Nextflow using the official installer.

    This runs `nextflow -version` which triggers the self-install
    of the JAR into ~/.nextflow/framework/.

    Returns:
        Path to the downloaded JAR, or None on failure
    """
    if not ensure_java_available():
        logger.error("Java not found. Install Java 17+ to use Nextflow.")
        return None

    logger.info("Downloading Nextflow...")

    try:
        # Download nextflow script to temp location
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            nf_script = Path(tmpdir) / "nextflow"

            # Download installer
            result = subprocess.run(
                ["curl", "-fsSL", "https://get.nextflow.io", "-o", str(nf_script)],
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.error(f"Failed to download installer: {result.stderr.decode()}")
                return None

            nf_script.chmod(0o755)

            # Run nextflow -version to trigger JAR download
            result = subprocess.run(
                [str(nf_script), "-version"],
                capture_output=True,
                timeout=300,  # 5 min for download
            )
            if result.returncode != 0:
                logger.error(f"Nextflow setup failed: {result.stderr.decode()}")
                return None

        # Now find the downloaded JAR
        return discover_nextflow_jar()

    except subprocess.TimeoutExpired:
        logger.error("Nextflow download timed out")
        return None
    except Exception as e:
        logger.error(f"Failed to download Nextflow: {e}")
        return None


def get_nextflow_jar(auto_download: bool = True) -> Path:
    """
    Get the Nextflow JAR path, optionally downloading if not found.

    Args:
        auto_download: If True, attempt to download Nextflow if not found

    Returns:
        Path to the Nextflow JAR

    Raises:
        FileNotFoundError: If JAR not found and download disabled/failed
    """
    # Try to discover existing JAR
    jar_path = discover_nextflow_jar()
    if jar_path:
        return jar_path

    # Attempt auto-download if enabled
    if auto_download:
        jar_path = download_nextflow()
        if jar_path:
            return jar_path

    # Provide helpful error message
    raise FileNotFoundError(
        "\n" + "=" * 60 + "\n"
        "Nextflow JAR not found.\n"
        "=" * 60 + "\n\n"
        "To install Nextflow:\n"
        "  1. Install Java 17+: brew install openjdk@17\n"
        "  2. Run: curl -s https://get.nextflow.io | bash\n"
        "  3. Run: ./nextflow -version\n\n"
        "The JAR will be installed to ~/.nextflow/framework/\n"
        "and auto-discovered on next startup.\n"
        "=" * 60 + "\n"
    )
