---
description: File this session's durable outcomes to the MemPalace palace now and write a diary entry
argument-hint: "[topic]"
---

# Checkpoint this session to the palace

Use the agent id from the MEMPALACE SHARED BRAIN block in this session's context (or
`bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" show`). `$ARGUMENTS`, if given, is the topic.

1. List what this session produced that someone would want to find later: decisions and why,
   conclusions, learned facts, corrections to earlier beliefs, verbatim quotes from the user
   that set direction, code or commands worth keeping. Leave out secrets, tokens, transient
   state and anything already filed.
2. For each item that is a rule or preference, `mempalace_check_duplicate` first. If a match
   exists, update that drawer with `mempalace_update_drawer` rather than filing a second one.
3. File the rest with `mempalace_add_drawer`: wing = the project, room = the aspect
   (decisions, problems, architecture, deployment...). Open each drawer with a purpose line
   phrased as the problem someone would search for, then a `Search terms:` line listing the
   phrasings they will actually type. Quote the user verbatim where it matters. Set
   `added_by` to the agent id.
4. Facts that changed: `mempalace_kg_supersede` for a single-valued fact (replaces old with new
   at one boundary), `mempalace_kg_invalidate` for a fact that simply ended, `mempalace_kg_add`
   for a new independent fact. Name drawer ids in the object. Objects cap at 128 characters.
5. If any claimed task reached a stopping point, ack it (`applied`, `blocked` or `failed`).
6. `mempalace_diary_write` with `agent_name=<agent id>`, one AAAK entry: what happened, what
   was learned, what matters, importance stars.

Report the drawer ids filed, any duplicates merged, and the diary entry id.
