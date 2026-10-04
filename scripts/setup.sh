#!/usr/bin/env bash
# Configure the plugin for this machine. Run with no arguments for usage.
#
#   scripts/setup.sh show
#   scripts/setup.sh init --agent-id my-laptop --url https://hub.example.com/mcp --token-env MEMPALACE_MCP_HTTP_TOKEN
#   scripts/setup.sh init --agent-id my-laptop --stdio-command "mempalace-mcp"
#   scripts/setup.sh init --agent-id my-laptop --transport none
#   scripts/setup.sh add-drawer drawer_x_y_abc "what it holds"
#   scripts/setup.sh probe
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/../hooks/bin/common.sh"
PY="$(find_python)" || { echo "python3 not found; set MEMPALACE_SHAREDBRAIN_PYTHON to an interpreter" >&2; exit 1; }
if [ $# -eq 0 ]; then
  exec "$PY" "$LIB_DIR/setup.py" --help
fi
exec "$PY" "$LIB_DIR/setup.py" "$@"
