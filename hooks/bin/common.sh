#!/usr/bin/env bash
# Shared by the hook wrappers. Source it, do not run it.
#
# Every hook fails open: if no usable python is found it prints "{}" and
# exits 0, so a broken machine never blocks Claude Code.

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
LIB_DIR="$PLUGIN_ROOT/hooks/lib"

# MEMPALACE_SHAREDBRAIN_PYTHON pins one interpreter and disables the search.
# Otherwise the usual locations are tried in order, Homebrew first so a Mac
# with a stale system python still gets a modern one.
find_python() {
  if [ -n "${MEMPALACE_SHAREDBRAIN_PYTHON:-}" ]; then
    [ -x "$MEMPALACE_SHAREDBRAIN_PYTHON" ] && { echo "$MEMPALACE_SHAREDBRAIN_PYTHON"; return 0; }
    return 1
  fi
  local c
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 2>/dev/null)" /usr/bin/python3; do
    [ -n "$c" ] && [ -x "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}

fail_open() {
  echo "{}"
  exit 0
}

run_lib() {
  local script="$1"; shift
  local py
  py="$(find_python)" || fail_open
  exec "$py" "$LIB_DIR/$script" "$@"
}
