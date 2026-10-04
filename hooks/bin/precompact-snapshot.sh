#!/usr/bin/env bash
# PreCompact hook: writes everything since the last snapshot to a pending
# file, without using any model context. Never blocks compaction.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
run_lib precompact.py
