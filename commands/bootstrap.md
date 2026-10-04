---
description: Run the MemPalace session bootstrap now (status, inbox, canonical drawers) and report what it finds
---

# MemPalace bootstrap, on demand

Use the agent id from the MEMPALACE SHARED BRAIN block in this session's context. If there is
no such block, run `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" show` and read `agent_id`.

Do all of these, then report in one short message:

1. `mempalace_status`. Note the drawer count and read the Memory Protocol it returns.
2. `mempalace_event_list` with `to_agent=<agent id>`, `status=open`, `type=task.request`,
   `preview=true`. Then `mempalace_event_list` with `from_agent=<agent id>` to see which of those
   you have already acked. List every unacked task verbatim (id, from, date, body). Do not claim
   any of them. The user decides.
3. For every canonical drawer id in the block, `mempalace_get_drawer` and apply what it says to
   this session. If a drawer id returns "not found", say so: the config needs updating.
4. `mempalace_kg_query` on your own agent id, so you know what the palace already records about
   this machine.

Report: palace reachable or not, drawer count, unacked tasks (verbatim), any canonical drawer
that failed to load, and anything in the protocol or drawers that changes how this session
should proceed.
