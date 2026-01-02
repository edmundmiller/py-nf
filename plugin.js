/**
 * Try to detect pynf-mcp installation
 */
async function detectPyNf($) {
    // Try 1: Check if pynf-mcp is in PATH (uv tool install location)
    try {
        await $ `which pynf-mcp`.quiet();
        return { found: true, location: "PATH" };
    }
    catch {
        // Not in PATH
    }
    // Try 2: Check if uv can run it (project-based or tool install)
    try {
        await $ `uv run pynf-mcp --help`.quiet();
        return { found: true, location: "uv" };
    }
    catch {
        // uv can't find it either
    }
    return { found: false };
}
/**
 * Check if uv is installed
 */
async function hasUv($) {
    try {
        await $ `which uv`.quiet();
        return true;
    }
    catch {
        return false;
    }
}
/**
 * Attempt to install py-nf via uv
 */
async function installPyNf($) {
    console.log("[opencode-py-nf] Installing py-nf via uv...");
    try {
        // Install as a uv tool (globally available)
        await $ `uv tool install nfpy`;
        console.log("[opencode-py-nf] py-nf installed successfully ✓");
        return { success: true };
    }
    catch (e) {
        const error = e?.message || String(e);
        console.error("[opencode-py-nf] Failed to install py-nf:", error);
        return { success: false, error };
    }
}
export const PyNfPlugin = async ({ $ }) => {
    // Step 1: Check if uv is available
    const uvAvailable = await hasUv($);
    if (!uvAvailable) {
        console.warn("[opencode-py-nf] uv not found - required for py-nf");
        console.warn("[opencode-py-nf] Install uv: https://docs.astral.sh/uv/getting-started/installation/");
        return {};
    }
    // Step 2: Detect py-nf installation
    let detection = await detectPyNf($);
    // Step 3: Auto-install if not found
    if (!detection.found) {
        console.log("[opencode-py-nf] pynf-mcp not found, attempting auto-install...");
        const installResult = await installPyNf($);
        if (installResult.success) {
            // Re-detect after install
            detection = await detectPyNf($);
        }
    }
    // Step 4: Final status
    if (detection.found) {
        console.log(`[opencode-py-nf] pynf-mcp ready (${detection.location}) ✓`);
        console.log("[opencode-py-nf] Ensure MCP is configured in opencode.json:");
        console.log(`
  "mcp": {
    "py-nf": {
      "type": "local",
      "command": ["uv", "run", "pynf-mcp"]
    }
  }
`);
    }
    else {
        console.error("[opencode-py-nf] Could not install py-nf automatically");
        console.error("[opencode-py-nf] Manual install: uv tool install nfpy");
    }
    // Return empty hooks - plugin is just for setup/validation
    // The actual tools come from the MCP server
    return {};
};
