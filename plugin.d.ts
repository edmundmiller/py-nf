/**
 * OpenCode plugin for py-nf - Nextflow execution via MCP
 *
 * This plugin:
 * 1. Detects if pynf-mcp is installed
 * 2. Auto-installs py-nf if missing (via uv)
 * 3. Provides helpful setup messages
 *
 * The actual Nextflow tools are provided by the MCP server.
 * Users must configure MCP in their opencode.json:
 *
 * "mcp": {
 *   "py-nf": {
 *     "type": "local",
 *     "command": ["uv", "run", "pynf-mcp"]
 *   }
 * }
 */
import type { Plugin } from "@opencode-ai/plugin";
export declare const PyNfPlugin: Plugin;
