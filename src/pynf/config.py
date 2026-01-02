"""
Auto-configuration for Nextflow JAR discovery and setup.

Search order:
1. NEXTFLOW_JAR_PATH environment variable
2. ~/.nextflow/framework/*/nextflow-*-one.jar (official installer location)
3. Auto-download via `nextflow -version` if Java available
"""

import os
import re
import subprocess
import logging
import platform
from pathlib import Path
from glob import glob

logger = logging.getLogger(__name__)

NEXTFLOW_FRAMEWORK_DIR = Path.home() / ".nextflow" / "framework"

# Common Java installation paths by platform
COMMON_JAVA_PATHS = {
    "Darwin": [
        Path("/opt/homebrew/opt/openjdk@17/bin/java"),
        Path("/opt/homebrew/opt/openjdk@21/bin/java"),
        Path("/opt/homebrew/opt/openjdk/bin/java"),
        Path("/Library/Java/JavaVirtualMachines/openjdk-17.jdk/Contents/Home/bin/java"),
        Path("/Library/Java/JavaVirtualMachines/openjdk-21.jdk/Contents/Home/bin/java"),
    ],
    "Linux": [
        Path("/usr/lib/jvm/java-17-openjdk/bin/java"),
        Path("/usr/lib/jvm/java-17-openjdk-amd64/bin/java"),
        Path("/usr/lib/jvm/java-21-openjdk/bin/java"),
        Path("/usr/lib/jvm/java-21-openjdk-amd64/bin/java"),
        Path("/usr/lib/jvm/default-java/bin/java"),
    ],
}

# Error messages with platform-specific guidance
ERROR_MSG_NO_JAVA = """
Java 17+ is required but not found.

Install Java:
  # macOS (Homebrew)
  brew install openjdk@17

  # Linux (Ubuntu/Debian)
  sudo apt-get install openjdk-17-jdk

  # Linux (Fedora/RHEL)
  sudo dnf install java-17-openjdk

Then install Nextflow:
  curl -s https://get.nextflow.io | bash
  ./nextflow -version

Or set JAVA_HOME:
  export JAVA_HOME=/path/to/java
"""

ERROR_MSG_NO_JAR = """
Nextflow JAR not found (Java is available).

Install Nextflow:
  curl -s https://get.nextflow.io | bash
  ./nextflow -version

The JAR will be installed to ~/.nextflow/framework/
and auto-discovered on next startup.

Or set NEXTFLOW_JAR_PATH environment variable.
"""

ERROR_MSG_JAR_NO_JAVA = """
Nextflow JAR found at: {jar_path}

But Java 17+ is required and was not found.

Install Java:
  # macOS (Homebrew)
  brew install openjdk@17

  # Linux (Ubuntu/Debian)
  sudo apt-get install openjdk-17-jdk

Or set JAVA_HOME:
  export JAVA_HOME=/path/to/java
"""

ERROR_MSG_SMOKE_TEST_FAILED = """
Nextflow installation appears broken.

JAR path: {jar_path}
Error: {error}

Try reinstalling:
  rm -rf ~/.nextflow/framework
  curl -s https://get.nextflow.io | bash
  ./nextflow -version
"""


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


def parse_nextflow_wrapper_java() -> Path | None:
    """
    Parse the nextflow wrapper script to find its Java configuration.

    The nextflow wrapper checks (in order):
    1. NXF_JAVA_HOME -> JAVA_HOME
    2. JAVA_HOME/bin/java
    3. /usr/libexec/java_home -v 17+ (macOS)
    4. which java

    We replicate this logic to ensure we use the same Java that nextflow would use.

    Returns:
        Path to java binary, or None if not found
    """
    # Check common nextflow wrapper locations
    wrapper_paths = [
        Path.home() / ".local" / "bin" / "nextflow",
        Path.home() / "bin" / "nextflow",
        Path("/usr/local/bin/nextflow"),
        Path("/opt/homebrew/bin/nextflow"),
    ]

    wrapper_path = None
    for p in wrapper_paths:
        if p.exists():
            wrapper_path = p
            break

    if not wrapper_path:
        logger.debug("No nextflow wrapper found to parse")
        return None

    # Rather than parsing the bash script (fragile), we replicate nextflow's logic:
    # This matches the behavior in the wrapper script

    # 1. Check NXF_JAVA_HOME first (nextflow's override)
    nxf_java_home = os.getenv("NXF_JAVA_HOME")
    if nxf_java_home:
        java_bin = Path(nxf_java_home) / "bin" / "java"
        if java_bin.exists():
            logger.debug(f"Found Java via NXF_JAVA_HOME: {java_bin}")
            return java_bin

    # 2. Check JAVA_HOME
    java_home = os.getenv("JAVA_HOME")
    if java_home:
        java_bin = Path(java_home) / "bin" / "java"
        if java_bin.exists():
            logger.debug(f"Found Java via JAVA_HOME: {java_bin}")
            return java_bin

    # 3. macOS: use /usr/libexec/java_home -v 17+
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["/usr/libexec/java_home", "-v", "17+"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                java_bin = Path(result.stdout.strip()) / "bin" / "java"
                if java_bin.exists():
                    logger.debug(f"Found Java via java_home: {java_bin}")
                    return java_bin
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # 4. Fallback: which java
    try:
        result = subprocess.run(
            ["which", "java"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            java_bin = Path(result.stdout.strip())
            if java_bin.exists():
                logger.debug(f"Found Java via which: {java_bin}")
                return java_bin
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def find_java() -> Path | None:
    """
    Find Java installation using multiple strategies.

    Priority:
    1. NXF_JAVA_HOME environment variable (nextflow's preference)
    2. JAVA_HOME environment variable
    3. /usr/libexec/java_home -v 17+ (macOS)
    4. Common installation paths (Homebrew, system packages)
    5. 'java' in PATH

    Returns:
        Path to java binary, or None if not found
    """
    # Strategy 1 & 2 & 3 & 4 (via nextflow wrapper logic)
    java_path = parse_nextflow_wrapper_java()
    if java_path:
        return java_path

    # Strategy 4: Common installation paths
    system = platform.system()
    common_paths = COMMON_JAVA_PATHS.get(system, [])
    for path in common_paths:
        if path.exists():
            logger.debug(f"Found Java at common path: {path}")
            return path

    return None


def ensure_java_available() -> bool:
    """Check if Java 17+ is available."""
    return find_java() is not None


def get_java_env(java_path: Path | None = None) -> dict[str, str]:
    """
    Get environment variables with Java properly configured.

    Args:
        java_path: Path to java binary. If None, will be auto-detected.

    Returns:
        Environment dict with JAVA_HOME set
    """
    env = os.environ.copy()

    if java_path is None:
        java_path = find_java()

    if java_path:
        # JAVA_HOME should be the parent of bin/
        # e.g., /opt/homebrew/opt/openjdk@17/bin/java -> /opt/homebrew/opt/openjdk@17
        java_home = java_path.parent.parent
        env["JAVA_HOME"] = str(java_home)
        # Also ensure java is in PATH
        env["PATH"] = f"{java_path.parent}:{env.get('PATH', '')}"

    return env


def download_nextflow() -> Path | None:
    """
    Download Nextflow using the official installer.

    This runs `nextflow -version` which triggers the self-install
    of the JAR into ~/.nextflow/framework/.

    Returns:
        Path to the downloaded JAR, or None on failure
    """
    java_path = find_java()
    if not java_path:
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

            # Run nextflow -version to trigger JAR download with proper Java env
            env = get_java_env(java_path)
            result = subprocess.run(
                [str(nf_script), "-version"],
                capture_output=True,
                timeout=300,  # 5 min for download
                env=env,
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


def run_nextflow_smoke_test(jar_path: Path, java_path: Path) -> tuple[bool, str]:
    """
    Run a smoke test to verify Nextflow JAR works.

    Args:
        jar_path: Path to the Nextflow JAR
        java_path: Path to Java binary

    Returns:
        (success, error_or_version_message) tuple
    """
    try:
        env = get_java_env(java_path)
        # Run: java -jar nextflow.jar -version
        result = subprocess.run(
            [str(java_path), "-jar", str(jar_path), "-version"],
            capture_output=True,
            timeout=30,
            env=env,
        )
        if result.returncode == 0:
            version_output = result.stdout.decode().strip()
            logger.debug(f"Nextflow smoke test passed: {version_output}")
            return True, version_output
        else:
            error = result.stderr.decode().strip() or result.stdout.decode().strip()
            return False, f"Nextflow failed to run: {error}"
    except subprocess.TimeoutExpired:
        return False, "Nextflow smoke test timed out (30s)"
    except Exception as e:
        return False, f"Smoke test failed: {e}"


def validate_nextflow_setup() -> tuple[bool, str]:
    """
    Validate Nextflow is installed and working.

    Checks:
    1. Java 17+ is available
    2. Nextflow JAR exists
    3. Nextflow runs successfully (smoke test)

    Returns:
        (success, error_message) tuple. On success, error_message contains version info.
    """
    # Step 1: Find Java
    java_path = find_java()

    # Step 2: Find JAR
    jar_path = discover_nextflow_jar()

    # Determine error state
    if not java_path and not jar_path:
        return False, ERROR_MSG_NO_JAVA

    if not java_path and jar_path:
        return False, ERROR_MSG_JAR_NO_JAVA.format(jar_path=jar_path)

    if java_path and not jar_path:
        return False, ERROR_MSG_NO_JAR

    # Both found - run smoke test
    assert java_path is not None and jar_path is not None  # for type checker
    success, message = run_nextflow_smoke_test(jar_path, java_path)
    if not success:
        return False, ERROR_MSG_SMOKE_TEST_FAILED.format(
            jar_path=jar_path, error=message
        )

    return True, message


def get_nextflow_jar(auto_download: bool = False) -> Path:
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
