"""Stop hook body.

The MemPalace plugin's own Stop hook saves the transcript through the local
package. A client whose only palace is a remote hub has no package and no
local palace, so this hook does what MemPalace's hook does in its legacy
(blocking) mode: every save_interval human turns it blocks the stop once and
asks the model to save through the MCP tools, using MemPalace's own wording.
Claude Code then calls the hook again with stop_hook_active=true and the stop
goes through, so this never loops.

Claude Code displays a blocking Stop hook as "Stop hook error" followed by
the reason. That is its label for any block, not a failure.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import sb_common as C  # noqa: E402
import sb_transcript as T  # noqa: E402

# Verbatim from mempalace/hooks_cli.py (STOP_BLOCK_REASON), followed by the
# one-call alternative the server offers and this session's identity.
REASON = (
    "MemPalace auto-save checkpoint. "
    "Use mempalace_diary_write (session summary) and mempalace_add_drawer "
    "(quotes, decisions, code) to save session content. "
    "Do NOT use native auto-memory files. "
    "mempalace_checkpoint does both in one call. Use %s as from_agent / added_by and %s as the diary agent_name. "
    "Then continue the conversation."
)


def main():
    C.rotate_log()
    payload = C.read_hook_input()
    if payload.get("stop_hook_active") in (True, "true", "True"):
        C.emit({})
        return

    cfg = C.load_config()
    interval = int(cfg["checkpoint"].get("save_interval") or 0)
    if interval <= 0:
        C.emit({})
        return

    cwd = str(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    ident = C.identity(cfg, cwd)
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
        with C.open_private(last_file, "w") as fh:
            fh.write(str(count))
        C.log("STOP session %s: re-baselined stale count to %d" % (session_id, count))
        C.emit({})
        return

    if count > 0 and since >= interval:
        with C.open_private(last_file, "w") as fh:
            fh.write(str(count))
        C.log("STOP session %s: checkpoint at %d human turns (%d since last)" % (session_id, count, since))
        C.emit({"decision": "block", "reason": REASON % (ident, C.diary_name(ident))})
        return

    C.emit({})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # fail open
        C.log("STOP crashed: %s: %s" % (type(exc).__name__, exc))
        C.emit({})
