#!/usr/bin/env bash
# Exercises every hook against fixtures and a fake MemPalace server.
# Needs bash and python3. Leaves nothing behind.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
HUB_PID=""
cleanup() { [ -n "$HUB_PID" ] && kill "$HUB_PID" 2>/dev/null; rm -rf "$TMP"; }
trap cleanup EXIT

export CLAUDE_PLUGIN_ROOT="$ROOT"
export MEMPALACE_SHAREDBRAIN_CONFIG="$TMP/config.json"
export MEMPALACE_SHAREDBRAIN_STATE="$TMP/state"
unset MEMPALACE_SHAREDBRAIN_PYTHON
PY="$(command -v python3)"
SS="$ROOT/hooks/bin/session-start.sh"
STOP="$ROOT/hooks/bin/stop-checkpoint.sh"
PRE="$ROOT/hooks/bin/precompact-snapshot.sh"
SETUP="$ROOT/scripts/setup.sh"

PASS=0; FAIL=0
ok()  { echo "ok    $1"; PASS=$((PASS + 1)); }
bad() { echo "FAIL  $1"; [ -n "${2:-}" ] && printf '      %s\n' "$2"; FAIL=$((FAIL + 1)); }
expect_eq()       { [ "$2" = "$3" ] && ok "$1" || bad "$1" "got: $2"; }
expect_contains() { case "$2" in *"$3"*) ok "$1" ;; *) bad "$1" "missing: $3" ;; esac; }
expect_missing()  { case "$2" in *"$3"*) bad "$1" "unexpected: $3" ;; *) ok "$1" ;; esac; }
context_of() { "$PY" -c 'import json,sys; d=json.load(sys.stdin); print(d.get("hookSpecificOutput",{}).get("additionalContext",""))'; }

echo "# syntax"
if "$PY" -m py_compile "$ROOT"/hooks/lib/*.py "$ROOT"/tests/fake_hub.py 2>"$TMP/compile.err"; then ok "python compiles"; else bad "python compiles" "$(cat "$TMP/compile.err")"; fi
rm -rf "$ROOT"/hooks/lib/__pycache__ "$ROOT"/tests/__pycache__

echo "# fail open"
OUT="$(echo '{}' | MEMPALACE_SHAREDBRAIN_PYTHON=/nonexistent/python3 "$SS")"
expect_eq "session-start with no python prints {}" "$OUT" "{}"
OUT="$(echo '{}' | MEMPALACE_SHAREDBRAIN_PYTHON=/nonexistent/python3 "$STOP")"
expect_eq "stop with no python prints {}" "$OUT" "{}"
OUT="$(echo 'not json' | "$SS" | context_of)"
expect_contains "session-start survives bad stdin" "$OUT" "MEMPALACE SHARED BRAIN"

echo "# bootstrap block, no transport"
"$SETUP" init --agent-id test-agent --transport none >/dev/null
"$SETUP" add-drawer drawer_demo_rules_0001 "house rules" >/dev/null
OUT="$(echo '{"session_id":"t1","source":"startup"}' | "$SS" | context_of)"
expect_contains "agent id in context" "$OUT" "Agent id: test-agent"
expect_contains "inbox step names the agent" "$OUT" "to_agent=test-agent"
expect_contains "canonical drawer listed" "$OUT" "drawer_demo_rules_0001  house rules"
expect_contains "probe skipped with no transport" "$OUT" "Live check: skipped"
expect_missing "no pending handoff for a fresh session" "$OUT" "snapshotted them to"

echo "# transcript fixture"
"$PY" - "$TMP/transcript.jsonl" <<'PYEOF'
import json, sys
out = open(sys.argv[1], "w")
def w(obj): out.write(json.dumps(obj) + "\n")
ts = "2026-10-04T01:00:00.000Z"
for i in range(17):
    w({"type": "user", "timestamp": ts, "message": {"role": "user", "content": "human turn %d" % i}})
    w({"type": "assistant", "timestamp": ts, "message": {"role": "assistant", "content": [
        {"type": "text", "text": "reply %d" % i},
        {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}})
    w({"type": "user", "timestamp": ts, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "x", "content": "listing"}]}})
    w({"type": "user", "timestamp": ts, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "y", "content": "more"}]}})
for i in range(5):
    w({"type": "user", "isMeta": True, "timestamp": ts, "message": {"role": "user", "content": "Stop hook feedback: save"}})
w({"type": "user", "timestamp": ts, "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user]"}]}})
w({"type": "user", "timestamp": ts, "message": {"role": "user", "content": "<command-message>inbox</command-message>"}})
for i in range(3):
    w({"type": "user", "isSidechain": True, "timestamp": ts, "message": {"role": "user", "content": "subagent prompt"}})
w({"type": "user", "timestamp": ts, "message": {"role": "user", "content": [{"type": "image", "source": {}}]}})
out.write("this line is not json\n")
PYEOF
COUNT="$("$PY" -c "import sys; sys.path.insert(0,'$ROOT/hooks/lib'); import sb_transcript as T; print(T.count_human_turns('$TMP/transcript.jsonl'))")"
expect_eq "counter sees 18 human turns (17 text + 1 pasted image)" "$COUNT" "18"

echo "# stop checkpoint"
PAYLOAD="{\"session_id\":\"t1\",\"transcript_path\":\"$TMP/transcript.jsonl\",\"stop_hook_active\":false}"
OUT="$(echo "$PAYLOAD" | "$STOP")"
expect_contains "first stop at 18 turns blocks" "$OUT" '"decision": "block"'
expect_contains "block reason names the agent" "$OUT" "added_by to test-agent"
OUT="$(echo "$PAYLOAD" | "$STOP")"
expect_eq "immediate re-run does not fire again" "$OUT" "{}"
OUT="$(echo '{"session_id":"t1","stop_hook_active":true}' | "$STOP")"
expect_eq "stop_hook_active passes through" "$OUT" "{}"
OUT="$(echo '{"session_id":"t9","transcript_path":"/nonexistent"}' | "$STOP")"
expect_eq "missing transcript is quiet" "$OUT" "{}"
echo 999 > "$TMP/state/t1_last_save"
OUT="$(echo "$PAYLOAD" | "$STOP")"
expect_eq "stale inflated count is re-baselined quietly" "$OUT" "{}"
expect_contains "re-baseline logged" "$(cat "$TMP/state/hook.log")" "re-baselined stale count to 18"
"$SETUP" set checkpoint.save_interval 0 >/dev/null
rm -f "$TMP/state/t1_last_save"
OUT="$(echo "$PAYLOAD" | "$STOP")"
expect_eq "save_interval 0 disables the checkpoint" "$OUT" "{}"
"$SETUP" set checkpoint.save_interval 15 >/dev/null

echo "# precompact snapshot and handoff"
OUT="$(echo "{\"session_id\":\"t1\",\"transcript_path\":\"$TMP/transcript.jsonl\",\"trigger\":\"auto\"}" | "$PRE")"
expect_eq "precompact never blocks" "$OUT" "{}"
[ -s "$TMP/state/pending/t1.md" ] && ok "pending snapshot written" || bad "pending snapshot written"
expect_contains "snapshot holds human turns" "$(cat "$TMP/state/pending/t1.md")" "### HUMAN"
expect_contains "snapshot holds tool names not output" "$(cat "$TMP/state/pending/t1.md")" "[tool_use Bash]"
expect_missing "snapshot drops tool output" "$(cat "$TMP/state/pending/t1.md")" "listing"
SIZE1="$(wc -c < "$TMP/state/pending/t1.md")"
echo "{\"session_id\":\"t1\",\"transcript_path\":\"$TMP/transcript.jsonl\",\"trigger\":\"auto\"}" | "$PRE" >/dev/null
SIZE2="$(wc -c < "$TMP/state/pending/t1.md")"
expect_eq "second precompact adds nothing new" "$SIZE1" "$SIZE2"
OUT="$(echo '{"session_id":"t1","source":"compact"}' | "$SS" | context_of)"
expect_contains "post-compact handoff names the pending file" "$OUT" "snapshotted them to"
expect_contains "post-compact still carries the bootstrap block" "$OUT" "Agent id: test-agent"
expect_missing "probe skipped after compaction" "$OUT" "Live check"
OUT="$(echo '{"session_id":"t1","transcript_path":"/nonexistent","trigger":"manual"}' | "$PRE")"
expect_eq "precompact with no transcript is quiet" "$OUT" "{}"

echo "# http probe (json)"
"$PY" "$ROOT/tests/fake_hub.py" --http 0 --token test-token > "$TMP/hub.out" &
HUB_PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do grep -q listening "$TMP/hub.out" 2>/dev/null && break; sleep 0.2; done
PORT="$(sed -n 's/listening on //p' "$TMP/hub.out")"
"$SETUP" init --transport http --url "http://127.0.0.1:$PORT/mcp" --token-env MEMPALACE_TEST_TOKEN >/dev/null
OUT="$(MEMPALACE_TEST_TOKEN=test-token "$SETUP" probe 2>&1)"
expect_contains "probe reaches the hub" "$OUT" "palace reachable, 1234 drawers"
expect_contains "probe counts open vs unacked" "$OUT" "3, of which 2 have no ack"
expect_contains "unacked task listed" "$OUT" "  - evt_task_unacked"
expect_contains "broadcast listed" "$OUT" "  - evt_broadcast"
expect_missing "acked task not listed" "$OUT" "  - evt_task_acked"
expect_missing "task for another agent not listed" "$OUT" "evt_not_mine"
OUT="$(env -u MEMPALACE_TEST_TOKEN "$SETUP" probe 2>&1)"; RC=$?
expect_contains "missing token reports 401 with a hint" "$OUT" "HTTP 401"
expect_contains "401 hint mentions token" "$OUT" "wants a token"
expect_eq "probe exits non-zero when unreachable" "$RC" "1"
OUT="$(MEMPALACE_TEST_TOKEN=test-token sh -c "echo '{\"session_id\":\"t3\",\"source\":\"startup\"}' | '$SS'" | context_of)"
expect_contains "session-start carries the live check" "$OUT" "Live check (http"
expect_contains "session-start lists unacked tasks" "$OUT" "2 have no ack"
"$SETUP" init --token-env "" --token-command "printf test-token" >/dev/null
OUT="$("$SETUP" probe 2>&1)"
expect_contains "token_command path works" "$OUT" "palace reachable"
kill "$HUB_PID"; wait "$HUB_PID" 2>/dev/null; HUB_PID=""

echo "# http probe (sse)"
"$PY" "$ROOT/tests/fake_hub.py" --http 0 --sse > "$TMP/hub.out" &
HUB_PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do grep -q listening "$TMP/hub.out" 2>/dev/null && break; sleep 0.2; done
PORT="$(sed -n 's/listening on //p' "$TMP/hub.out")"
"$SETUP" init --url "http://127.0.0.1:$PORT/mcp" --token-command "" >/dev/null
OUT="$("$SETUP" probe 2>&1)"
expect_contains "sse responses parsed" "$OUT" "palace reachable, 1234 drawers"
kill "$HUB_PID"; wait "$HUB_PID" 2>/dev/null; HUB_PID=""
OUT="$("$SETUP" probe 2>&1)"
expect_contains "dead server reported, not raised" "$OUT" "FAILED, cannot reach"

echo "# stdio probe"
"$SETUP" init --transport stdio --stdio-command "$PY $ROOT/tests/fake_hub.py --stdio" >/dev/null
OUT="$("$SETUP" probe 2>&1)"
expect_contains "stdio transport works" "$OUT" "Live check (stdio"
expect_contains "stdio sees the inbox" "$OUT" "3, of which 2 have no ack"
"$SETUP" init --stdio-command "/nonexistent/mempalace-mcp" >/dev/null
OUT="$("$SETUP" probe 2>&1)"
expect_contains "stdio start failure reported" "$OUT" "cannot start"

echo "# config tool"
OUT="$("$SETUP" show)"
expect_contains "show prints agent id" "$OUT" "agent_id:    test-agent"
"$SETUP" remove-drawer drawer_demo_rules_0001 >/dev/null
OUT="$(echo '{"session_id":"t4","source":"clear"}' | "$SS" | context_of)"
expect_missing "removed drawer gone from context" "$OUT" "drawer_demo_rules_0001"
rm -f "$MEMPALACE_SHAREDBRAIN_CONFIG"
OUT="$(echo '{"session_id":"t5","source":"startup"}' | "$SS" | context_of)"
expect_contains "no config still yields a bootstrap block" "$OUT" "MEMPALACE SHARED BRAIN"

rm -rf "$ROOT"/hooks/lib/__pycache__ "$ROOT"/tests/__pycache__
echo
echo "passed $PASS, failed $FAIL"
[ "$FAIL" -eq 0 ]
