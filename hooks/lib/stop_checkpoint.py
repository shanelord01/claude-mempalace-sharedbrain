"""Stop hook body.

Counts the genuine human turns in the transcript and, once save_interval
new ones have passed since the last checkpoint, blocks the stop once with a
reason asking the model to file the session's durable outcomes. Claude Code
then calls the hook again with stop_hook_active=true and the hook lets the
stop through, so this never loops.

Claude Code displays a blocking Stop hook as "Stop hook error" followed by
the reason. That is its label for any block, not a failure.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import sb_common as C  # noqa: E402
import sb_transcript as T  # noqa: E402

REASON = (
    "MEMPALACE CHECKPOINT. File this session's durable outcomes so far to the palace with the "
    "mempalace MCP tools: decisions, conclusions, learned facts, verbatim quotes and code worth "
    "keeping. Run mempalace_check_duplicate before filing a rule or preference, then "
    "mempalace_add_drawer with a purpose line phrased as the problem someone would search for plus a "
    "'Search terms:' line. Record changed facts with mempalace_kg_add, and use mempalace_kg_supersede "
    "rather than stacking a contradictory fact. Write a short mempalace_diary_write entry in AAAK. "
    "Set from_agent / added_by to %s. Then continue the conversation."
)


def main():
    C.rotate_log()
    payload = C.read_hook_input()
    if payload.get("stop_hook_active") in (True, "true", "True"):
        C.emit({})
        return

    cfg = C.load_config()
    agent = C.agent_id(cfg)
    interval = int(cfg["checkpoint"].get("save_interval") or 0)
    if interval <= 0:
        C.emit({})
        return

    session_id = C.safe_id(payload.get("session_id"))
    transcript = os.path.expanduser(str(payload.get("transcript_path") or ""))
    count = 0
    if transcript and os.path.isfile(transcript):
        try:
            count = T.count_human_turns(transcript)
        except OSError as exc:
            C.log("STOP session %s: transcript unreadable: %s" % (session_id, exc))

    C.ensure_dirs()
    last_file = os.path.join(C.STATE_DIR, "%s_last_save" % session_id)
    last = 0
    try:
        with open(last_file) as fh:
            last = int(fh.read().strip() or 0)
    except (OSError, ValueError):
        pass

    since = count - last
    if since < 0:
        # A stale state file from another counter would keep the delta negative for ever.
        with open(last_file, "w") as fh:
            fh.write(str(count))
        C.log("STOP session %s: re-baselined stale count to %d" % (session_id, count))
        C.emit({})
        return

    if count > 0 and since >= interval:
        with open(last_file, "w") as fh:
            fh.write(str(count))
        C.log("STOP session %s: checkpoint at %d human turns (%d since last)" % (session_id, count, since))
        C.emit({"decision": "block", "reason": REASON % agent})
        return

    C.emit({})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # fail open
        C.log("STOP crashed: %s: %s" % (type(exc).__name__, exc))
        C.emit({})
