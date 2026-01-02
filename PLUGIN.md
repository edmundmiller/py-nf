# OpenCode Plugin for py-nf

OpenCode plugin for py-nf MCP server - run Nextflow modules directly from OpenCode.

## Installation

1. Install plugin dependencies:
   ```bash
   bun install  # or npm install
   ```

2. Add to your `~/.config/opencode/opencode.json`:
   ```json
   {
     "plugins": [
       {
         "name": "py-nf",
         "path": "/absolute/path/to/py-nf",
         "enabled": true
       }
     ],
     "mcp": {
       "py-nf": {
         "command": ["uv", "run", "pynf-mcp"],
         "enabled": true
       }
     }
   }
   ```

3. Restart OpenCode

## Requirements

- [uv](https://docs.astral.sh/uv/) - Python package manager
- Java 17+ (for Nextflow execution)
- Bun or npm (for plugin dependencies)

## What This Plugin Does

1. Detects if `pynf-mcp` is installed
2. Auto-installs py-nf via `uv tool install nfpy` if missing
3. Validates setup and provides helpful messages

## MCP Tools

The MCP server provides these tools:

| Tool | Description |
|------|-------------|
| `run_module` | Run local `.nf` scripts |
| `run_nfcore_module` | Run nf-core modules (Docker recommended) |
| `save_process` | Save process to workflow session |
| `list_saved_processes` | List saved processes |
| `export_workflow` | Export to `.nf` file |

## Manual Installation

If auto-install fails:

```bash
uv tool install nfpy
```

## Development

Build the plugin:

```bash
bun run build  # compiles plugin.ts to plugin.js
```

## License

Apache-2.0
