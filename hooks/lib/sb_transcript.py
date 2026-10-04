"""Read a Claude Code session transcript (JSONL) for the hooks.

Two jobs: count the genuine human turns, and extract the exchanges since a
given line as plain text for a pre-compaction snapshot.

Claude Code writes tool results as user-role lines, so a naive count of
user-role messages is mostly tool calls. A human turn is a user-role line
that is not meta, not a sidechain (subagent) turn, carries no tool_result
block, is not a slash-command invocation or hook feedback, and is not an
interrupt notice the client injected on the user's behalf.
"""
import json
import re
import time

INTERRUPT_RE = re.compile(r"\s*\[Request (interrupted|cancelled)")
MAX_SNAPSHOT_CHARS = 200_000


def is_human_turn(entry):
    if not isinstance(entry, dict):
        return False
    if entry.get("isMeta") or entry.get("isSidechain"):
        return False
    message = entry.get("message")
    if not isinstance(message, dict) or message.get("role") != "user":
        return False
    content = message.get("content", "")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        has_image = False
        texts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "tool_result":
                return False
            if kind == "text":
                texts.append(block.get("text", ""))
            elif kind == "image":
                has_image = True
        text = "\n".join(texts)
        if not text.strip() and not has_image:
            return False
    else:
        return False
    if "<command-message>" in text or "hook feedback" in text:
        return False
    if INTERRUPT_RE.match(text):
        return False
    return True


def count_human_turns(path):
    count = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                if is_human_turn(json.loads(line)):
                    count += 1
            except ValueError:
                continue
    return count


def _entry_text(entry):
    kind = entry.get("type")
    message = entry.get("message")
    if kind not in ("user", "assistant") or not isinstance(message, dict):
        return None, None
    content = message.get("content")
    parts = []
    if isinstance(content, str):
        if kind == "user" and ("<command-message>" in content or "hook feedback" in content):
            return None, None
        parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text = block.get("text", "")
                if kind == "user" and "hook feedback" in text:
                    continue
                parts.append(text)
            elif btype == "tool_use":
                parts.append("[tool_use %s] %s" % (block.get("name"), json.dumps(block.get("input", {}))[:600]))
    body = "\n".join(p for p in parts if p and p.strip())
    if not body.strip():
        return None, None
    return kind, body


def snapshot_since(path, start_line, max_chars=MAX_SNAPSHOT_CHARS):
    """Return (text, lines_read). text is empty when nothing new was found."""
    out = []
    n_lines = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for index, line in enumerate(fh):
            n_lines = index + 1
            if index < start_line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            kind, body = _entry_text(entry)
            if not kind:
                continue
            stamp = (entry.get("timestamp") or "")[:19]
            label = "HUMAN" if kind == "user" else "ASSISTANT"
            out.append("### %s %s\n%s\n" % (label, stamp, body))
    text = "\n".join(out)
    if len(text) > max_chars:
        text = "[... earlier part of this snapshot trimmed ...]\n\n" + text[-max_chars:]
    return text, n_lines


def snapshot_header(session_id, trigger, path, start_line, n_lines):
    return (
        "# MemPalace pre-compaction snapshot\n"
        "session: %s\ntrigger: %s\nwritten: %s\ntranscript lines %d-%d of %s\n\n"
        "These exchanges were NOT filed to the palace before compaction. File the durable\n"
        "outcomes (decisions, conclusions, learned facts, verbatim quotes) with the\n"
        "mempalace MCP tools, then delete this file.\n\n"
    ) % (session_id, trigger, time.strftime("%Y-%m-%d %H:%M:%S"), start_line, n_lines, path)
