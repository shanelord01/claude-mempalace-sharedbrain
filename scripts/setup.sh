#!/usr/bin/env bash
# Configure and operate the plugin on this machine. Run with no arguments for usage.
#
#   scripts/setup.sh show
#   scripts/setup.sh init --host office-desktop --url https://hub.example.com/mcp --token-env MEMPALACE_MCP_HTTP_TOKEN
#   scripts/setup.sh rules install --write
#   scripts/setup.sh probe
#   scripts/setup.sh cursor set evt_...
#   scripts/setup.sh listen arm --correlation-id task_...
#   scripts/setup.sh peers
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/../hooks/bin/common.sh"
PY="$(find_python)" || { echo "python3 not found; set MEMPALACE_SHAREDBRAIN_PYTHON to an interpreter" >&2; exit 1; }
if [ $# -eq 0 ]; then
  exec "$PY" "$LIB_DIR/setup.py" --help
fi
exec "$PY" "$LIB_DIR/setup.py" "$@"
