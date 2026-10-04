"""SessionStart hook body.

Emits additionalContext with, in order: any pre-compaction snapshot waiting
to be filed for this session, the bootstrap checklist with this machine's
agent id and canonical drawer ids, and the result of a live probe of the
palace (skipped after a compaction, since the inbox was already shown).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import sb_common as C  # noqa: E402
import sb_probe as P  # noqa: E402

TOOL_NOTE = (
    "The palace is reached through the mempalace_* MCP tools. Your client may list them under a "
    "server prefix (mcp__mempalace__, mcp__claude_ai_Mempalace__, mcp__plugin_mempalace_mempalace__). "
    "If no mempalace tools are present in this session, say so. Never answer as if you had checked."
)


def bootstrap_block(cfg, agent, source):
    lines = [
        "MEMPALACE SHARED BRAIN (plugin mempalace-sharedbrain %s). Agent id: %s. Session event: %s."
        % (C.plugin_version(), agent, source),
        TOOL_NOTE,
        "Before the first task of this session, and again after a compaction:",
    ]
    step = 1
    lines.append("%d. mempalace_status once. Its response carries the palace's Memory Protocol and AAAK "
                 "dialect spec alongside the counts." % step)
    step += 1
    lines.append("%d. Inbox: mempalace_event_list with to_agent=%s, status=open (this also matches * "
                 "broadcasts). Report any task.request to the user verbatim. Never claim a task without "
                 "the user's explicit go-ahead." % (step, agent))
    step += 1
    drawers = cfg.get("canonical_drawers") or []
    if drawers:
        lines.append("%d. Fetch these canonical drawers by id with mempalace_get_drawer (search ranking "
                     "drifts as a palace grows, ids do not):" % step)
        step += 1
        for drawer in drawers:
            if isinstance(drawer, dict):
                lines.append("   - %s  %s" % (drawer.get("id", ""), drawer.get("note", "")))
            else:
                lines.append("   - %s" % drawer)
    lines.append("%d. Before answering about past work, decisions, people or projects: mempalace_search "
                 "or mempalace_kg_query first, and quote what comes back verbatim. If the palace has "
                 "nothing, say so rather than guessing." % step)
    lines.append(
        "Every write (mempalace_add_drawer, mempalace_diary_write, mempalace_kg_add, "
        "mempalace_event_append, mempalace_event_ack) carries from_agent / added_by = %s. File durable "
        "outcomes, never secrets. Run mempalace_check_duplicate before filing a rule or preference. "
        "Close every task you touch: claimed, then applied, blocked or failed. The mempalace-protocol "
        "skill holds the full rules." % agent
    )
    for extra in cfg.get("extra_context") or []:
        lines.append(str(extra))
    return "\n".join(lines)


def pending_handoff(session_id):
    path = os.path.join(C.PENDING_DIR, "%s.md" % session_id)
    try:
        size = os.path.getsize(path)
    except OSError:
        return ""
    if size == 0:
        return ""
    return (
        "MEMPALACE: the conversation was just compacted or resumed and the exchanges since the last "
        "palace save were NOT filed. The PreCompact hook snapshotted them to:\n  %s\n(%d bytes: human "
        "prompts, assistant replies and tool names, no tool output).\nBefore continuing the task: read "
        "that file, then file the durable outcomes (decisions, conclusions, learned facts, verbatim "
        "quotes, code) with the mempalace MCP tools. Run mempalace_check_duplicate before filing a rule "
        "or preference, then mempalace_add_drawer with a purpose line phrased as the problem someone "
        "would search for plus a 'Search terms:' line. Record changed facts with mempalace_kg_add, and "
        "use mempalace_kg_supersede rather than stacking a contradictory fact. Delete the file when "
        "done, then carry on." % (path, size)
    )


def main():
    payload = C.read_hook_input()
    cfg = C.load_config()
    agent = C.agent_id(cfg)
    session_id = C.safe_id(payload.get("session_id"))
    source = str(payload.get("source") or "unknown")

    parts = []
    handoff = pending_handoff(session_id)
    if handoff:
        parts.append(handoff)
    parts.append(bootstrap_block(cfg, agent, source))

    if cfg["probe"].get("enabled", True) and source != "compact":
        outcome = P.run_probe(cfg, agent)
        parts.append(P.format_probe(outcome, agent))
        C.log("SESSION-START %s session %s agent %s: probe %s reachable=%s open=%d unacked=%d error=%r handoff=%s"
              % (source, session_id, agent, outcome.get("transport"), outcome.get("reachable"),
                 len(outcome.get("open_tasks") or []), len(outcome.get("unacked_tasks") or []),
                 outcome.get("error"), bool(handoff)))
    else:
        C.log("SESSION-START %s session %s agent %s: probe skipped handoff=%s"
              % (source, session_id, agent, bool(handoff)))

    C.emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n\n".join(parts)}})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # fail open
        C.log("SESSION-START crashed: %s: %s" % (type(exc).__name__, exc))
        C.emit({})
