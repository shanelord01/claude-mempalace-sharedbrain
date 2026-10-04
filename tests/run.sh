#!/usr/bin/env bash
# Exercises every hook and the setup tool against fixtures and a fake hub.
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
export MEMPALACE_SHAREDBRAIN_AGENT_SOCK=""   # never the real 1Password agent; the agent tests start their own
export CLAUDE_PROJECT_DIR=/tmp/demo   # the workspace the scripts and hooks compose the project from
PY="$(command -v python3)"
SS="$ROOT/hooks/bin/session-start.sh"
WAKE="$ROOT/hooks/bin/wake.sh"
STOP="$ROOT/hooks/bin/stop-checkpoint.sh"
PRE="$ROOT/hooks/bin/precompact-snapshot.sh"
SETUP="$ROOT/scripts/setup.sh"
CLAUDE_MD="$TMP/CLAUDE.md"

PASS=0; FAIL=0
ok()  { echo "ok    $1"; PASS=$((PASS + 1)); }
bad() { echo "FAIL  $1"; [ -n "${2:-}" ] && printf '      %s\n' "$2"; FAIL=$((FAIL + 1)); }
expect_eq()       { [ "$2" = "$3" ] && ok "$1" || bad "$1" "got: $2"; }
expect_contains() { case "$2" in *"$3"*) ok "$1" ;; *) bad "$1" "missing: $3" ;; esac; }
expect_missing()  { case "$2" in *"$3"*) bad "$1" "unexpected: $3" ;; *) ok "$1" ;; esac; }
context_of() { "$PY" -c 'import json,sys; d=json.load(sys.stdin); print(d.get("hookSpecificOutput",{}).get("additionalContext",""))'; }
start_hub() { "$PY" "$ROOT/tests/fake_hub.py" --http 0 "$@" > "$TMP/hub.out" & HUB_PID=$!; for _ in 1 2 3 4 5 6 7 8 9 10; do grep -q listening "$TMP/hub.out" 2>/dev/null && break; sleep 0.2; done; PORT="$(sed -n 's/listening on //p' "$TMP/hub.out")"; }
stop_hub() { [ -n "$HUB_PID" ] && { kill "$HUB_PID"; wait "$HUB_PID" 2>/dev/null; HUB_PID=""; }; }

echo "# syntax"
if "$PY" -m py_compile "$ROOT"/hooks/lib/*.py "$ROOT"/tests/fake_hub.py 2>"$TMP/compile.err"; then ok "python compiles"; else bad "python compiles" "$(cat "$TMP/compile.err")"; fi

echo "# fail open"
OUT="$(echo '{}' | MEMPALACE_SHAREDBRAIN_PYTHON=/nonexistent/python3 "$SS")"
expect_eq "session-start with no python prints {}" "$OUT" "{}"
OUT="$(echo '{}' | MEMPALACE_SHAREDBRAIN_PYTHON=/nonexistent/python3 "$WAKE")"
expect_eq "wake with no python prints {}" "$OUT" "{}"
OUT="$(echo 'not json' | "$SS" | context_of)"
expect_contains "session-start survives bad stdin" "$OUT" "MEMPALACE SHARED BRAIN"

echo "# identity"
"$SETUP" init --host "Office Desktop" --rules-target "$CLAUDE_MD" --transport none >/dev/null
expect_eq "host label sanitised" "$("$SETUP" identity --cwd "/tmp/My Project")" "office-desktop:claude:my-project"
expect_eq "project component falls back" "$("$SETUP" identity --cwd "/")" "office-desktop:claude:workspace"
"$SETUP" init --fixed-id legacy-box >/dev/null
expect_eq "fixed id overrides composition" "$("$SETUP" identity --cwd /tmp/x)" "legacy-box"
"$SETUP" init --no-fixed-id >/dev/null
printf '{"agent_id":"old-style-id","hub":{"transport":"none"}}\n' > "$TMP/legacy.json"
expect_eq "0.1 config agent_id becomes the fixed identity" "$(MEMPALACE_SHAREDBRAIN_CONFIG=$TMP/legacy.json "$SETUP" identity)" "old-style-id"

echo "# rules block"
EXPECTED="$("$PY" - "$ROOT/vendor/shared_brain_rules.md" <<'PYEOF'
import sys
body = open(sys.argv[1], encoding="utf-8").read().replace("<HOST>", "office-desktop").replace("<HARNESS>", "claude").replace("<PROJECT>", "demo")
start = ("<!-- mempalace-shared-brain:start (canonical source: mempalace repo integrations/shared/coordination-protocol.md — edit there, "
         "re-render with `mempalace rules --host office-desktop --harness claude --project demo`) -->")
print("\n".join([start, "", body.rstrip("\n"), "", "<!-- mempalace-shared-brain:end -->"]))
PYEOF
)"
RENDERED="$("$SETUP" rules render --project demo 2>/dev/null)"
expect_eq "render matches the mempalace rules layout byte for byte" "$RENDERED" "$EXPECTED"
expect_contains "render fills the identity" "$RENDERED" "office-desktop:claude:<project>"
LIGHT="$("$SETUP" rules render --project demo --mcp light 2>/dev/null)"
expect_contains "light mcp swaps supersede" "$LIGHT" "palace_exec KG SUPERSEDE"
expect_contains "light mcp swaps kg_add" "$LIGHT" "palace_exec KG ADD"
expect_missing "light mcp leaves no full tool names" "$LIGHT" "mempalace_kg_add"
"$SETUP" rules render --host "Bad Host" >/dev/null 2>&1; expect_eq "invalid host rejected" "$?" "1"
"$SETUP" rules check --project demo >/dev/null; expect_eq "check: missing exits 3" "$?" "3"
printf '# My instructions\n\nKeep this.\n' > "$CLAUDE_MD"
OUT="$("$SETUP" rules install --project demo)"
expect_contains "install shows a diff first" "$OUT" "+<!-- mempalace-shared-brain:start"
expect_missing "install without --write leaves the file alone" "$(cat "$CLAUDE_MD")" "mempalace-shared-brain"
"$SETUP" rules install --project demo --write >/dev/null
expect_contains "install appends the block" "$(cat "$CLAUDE_MD")" "mempalace-shared-brain:end -->"
expect_contains "install keeps existing content" "$(cat "$CLAUDE_MD")" "Keep this."
expect_eq "exactly one block" "$(grep -c 'mempalace-shared-brain:start' "$CLAUDE_MD")" "1"
"$SETUP" rules check --project demo >/dev/null; expect_eq "check: current exits 0" "$?" "0"
OUT="$("$SETUP" rules install --project demo --write)"
expect_contains "second install is a no-op" "$OUT" "already current"
sed -i 's/impersonate another agent/impersonate anybody/' "$CLAUDE_MD"
"$SETUP" rules check --project demo >/dev/null; expect_eq "check: edited block exits 4 (stale)" "$?" "4"
"$SETUP" rules install --project demo --write >/dev/null
expect_contains "install replaces a stale block in place" "$(cat "$CLAUDE_MD")" "impersonate another agent"
expect_eq "still exactly one block after replace" "$(grep -c 'mempalace-shared-brain:start' "$CLAUDE_MD")" "1"
expect_contains "previous file saved" "$(ls "$TMP/state/rules")" "CLAUDE.md."

echo "# session start, no transport"
"$SETUP" init --project-example demo >/dev/null
OUT="$(echo '{"session_id":"t1","source":"startup","cwd":"/tmp/demo"}' | "$SS" | context_of)"
expect_contains "identity composed from cwd" "$OUT" "Identity for this session: office-desktop:claude:demo"
expect_contains "diary-safe name offered" "$OUT" "Diary agent_name: office-desktop_claude_demo"
expect_eq "identity --diary prints the diary form" "$("$SETUP" identity --diary --cwd /tmp/demo)" "office-desktop_claude_demo"
expect_contains "rules block reported current" "$OUT" "it is current"
expect_contains "wake-up points at mempalace_status" "$OUT" "call mempalace_status first"
expect_contains "declared-idle posture" "$OUT" "declared-idle"
expect_contains "no cursor yet" "$OUT" "none recorded yet"
expect_contains "no transport: model asked to sweep" "$OUT" "Inbox sweep (the hook has no path"
expect_missing "no protocol restatement" "$OUT" "Quote results verbatim"
rm -f "$CLAUDE_MD"
OUT="$(echo '{"session_id":"t1","source":"startup","cwd":"/tmp/demo"}' | "$SS" | context_of)"
expect_contains "missing block reported" "$OUT" "has NO mempalace-shared-brain block"
"$SETUP" rules install --project demo --write >/dev/null

echo "# cursor"
"$SETUP" cursor set bogus >/dev/null 2>&1; expect_eq "bad cursor rejected" "$?" "1"
"$SETUP" cursor set evt_02_task_acked >/dev/null
expect_eq "cursor stored" "$("$SETUP" cursor get)" "evt_02_task_acked"
OUT="$(echo '{"session_id":"t1","source":"startup","cwd":"/tmp/demo"}' | "$SS" | context_of)"
expect_contains "cursor shown at session start" "$OUT" "last event id processed): evt_02_task_acked"
"$SETUP" cursor clear >/dev/null
expect_eq "cursor cleared" "$("$SETUP" cursor get)" ""

echo "# transcript fixture"
"$PY" - "$TMP/transcript.jsonl" <<'PYEOF'
import json, sys
out = open(sys.argv[1], "w")
def w(obj): out.write(json.dumps(obj) + "\n")
ts = "2026-10-04T01:00:00.000Z"
for i in range(17):
    w({"type": "user", "timestamp": ts, "message": {"role": "user", "content": "human turn %d" % i}})
    w({"type": "assistant", "timestamp": ts, "message": {"role": "assistant", "content": [
        {"type": "text", "text": "reply %d" % i}, {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}})
    w({"type": "user", "timestamp": ts, "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": "listing"}]}})
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
expect_eq "counter sees 18 human turns" "$COUNT" "18"

echo "# stop checkpoint"
PAYLOAD="{\"session_id\":\"t1\",\"transcript_path\":\"$TMP/transcript.jsonl\",\"cwd\":\"/tmp/demo\",\"stop_hook_active\":false}"
OUT="$(echo "$PAYLOAD" | "$STOP")"
expect_contains "first stop at 18 turns blocks" "$OUT" '"decision": "block"'
expect_contains "reason uses MemPalace's own wording" "$OUT" "MemPalace auto-save checkpoint."
expect_contains "reason names the identity" "$OUT" "office-desktop:claude:demo"
expect_contains "reason gives a diary-safe name" "$OUT" "office-desktop_claude_demo as the diary agent_name"
expect_eq "re-run does not fire again" "$(echo "$PAYLOAD" | "$STOP")" "{}"
expect_eq "stop_hook_active passes through" "$(echo '{"session_id":"t1","stop_hook_active":true}' | "$STOP")" "{}"
"$SETUP" set checkpoint.save_interval 0 >/dev/null; rm -f "$TMP/state/t1_last_save"
expect_eq "save_interval 0 disables the checkpoint" "$(echo "$PAYLOAD" | "$STOP")" "{}"
"$SETUP" set checkpoint.save_interval 15 >/dev/null

echo "# precompact snapshot and handoff"
expect_eq "precompact never blocks" "$(echo "{\"session_id\":\"t1\",\"transcript_path\":\"$TMP/transcript.jsonl\",\"trigger\":\"auto\"}" | "$PRE")" "{}"
[ -s "$TMP/state/pending/t1.md" ] && ok "pending snapshot written" || bad "pending snapshot written"
expect_eq "snapshot is private" "$(stat -c %a "$TMP/state/pending/t1.md")" "600"
OUT="$(echo '{"session_id":"t1","source":"compact","cwd":"/tmp/demo"}' | "$SS" | context_of)"
expect_contains "post-compact handoff names the pending file" "$OUT" "snapshotted them to"
expect_missing "probe skipped after compaction" "$OUT" "Live check"

echo "# http hub: probe, cursor, inbox"
start_hub --token test-token
"$SETUP" init --transport http --url "http://127.0.0.1:$PORT/mcp" --token-env MEMPALACE_TEST_TOKEN >/dev/null
OUT="$(MEMPALACE_TEST_TOKEN=test-token "$SETUP" probe 2>&1)"
expect_contains "probe reaches the hub via healthz and mcp" "$OUT" "hub reachable, MemPalace 9.9.9-fake, 1234 drawers"
expect_contains "probe counts open vs unacked" "$OUT" "3, of which 2 have no ack"
expect_contains "unacked listed" "$OUT" "  - evt_01_task_unacked"
expect_contains "unmeetable requirement flagged" "$OUT" "THIS MACHINE CANNOT MEET: xcode>=99"
expect_contains "Requires line read from the body" "$OUT" "requires python; this machine meets it"
expect_missing "acked task not listed" "$OUT" "  - evt_02_task_acked"
expect_missing "other agent's task not listed" "$OUT" "evt_05_not_mine"
"$SETUP" cursor set evt_04_broadcast >/dev/null
OUT="$(MEMPALACE_TEST_TOKEN=test-token "$SETUP" probe 2>&1)"
expect_contains "events since cursor reported" "$OUT" "since your cursor evt_04_broadcast: 3:"
expect_contains "reply since cursor listed" "$OUT" "evt_06_reply_blocked  task.reply blocked"
"$SETUP" cursor clear >/dev/null
OUT="$(env -u MEMPALACE_TEST_TOKEN "$SETUP" probe 2>&1)"; RC=$?
expect_contains "missing token reports 401" "$OUT" "HTTP 401"
expect_eq "probe exits 1 when unreachable" "$RC" "1"
OUT="$(MEMPALACE_TEST_TOKEN=test-token sh -c "echo '{\"session_id\":\"t3\",\"source\":\"startup\",\"cwd\":\"/tmp/demo\"}' | '$SS'" | context_of)"
expect_contains "session-start carries the live check" "$OUT" "Live check (http"
"$SETUP" init --token-env "" --token-command "printf test-token" >/dev/null
expect_contains "token_command path works" "$("$SETUP" probe 2>&1)" "hub reachable"

echo "# http hub: listen and wake"
expect_eq "wake while disarmed is silent" "$(echo '{"session_id":"t3","cwd":"/tmp/demo","prompt":"hi"}' | "$WAKE")" "{}"
OUT="$("$SETUP" listen arm --from evt_02_task_acked)"
expect_contains "arm reports the filter" "$OUT" "types task.request, task.reply, patch.ready"
expect_contains "arm prints the announcement" "$OUT" "is MONITORING for coordination replies"
OUT="$(echo '{"session_id":"t3","cwd":"/tmp/demo","prompt":"hi"}' | "$WAKE" | context_of)"
expect_contains "wake reports matches" "$OUT" "MEMPALACE WAKE: 2 coordination events"
expect_contains "wake includes the broadcast request" "$OUT" "evt_04_broadcast"
expect_contains "wake includes the blocked reply" "$OUT" "evt_06_reply_blocked"
expect_missing "wake excludes own events" "$OUT" "evt_08_my_broadcast  status"
expect_missing "wake excludes other agents' status" "$OUT" "evt_07_status_other"
expect_contains "watch cursor advanced past everything examined" "$OUT" "Watch cursor is now evt_08_my_broadcast"
expect_eq "second wake is silent" "$(echo '{"session_id":"t3","cwd":"/tmp/demo","prompt":"hi"}' | "$WAKE")" "{}"
OUT="$(echo '{"session_id":"t3","source":"startup","cwd":"/tmp/demo"}' | "$SS" | context_of)"
expect_contains "session start shows the armed watch" "$OUT" "wake check is ARMED"
OUT="$("$SETUP" listen arm)"
expect_contains "arm without --from starts at the tip" "$OUT" "watch cursor evt_08_my_broadcast"
OUT="$("$SETUP" listen disarm)"
expect_contains "disarm prints the declared-idle statement" "$OUT" "is NOT monitoring"

echo "# http hub: peers and statusz"
OUT="$("$SETUP" peers)"
expect_contains "peers returns mesh peers" "$OUT" '"name": "desktop"'
expect_contains "peers reads statusz with the token" "$OUT" '"uptime_seconds": 42'
stop_hub

echo "# http hub without writer param, sse"
start_hub --sse --no-writer
"$SETUP" init --url "http://127.0.0.1:$PORT/mcp" --token-command "" >/dev/null
OUT="$("$SETUP" probe 2>&1)"
expect_contains "sse parsed" "$OUT" "hub reachable"
expect_contains "from_agent fallback still finds own acks" "$OUT" "3, of which 2 have no ack"
stop_hub
expect_contains "dead hub reported, not raised" "$("$SETUP" probe 2>&1)" "FAILED, cannot reach"

echo "# oauth client credentials (no static token anywhere)"
start_hub --token cc-token --oauth-secret s3cret
"$SETUP" init --transport http --url "http://127.0.0.1:$PORT/mcp" --token-env "" --token-command "" >/dev/null
"$SETUP" set hub.oauth.token_url "http://127.0.0.1:$PORT/api/oidc/token" >/dev/null
"$SETUP" set hub.oauth.client_id hooks-client >/dev/null
"$SETUP" set hub.oauth.client_secret_env MP_CLIENT_SECRET >/dev/null
OUT="$(MP_CLIENT_SECRET=s3cret "$SETUP" probe 2>&1)"
expect_contains "client credentials token reaches the hub" "$OUT" "hub reachable"
[ -n "$(ls "$TMP/state/oauth" 2>/dev/null)" ] && ok "access token cached" || bad "access token cached"
expect_eq "token cache is private" "$(stat -c %a "$TMP"/state/oauth/*.json)" "600"
OUT="$(MP_CLIENT_SECRET=wrong "$SETUP" probe 2>&1)"
expect_contains "cached token still used with a wrong secret (not expired)" "$OUT" "hub reachable"
rm -f "$TMP"/state/oauth/*.json
OUT="$(MP_CLIENT_SECRET=wrong "$SETUP" probe 2>&1)"
expect_contains "wrong secret reports the token endpoint" "$OUT" "token endpoint"
expect_contains "wrong secret shows the server's error" "$OUT" "invalid_client"
"$SETUP" set hub.oauth.client_id '""' >/dev/null
"$SETUP" set hub.oauth.token_url '""' >/dev/null
stop_hub

echo "# no transport: the model makes the calls"
"$SETUP" init --transport none >/dev/null
OUT="$(echo '{"session_id":"t6","source":"startup","cwd":"/tmp/demo"}' | "$SS" | context_of)"
expect_contains "session start asks the model to sweep" "$OUT" "Inbox sweep (the hook has no path"
expect_contains "sweep names the identity" "$OUT" "to_agent=office-desktop:claude:demo, preview=true, limit=10"
"$SETUP" cursor set evt_04_broadcast >/dev/null
OUT="$(echo '{"session_id":"t6","source":"startup","cwd":"/tmp/demo"}' | "$SS" | context_of)"
expect_contains "sweep resumes from the cursor" "$OUT" "since_event_id=evt_04_broadcast"
"$SETUP" cursor clear >/dev/null
"$SETUP" set probe.model_sweep false >/dev/null
OUT="$(echo '{"session_id":"t6","source":"startup","cwd":"/tmp/demo"}' | "$SS" | context_of)"
expect_contains "model sweep can be turned off" "$OUT" "Live check: off"
"$SETUP" set probe.model_sweep true >/dev/null
"$SETUP" listen arm --from evt_02_task_acked >/dev/null
OUT="$(echo '{"session_id":"t6","cwd":"/tmp/demo","prompt":"hi"}' | "$WAKE" | context_of)"
expect_contains "wake asks the model to sweep when armed" "$OUT" "MEMPALACE WAKE CHECK"
expect_contains "wake sweep resumes from the watch cursor" "$OUT" "since_event_id=evt_02_task_acked"
"$SETUP" listen cursor evt_06_reply_blocked >/dev/null
expect_contains "listen cursor advances the watch cursor" "$("$SETUP" listen status)" '"since_event_id": "evt_06_reply_blocked"'
"$SETUP" listen cursor bogus >/dev/null 2>&1; expect_eq "listen cursor rejects a bad id" "$?" "1"
"$SETUP" listen disarm >/dev/null
expect_eq "wake silent once disarmed" "$(echo '{"session_id":"t6","cwd":"/tmp/demo","prompt":"hi"}' | "$WAKE")" "{}"

echo "# stdio"
"$SETUP" init --transport stdio --stdio-command "$PY $ROOT/tests/fake_hub.py --stdio" >/dev/null
expect_contains "stdio transport works" "$("$SETUP" probe 2>&1)" "Live check (stdio"
"$SETUP" init --stdio-command "/nonexistent/mempalace-mcp" >/dev/null
expect_contains "stdio start failure reported" "$("$SETUP" probe 2>&1)" "cannot start"
"$SETUP" init --transport none >/dev/null
OUT="$("$SETUP" listen arm)"
expect_contains "arm with no transport says the model will sweep" "$OUT" "no transport to the hub"
"$SETUP" listen disarm >/dev/null

echo "# capabilities"
OUT="$("$SETUP" capabilities probe)"
expect_contains "probe names the host" "$OUT" "host office-desktop, probe hash"
expect_contains "probe lists python" "$OUT" "python"
"$SETUP" capabilities check python "memory-gb>=1" >/dev/null; expect_eq "check met exits 0" "$?" "0"
OUT="$("$SETUP" capabilities check python "memory-gb>=99999" "no-such-tool")"; RC=$?
expect_eq "check unmet exits 3" "$RC" "3"
expect_contains "check names a version shortfall" "$OUT" "memory-gb>=99999 (have"
expect_contains "check names a missing tool" "$OUT" '"no-such-tool"'
"$SETUP" capabilities status >/dev/null; expect_eq "status before publish exits 3" "$?" "3"
expect_contains "status says never published" "$("$SETUP" capabilities status)" '"state": "never-published"'
OUT="$(echo '{"session_id":"t7","source":"startup","cwd":"/tmp/demo"}' | "$SS" | context_of)"
expect_contains "session start nudges an unpublished machine" "$OUT" "have never been published to the hub"
PLAN="$("$SETUP" capabilities plan)"
expect_contains "plan carries kg facts" "$PLAN" '"predicate": "has_capability"'
expect_contains "plan carries the profile text" "$PLAN" "Search terms: office-desktop capabilities"
expect_eq "fact objects fit the kg limit" "$(echo "$PLAN" | "$PY" -c 'import json,sys; print(max(len(f["object"]) for f in json.load(sys.stdin)["facts"]) <= 128)')" "True"
HASH="$(echo "$PLAN" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["probe_hash"])')"
"$SETUP" capabilities published "$HASH" drawer_fleet_machines_abc >/dev/null
"$SETUP" capabilities status >/dev/null; expect_eq "status after publish exits 0" "$?" "0"
expect_contains "config keeps the profile drawer id" "$("$SETUP" show)" "drawer_fleet_machines_abc"
OUT="$(echo '{"session_id":"t7","source":"startup","cwd":"/tmp/demo"}' | "$SS" | context_of)"
expect_contains "session start reports a current profile" "$OUT" "(published, profile drawer drawer_fleet_machines_abc)"
"$SETUP" set capabilities.custom '{"always-there": "true", "never-there": "false", "noisy": "echo SECRETVALUE"}' >/dev/null
OUT="$("$SETUP" capabilities probe)"
expect_missing "custom check output never published" "$("$SETUP" capabilities plan)" "SECRETVALUE"
expect_contains "custom check present" "$OUT" "always-there       yes (custom check)"
expect_contains "custom check absent" "$OUT" "never-there        no"
expect_contains "status sees the custom change" "$("$SETUP" capabilities status)" '"state": "changed"'
"$SETUP" set capabilities.enabled false >/dev/null
OUT="$(echo '{"session_id":"t7","source":"startup","cwd":"/tmp/demo"}' | "$SS" | context_of)"
expect_missing "capabilities line can be turned off" "$OUT" "Capabilities of host"
"$SETUP" set capabilities.enabled true >/dev/null
OUT="$("$PY" -c "
import sys; sys.path.insert(0, '$ROOT/hooks/lib'); import capabilities as K
print(K.requires_of({'metadata': {'requires': 'a, b>=2'}}), K.requires_of({'body': 'x\\nRequires: c d'}), K.requires_of({}))
r = {'capabilities': {'xcode': {'present': True, 'version': '27.1'}}}
print(K.check_requirements(r, ['xcode>=27', 'xcode>27.1', 'xcode=27', 'xcode<27', 'bad req!!']))")"
expect_contains "requires parsed from metadata string" "$OUT" "['a', 'b>=2']"
expect_contains "requires parsed from a body line" "$OUT" "['c', 'd']"
expect_contains "version comparisons" "$OUT" "(['xcode>=27', 'xcode=27'], ['xcode>27.1 (have 27.1)', 'xcode<27 (have 27.1)', 'bad req!! (unreadable requirement)'])"

XA="$TMP/Applications"; mkdir -p "$XA/Xcode-beta.app/Contents" "$XA/Xcode_26.app/Contents"
"$PY" -c "
import plistlib
plistlib.dump({'CFBundleShortVersionString': '27.1', 'ProductBuildVersion': '27A9269'}, open('$XA/Xcode-beta.app/Contents/version.plist', 'wb'))
plistlib.dump({'CFBundleShortVersionString': '26.4', 'ProductBuildVersion': '26E240d'}, open('$XA/Xcode_26.app/Contents/version.plist', 'wb'))"
OUT="$("$PY" -c "
import sys, platform; sys.path.insert(0, '$ROOT/hooks/lib'); import capabilities as K
K.APPLICATIONS = '$XA'; platform.system = lambda: 'Darwin'
x, b = K.probe_xcode()
print(x['present'], x.get('version'), b['present'], b.get('version'), [a['app'] for a in b['detail']['apps']])")"
expect_contains "beta-named bundle still counts as xcode" "$OUT" "True 27.1 True 27.1"
expect_contains "letter-suffixed release build is not a beta" "$OUT" "['Xcode-beta.app']"

OUT="$(echo '{"session_id":"m0","source":"startup","cwd":"/tmp/demo/some/subdir"}' | "$SS" | context_of)"
expect_contains "identity follows the project root, not a shell cd" "$OUT" "Identity for this session: office-desktop:claude:demo"

OUT="$("$SETUP" peers)"; RC=$?
expect_eq "peers without a transport is not an error" "$RC" "0"
expect_contains "peers without a transport says what to do" "$OUT" "call mempalace_mesh_peers through the session's MCP tools"

expect_eq "presence empty at first" "$("$SETUP" presence get)" ""
"$SETUP" presence set drawer_fleet_presence_abc >/dev/null
expect_eq "presence remembers the drawer" "$("$SETUP" presence get)" "drawer_fleet_presence_abc"
expect_contains "mod-context carries the presence drawer" "$("$SETUP" mod-context --cwd /tmp/demo)" '"drawer_id": "drawer_fleet_presence_abc"'
"$SETUP" presence set "not a drawer" >/dev/null 2>&1; expect_eq "presence rejects a bad id" "$?" "1"
"$SETUP" presence clear >/dev/null
expect_eq "presence clear" "$("$SETUP" presence get)" ""

echo "# mod"
"$SETUP" init --transport none >/dev/null
OUT="$("$SETUP" mod-context --cwd /tmp/demo)"
expect_contains "mod-context names the identity" "$OUT" '"identity": "office-desktop:claude:demo"'
expect_contains "mod-context carries capabilities" "$OUT" '"python": {"present": true'
expect_contains "mod-context carries the server setting" "$OUT" '"mcp_server": ""'
OUT="$(echo '{"session_id":"m1","source":"startup","cwd":"/tmp/demo","mempalace_sharedbrain_mod":"active"}' | "$SS" | context_of)"
expect_contains "session start keeps its block under the mod" "$OUT" "Identity for this session: office-desktop:claude:demo"
expect_missing "session start leaves the sweep to the mod" "$OUT" "Inbox sweep (the hook has no path"
"$SETUP" listen arm >/dev/null
expect_eq "wake stands down under the mod" "$(echo '{"session_id":"m1","cwd":"/tmp/demo","prompt":"hi","mempalace_sharedbrain_mod":"active"}' | "$WAKE")" "{}"
expect_contains "wake still runs without the mod" "$(echo '{"session_id":"m1","cwd":"/tmp/demo","prompt":"hi"}' | "$WAKE" | context_of)" "MEMPALACE WAKE CHECK"
"$SETUP" listen disarm >/dev/null

echo "# bridge"
rm -f "$TMP/state/watch/"*.json
OUT="$("$SETUP" mod-context --cwd /tmp/demo)"
expect_contains "the bridge reads by default" "$OUT" '"mode": "read"'
"$SETUP" set bridge.mode bogus >/dev/null 2>&1; expect_eq "set refuses an unknown mode" "$?" "1"
"$PY" -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); d.setdefault("bridge",{})["mode"]="bogus"; json.dump(d,open(p,"w"))' "$TMP/config.json"
expect_contains "an unknown mode fails closed to read" "$("$SETUP" mod-context --cwd /tmp/demo)" '"mode": "read"'
"$SETUP" set bridge.mode act >/dev/null
expect_contains "the bridge arms listening" "$OUT" '"auto": true'
"$SETUP" listen disarm >/dev/null
expect_contains "a disarm sticks" "$("$SETUP" mod-context --cwd /tmp/demo)" '"disarmed": true'
"$SETUP" listen arm >/dev/null
expect_eq "first claim wins" "$("$SETUP" bridge claim evt_a --owner s1; echo $?)" "$(printf 'claimed\n0')"
expect_eq "same owner keeps it" "$("$SETUP" bridge claim evt_a --owner s1 >/dev/null; echo $?)" "0"
expect_eq "another session loses it" "$("$SETUP" bridge claim evt_a --owner s2 >/dev/null; echo $?)" "3"
"$SETUP" bridge turn -- "--cwd" >/dev/null 2>&1; expect_eq "an id that looks like an option is refused" "$?" "1"
"$SETUP" set bridge.max_turns_per_thread 2 >/dev/null
expect_contains "turn 1 of 2" "$("$SETUP" bridge turn task_x)" '"task_x": {"turns": 1, "is_last": false}'
expect_contains "turn 2 is the last" "$("$SETUP" bridge turn task_x)" '"task_x": {"turns": 2, "is_last": true}'
expect_contains "a paused thread starts no turn" "$("$SETUP" bridge turn task_x)" '"reason": "paused"'
expect_contains "mod-context lists the paused thread" "$("$SETUP" mod-context --cwd /tmp/demo)" '"paused": ["task_x"]'
expect_contains "continue resumes it" "$("$SETUP" bridge continue task_x)" "continuing task_x"
expect_contains "after continue it counts from one" "$("$SETUP" bridge turn task_x)" '"turns": 1'
"$SETUP" set bridge.max_turns_per_hour 2 >/dev/null
"$SETUP" bridge turn task_y >/dev/null
expect_contains "the hourly limit holds" "$("$SETUP" bridge turn task_z)" '"reason": "hourly limit"'
OUT="$("$PY" - "$ROOT/hooks/lib" <<'PYEOF'
import sys; sys.path.insert(0, sys.argv[1])
import sb_probe as P
named = {"id": "evt_n", "from_agent": "s:claude:a", "to_agent": "me:claude:b", "correlation_id": "t_n"}
cast = {"id": "evt_b", "from_agent": "s:claude:a", "to_agent": "*"}
ack = lambda by, of: {"type": "event.ack", "status": "applied", "from_agent": by, "metadata": {"ack_of": of}}
print(sorted(P.closed_tasks([ack("x:claude:z", "evt_n")], [named], "me:claude:b")[0]),
      sorted(P.closed_tasks([ack("s:claude:a", "evt_n")], [named], "me:claude:b")[0]),
      sorted(P.closed_tasks([ack("x:claude:z", "evt_b")], [cast], "me:claude:b")[0]))
PYEOF
)"
expect_eq "closures count only from sender, addressee or self; anyone for a broadcast" "$OUT" "[] ['evt_n'] ['evt_b']"

"$PY" -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); d.setdefault("bridge",{}).pop("sign_tasks",None); json.dump(d,open(p,"w"))' "$TMP/config.json"
expect_contains "signing asks once per recipient by default" "$("$SETUP" bridge status)" '"sign_tasks": "session"'
"$SETUP" set bridge.sign_tasks always >/dev/null 2>&1; expect_eq "set refuses an unknown signing setting" "$?" "1"
"$PY" -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); d["bridge"]["sign_tasks"]="sometimes"; json.dump(d,open(p,"w"))' "$TMP/config.json"
expect_contains "an unknown signing setting fails closed to ask" "$("$SETUP" bridge status)" '"sign_tasks": "ask"'
"$SETUP" set bridge.sign_tasks session >/dev/null

echo "# signing and pairing"
if command -v ssh-keygen >/dev/null; then
  KEYINFO="$("$SETUP" sign show)"
  expect_contains "a bridge key is created" "$KEYINFO" '"available": true'
  expect_eq "the key is private" "$(stat -c %a "$TMP/bridge_ed25519")" "600"
  expect_contains "this machine trusts its own key" "$(cat "$TMP/trusted_signers")" 'office-desktop:* namespaces="mempalace-bridge" ssh-ed25519'
  SIG="$(printf '%s' '{"from":"office-desktop:claude:demo","to":"mac:claude:app","type":"task.request","correlation":"t1","body":"go  \ncafé"}' | "$SETUP" sign make --cwd /tmp/demo)"
  mkev() { "$PY" -c "import json,sys; e={'id':'evt_s1','from_agent':'office-desktop:claude:demo','to_agent':'mac:claude:app','type':'task.request','correlation_id':'t1','body':'go  \ncafé','metadata':{'bridge_sig':json.loads(sys.argv[1])}}; $1; print(json.dumps(e))" "$SIG"; }
  expect_contains "a signed event verifies" "$(mkev pass | "$SETUP" sign verify)" '"ok": true'
  expect_contains "the fingerprint shown is the verifying key's" "$(mkev "e['metadata']['bridge_sig']['key']='SHA256:FAKE'" | "$SETUP" sign verify)" "$(echo "$KEYINFO" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["fingerprint"])')"
  expect_contains "a changed body fails" "$(mkev "e['body']+='!'" | "$SETUP" sign verify)" '"ok": false'
  expect_contains "another recipient fails" "$(mkev "e['to_agent']='x:claude:y'" | "$SETUP" sign verify)" '"ok": false'
  expect_contains "a replay on another event fails" "$(mkev "e['id']='evt_s2'" | "$SETUP" sign verify)" "replayed signature"
  expect_contains "an old signature fails" "$(mkev "e['metadata']['bridge_sig']['signed_at']='2026-01-01T00:00:00Z'" | "$SETUP" sign verify)" "older than 14 days"
  expect_contains "unsigned is reported" "$(mkev "e['metadata']={}" | "$SETUP" sign verify)" '"unsigned"'
  printf '%s' '{"from":"other-host:claude:x","to":"a","type":"task.request"}' | "$SETUP" sign make --cwd /tmp/demo >/dev/null 2>&1
  expect_eq "it signs only for this machine's identities" "$?" "1"
  # A second machine, with its own config, pairs with this one.
  OTHER="$TMP/other.json"; MEMPALACE_SHAREDBRAIN_CONFIG="$OTHER" "$SETUP" init --host mac --transport none >/dev/null
  OFFER="$(MEMPALACE_SHAREDBRAIN_CONFIG="$OTHER" CLAUDE_PROJECT_DIR=/tmp/app "$SETUP" trust offer --cwd /tmp/app)"
  CODE="$(echo "$OFFER" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["code"])')"
  expect_missing "the code is not in the hub request" "$(echo "$OFFER" | "$PY" -c 'import json,sys;print(json.dumps(json.load(sys.stdin)["offer"]))')" "$CODE"
  OFFERS="$(echo "$OFFER" | "$PY" -c 'import json,sys;o=json.load(sys.stdin)["offer"];print(json.dumps([{"id":"evt_p","type":"bridge.pair","from_agent":o["identity"],"metadata":{"bridge_pair":o}}]))')"
  echo "$OFFERS" | "$SETUP" trust accept "$(printf %06d $(( (10#$CODE + 1) % 1000000 )))" >/dev/null 2>&1
  expect_eq "a wrong code pairs nothing" "$?" "1"
  expect_contains "the right code pairs" "$(echo "$OFFERS" | "$SETUP" trust accept "$CODE")" "for mac:*"
  expect_contains "the paired key is trusted for its host" "$("$SETUP" trust list)" '"principal": "mac:*"'
  echo "x" | "$SETUP" trust approve mac:claude:app >/dev/null 2>&1
  expect_eq "approve without a fingerprint is refused" "$?" "1"
  expect_contains "revoke" "$("$SETUP" trust revoke 'mac:*')" "revoked 1 key"
  # A plain ssh-agent stands in for 1Password's: same socket protocol, keys named by comment.
  AG="$(mktemp -d /tmp/sbag.XXXX)"; mkdir -p "$TMP/agent"; AGCFG="$TMP/agent/config.json"
  eval "$(ssh-agent -a "$AG/s")" >/dev/null
  agent() { MEMPALACE_SHAREDBRAIN_CONFIG="$AGCFG" MEMPALACE_SHAREDBRAIN_AGENT_SOCK="$AG/s" "$SETUP" "$@"; }
  MEMPALACE_SHAREDBRAIN_CONFIG="$AGCFG" "$SETUP" init --host agenthost --transport none >/dev/null
  expect_contains "without a 1Password key it falls back to a file, with a warning" "$(agent sign show)" '"source": "file"'
  expect_contains "the fallback warns that a session could sign without asking" "$(agent sign show)" "could sign without asking"
  MEMPALACE_SHAREDBRAIN_CONFIG="$AGCFG" "$SETUP" set bridge.key_source 1password >/dev/null
  expect_contains "key_source 1password never uses a file" "$(agent sign show)" '"available": false'
  MEMPALACE_SHAREDBRAIN_CONFIG="$AGCFG" "$SETUP" set bridge.key_source auto >/dev/null
  ssh-keygen -q -t ed25519 -N "" -C "MemPalace bridge agenthost" -f "$AG/k" && SSH_AUTH_SOCK="$AG/s" ssh-add -q "$AG/k" && rm -f "$AG/k"
  expect_contains "the key named for this machine in the agent is used" "$(agent sign show)" '"source": "1password"'
  expect_eq "the old key file is removed" "$(ls "$TMP/agent" | grep -c "^bridge_ed25519")" "0"
  ASIG="$(printf '%s' '{"from":"agenthost:claude:demo","to":"x:claude:y","type":"task.request","correlation":"c1","body":"hi"}' | agent sign make --cwd /tmp/demo)"
  expect_contains "it signs through the agent" "$("$PY" -c "import json,sys; print(json.dumps({'id':'ea','from_agent':'agenthost:claude:demo','to_agent':'x:claude:y','type':'task.request','correlation_id':'c1','body':'hi','metadata':{'bridge_sig':json.loads(sys.argv[1])}}))" "$ASIG" | agent sign verify)" '"ok": true'
  kill "$SSH_AGENT_PID"
  expect_contains "with the agent gone it does not fall back to a file" "$(agent sign show)" '"available": false'
  expect_eq "and still no key file" "$(ls "$TMP/agent" | grep -c "^bridge_ed25519")" "0"
  rm -rf "$AG"
else
  ok "ssh-keygen absent: signing checks skipped"
fi

echo "# permissions"
expect_eq "state dir private" "$(stat -c %a "$TMP/state")" "700"
expect_eq "config private" "$(stat -c %a "$TMP/config.json")" "600"

rm -rf "$ROOT"/hooks/lib/__pycache__ "$ROOT"/tests/__pycache__
echo
echo "passed $PASS, failed $FAIL"
[ "$FAIL" -eq 0 ]
