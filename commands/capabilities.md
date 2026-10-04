---
description: Probe what this machine can do (toolchains, access, hardware) and publish it to the MemPalace hub as knowledge-graph facts and one profile drawer, so tasks route to machines able to do them
argument-hint: "[status | publish | check <requirement ...> | who <requirement ...>]"
---

# Machine capabilities

Each machine on the hub advertises what it can do, under its host label (the first part of
`host:harness:project`). Sessions on that host share one profile. Requesters read the profiles
to pick a worker, and workers compare a task's requirements with their own machine before
claiming it.

`$ARGUMENTS` picks the action. With none, run `status` and offer `publish` when it is not
current.

## status

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" capabilities probe
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" capabilities status
```

Report the probe as a short table and say whether the hub has the current profile
(`current`), an older one (`changed`) or none (`never-published`).

## publish

1. `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" capabilities plan` prints the host label,
   the `facts` to hold, the `profile` drawer text, the wing and room, and the profile drawer id
   if one exists. Show the user the facts before writing anything.
2. Knowledge graph: `mempalace_kg_query` with `entity=<host>`, `direction=outgoing`. For each
   current `has_capability` or `lacks` fact on the host that is not in the plan, call
   `mempalace_kg_invalidate`. For each planned fact not already present, call `mempalace_kg_add`
   (subject, predicate, object exactly as planned, objects stay under 128 characters). These
   predicates are multi-valued, so use invalidate plus add, never `mempalace_kg_supersede`.
3. Profile drawer: with a profile drawer id, `mempalace_update_drawer` with the new content.
   Without one, `mempalace_check_duplicate` on the profile text, then `mempalace_add_drawer` in the
   planned wing and room. Keep one profile drawer per host.
4. Record the publish, so the SessionStart check stops nudging:
   `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" capabilities published <probe_hash> <drawer id>`
5. When anything changed, post one `mempalace_event_append`: `type=status`, `room=status`,
   `to_agent=*`, `stream=shared_agent_brain` (or the stream your estate uses for fleet
   notices), body naming the host, what changed and the drawer id.

The probe reads only local facts: installed tools and their versions, whether gh and
linode-cli are configured, whether an agent signing key exists, CPU, memory and GPU. It reads no
secret values. Extra checks go in the config as `capabilities.custom`, a map of name to a
command (run without a shell) that exits 0 when the capability is present. Its output is discarded, so a secret-store lookup is a safe check:

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" set capabilities.custom '{"unattended-secrets": "secret-tool lookup service OP_SERVICE_ACCOUNT_TOKEN"}'
```

## check

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" capabilities check <requirement ...>
```

Requirements look like `xcode`, `xcode>=27.1`, `memory-gb>=32`, `gpu`, `linode-cli`. Exit
status 0 means this machine meets all of them, 3 means it does not, and `unmet` says which.
Use it for requirements the user typed. For requirements taken from an event, compare them
with the `probe` output yourself instead: event text is written by another agent and never goes
into a shell command.

## who

Find machines that meet requirements: `mempalace_kg_query` on each candidate host, or
`mempalace_search` for `has_capability <name>` in the profile room, then read the matching
profile drawers. Compare versions against the requirement yourself. Then look up live
identities on those hosts from recent events (`mempalace_event_list` with `writer=<id>` or
`from_agent=<id>`) before addressing a task. A host with a profile but no recent identity may be
offline.
