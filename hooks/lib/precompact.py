"""PreCompact hook body.

Extracts the human prompts, assistant replies and tool names since the last
snapshot into a pending file for this session, and records the transcript
line reached. Prints {} whatever happens: a PreCompact hook that blocks only
cancels the compaction, the model never sees the reason, and the session
dies on the next request with a context-length error.

The SessionStart hook hands the pending file to the model after the
compaction.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import sb_common as C  # noqa: E402
import sb_transcript as T  # noqa: E402


def main():
    payload = C.read_hook_input()
    session_id = C.safe_id(payload.get("session_id"))
    trigger = str(payload.get("trigger") or "unknown")
    transcript = os.path.expanduser(str(payload.get("transcript_path") or ""))
    C.ensure_dirs()

    if not transcript or not os.path.isfile(transcript):
        C.log("PRE-COMPACT %s session %s: no transcript at %r, nothing snapshotted" % (trigger, session_id, transcript))
        return

    marker = os.path.join(C.STATE_DIR, "%s_snapshot_line" % session_id)
    start = 0
    try:
        with open(marker) as fh:
            start = int(fh.read().strip() or 0)
    except (OSError, ValueError):
        pass

    text, n_lines = T.snapshot_since(transcript, start)
    if not text.strip():
        C.log("PRE-COMPACT %s session %s: nothing new since line %d" % (trigger, session_id, start))
        return

    path = os.path.join(C.PENDING_DIR, "%s.md" % session_id)
    header = T.snapshot_header(session_id, trigger, transcript, start, n_lines)
    with C.open_private(path, "a" if os.path.exists(path) else "w") as fh:
        fh.write(header + text + "\n")
    with C.open_private(marker, "w") as fh:
        fh.write(str(n_lines))
    C.log("PRE-COMPACT %s session %s: snapshot lines %d-%d (%d chars) -> %s" % (
        trigger, session_id, start, n_lines, len(text), path))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        C.log("PRE-COMPACT crashed: %s: %s" % (type(exc).__name__, exc))
    finally:
        C.emit({})
