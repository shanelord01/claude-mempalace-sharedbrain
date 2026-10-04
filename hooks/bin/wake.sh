#!/usr/bin/env bash
# UserPromptSubmit hook: when listening is armed, sweeps the hub for new
# coordination events addressed to this identity and places matches in context.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
run_lib wake.py
