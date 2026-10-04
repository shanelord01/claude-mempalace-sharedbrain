#!/usr/bin/env bash
# SessionStart hook: injects the MemPalace bootstrap checklist, the live
# inbox check, and any pre-compaction snapshot waiting to be filed.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
run_lib session_start.py
