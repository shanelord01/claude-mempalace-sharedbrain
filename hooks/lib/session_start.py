"""SessionStart hook body.

Puts the facts a shared-brain client needs in front of the model before the
first prompt: this session's identity, whether the canonical rules block in
the instruction file is current, the wake-up step the Memory Protocol asks
for, the inbox cursor, the session's monitoring posture, a live check of the
hub when the hook has a transport, and any pre-compaction snapshot waiting
to be filed. It restates no protocol: the rules block in CLAUDE.md and the
hub's own Memory Protocol do that.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import sb_common as C  # noqa: E402
import sb_probe as P  # noqa: E402
import rules as R  # noqa: E402

TOOL_NOTE = (
    "The hub is reached through the mempalace_* MCP tools. Your client may list them under a server "
    "prefix (mcp__mempalace__, mcp__claude_ai_Mempalace__, mcp__plugin_mempalace_mempalace__). If no "
    "mempalace tools are present in this session, say so. Never answer as if you had checked."
)


def identity_line(cfg, ident, cwd):
    if cfg["identity"].get("fixed"):
        note = "" if C.identity_is_canonical(ident) else " (a fixed id from this machine's config, outside the canonical host:harness:project form)"
        return "Identity for this session: %s%s." % (ident, note)
    return "Identity for this session: %s (host:harness:project, project taken from the workspace %s)." % (ident, cwd or os.getcwd())


def rules_line(cfg):
    try:
        rendered, source = R.render(cfg)
        path = R.target_path(cfg)
        try:
            with open(path, encoding="utf-8") as fh:
                current = fh.read()
        except FileNotFoundError:
            current = ""
        status = R.check(current, rendered)
    except Exception as exc:  # never block the session on a rendering problem
        return "Rules block: could not be checked (%s)." % C.clean_line(exc, 120)
    where = "the installed mempalace CLI" if source == "cli" else "the plugin's vendored MemPalace template"
    if status == "current":
        return "Rules block: %s carries the canonical MemPalace shared-brain block and it is current (checked against %s). Follow it." % (path, where)
    if status == "stale":
        return ("Rules block: %s carries a shared-brain block that differs from the canonical render (%s). Tell the user and "
                "offer /mempalace-sharedbrain:rules to update it in place. Follow the installed block meanwhile." % (path, where))
    return ("Rules block: %s has NO mempalace-shared-brain block. Tell the user and offer /mempalace-sharedbrain:rules to "
            "install the canonical one. Until then, read the hub's protocol from mempalace_status and work from that." % path)


def posture_lines(cfg, ident):
    lines = []
    cursor = C.read_cursor(ident)
    watch = C.read_watch(ident)
    if watch.get("armed"):
        lines.append("Posture: a wake check is ARMED for %s. Each of the user's prompts triggers a sweep of events since "
                     "the watch cursor %s for types %s%s; matches are placed in your context. Re-announce only if the "
                     "filter changes." % (ident, watch.get("since_event_id") or "(start)", ", ".join(watch.get("types") or []),
                                          (" on correlation %s" % watch["correlation_id"]) if watch.get("correlation_id") else ""))
    else:
        lines.append("Posture: this session is turn-based and declared-idle (no background watcher). "
                     "/mempalace-sharedbrain:listen arms a per-prompt wake check when a coordination loop starts.")
    if cursor:
        lines.append("Inbox cursor for %s (last event id processed): %s. Resume sweeps from it with since_event_id; "
                     "record a new one with `bash \"${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh\" cursor set <event id>`." % (ident, cursor))
    else:
        lines.append("Inbox cursor for %s: none recorded yet. After your first sweep, record the last event id you processed "
                     "with `bash \"${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh\" cursor set <event id>`." % ident)
    return lines, cursor


def pending_handoff(session_id):
    path = os.path.join(C.PENDING_DIR, "%s.md" % session_id)
    try:
        size = os.path.getsize(path)
    except OSError:
        return ""
    if size == 0:
        return ""
    return (
        "MEMPALACE: the conversation was just compacted or resumed and the exchanges since the last palace "
        "save were NOT filed. The PreCompact hook snapshotted them to:\n  %s\n(%d bytes: human prompts, "
        "assistant replies and tool names, no tool output).\nBefore continuing the task: read that file and "
        "file the durable outcomes with the mempalace tools (mempalace_checkpoint files several items and a "
        "diary entry in one call). Delete the file when done, then carry on." % (path, size)
    )


def main():
    payload = C.read_hook_input()
    cfg = C.load_config()
    cwd = str(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    ident = C.identity(cfg, cwd)
    session_id = C.safe_id(payload.get("session_id"))
    source = str(payload.get("source") or "unknown")

    parts = []
    handoff = pending_handoff(session_id)
    if handoff:
        parts.append(handoff)

    header = [
        "MEMPALACE SHARED BRAIN (plugin mempalace-sharedbrain %s). Session event: %s." % (C.plugin_version(), source),
        identity_line(cfg, ident, cwd),
        TOOL_NOTE,
        rules_line(cfg),
        "Wake-up: call mempalace_status first. Its response carries the hub's Memory Protocol and the AAAK dialect spec.",
    ]
    posture, cursor = posture_lines(cfg, ident)
    header.extend(posture)
    for extra in cfg.get("extra_context") or []:
        header.append(str(extra))
    parts.append("\n".join(header))

    if cfg["probe"].get("enabled", True) and source != "compact":
        outcome = P.run_probe(cfg, ident, cursor)
        parts.append(P.format_probe(outcome, ident))
        C.log("SESSION-START %s session %s identity %s: probe %s reachable=%s new=%d open=%d unacked=%d error=%r handoff=%s"
              % (source, session_id, ident, outcome.get("transport"), outcome.get("reachable"),
                 len(outcome.get("new_since_cursor") or []), len(outcome.get("open_tasks") or []),
                 len(outcome.get("unacked_tasks") or []), outcome.get("error"), bool(handoff)))
    else:
        C.log("SESSION-START %s session %s identity %s: probe skipped handoff=%s" % (source, session_id, ident, bool(handoff)))

    C.emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n\n".join(parts)}})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # fail open
        C.log("SESSION-START crashed: %s: %s" % (type(exc).__name__, exc))
        C.emit({})
