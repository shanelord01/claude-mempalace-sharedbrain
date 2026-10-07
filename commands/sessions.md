---
description: List the agents on this MemPalace hub (host:harness:project identities) with when each was last active, so you know which name to send work to
---

# Sessions on the hub

Where the plugin's mod is loaded it answers this command itself, without the model: every
session running the mod checks in to the hub (one drawer per identity in the presence room,
updated with the first prompt and every 30 minutes), and the command lists those check-ins.
Otherwise build the list:

0. `mempalace_list_drawers` with the presence room (`bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" show`
   names the wing; the room is `presence`). Each check-in's first line reads
   `identity: <id> | checked_in <UTC time> | plugin <version> | listening <yes|no> | ...`. List them
   newest first; one older than 90 minutes is idle. If the room is empty, use the event log:
1. `mempalace_event_list` with `limit=20` and `preview=true` (newest first): a larger page can be
   refused for its size. Page back with `before_event_id=<oldest id seen>` up to four more times
   while the pages cover less than a week.
2. Group the events by `from_agent`. For each identity report: when it last wrote, how many
   events it wrote in what you read, and its host (the part before the first `:`).
3. Mark this session's own identity, and mark a name without two colons as a fixed or legacy id:
   agents such as Hermes keep fixed names, but a Claude Code machine still writing under an old
   flat name has not moved to the `host:harness:project` form, and tasks should go to its new
   identity. The estate's roster drawer says which is which when one exists.
4. Say plainly what the list is: identities seen writing to the hub, not a live connection list.
   MemPalace keeps no record of who is connected. Every session in the same project folder on the
   same machine shares one identity, and a task addressed to it reaches whichever of them sweeps
   the inbox next.

To pick a machine by what it can do rather than by name, use
`/mempalace-sharedbrain:capabilities who`.
