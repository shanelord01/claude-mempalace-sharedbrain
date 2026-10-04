#!/usr/bin/env bash
# Stop hook: every N human turns, asks the model to file this session's
# durable outcomes to the palace before it stops.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
run_lib stop_checkpoint.py
