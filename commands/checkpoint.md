---
description: Save this session's durable outcomes to the hub now with mempalace_checkpoint (drawers plus a diary entry in one call)
argument-hint: "[topic]"
---

# Checkpoint this session

MemPalace's `mempalace_checkpoint` saves a whole session in one call: it dedups each item,
files the new ones as drawers, then writes one diary entry. Use it rather than many separate
calls. Identity comes from the MEMPALACE SHARED BRAIN block; `$ARGUMENTS`, if given, is the
diary topic.

1. List what this session produced that a future session should know: decisions and their
   reasons, conclusions, learned facts, corrections, the user's verbatim words that set
   direction, code or commands worth keeping. Leave out secrets, tokens, transient state and
   anything already filed.
2. Call `mempalace_checkpoint` with `items` (each `{wing, room, content}`, content verbatim),
   `added_by=<identity>`, and `diary={agent_name: <diary name>, entry: <AAAK>, topic}`. The diary
   name is the identity with colons replaced by underscores (the session block states it, or
   `setup.sh identity --diary`): MemPalace's `sanitize_name` rejects colons in `agent_name`. The
   AAAK spec comes back from `mempalace_get_aaak_spec` or the `mempalace_status` response.
3. Facts that changed: `mempalace_kg_supersede` for a single-valued fact, `mempalace_kg_invalidate`
   for one that ended, `mempalace_kg_add` for a new independent fact.
4. Any claimed task that reached a stopping point: ack it (`applied`, `blocked` or `failed`).

Report the drawer ids filed, duplicates skipped, and the diary entry id. The inbox cursor is
unchanged by a checkpoint.
