---
description: Arm or disarm the per-prompt wake check for this identity (the turn-based substitute for `mempalace logstream watch`) and post the announcement the protocol asks for
argument-hint: "[arm [--correlation-id ID] [--topic T] | disarm | status]"
---

# Listen: the wake check

The shared-brain block says to arm a watcher when the user asks you to listen, when you claim a
task, or when you delegate, and never at session start. A Claude Code session cannot run
`mempalace logstream watch` in the background and, as a remote MCP client, should not. This
plugin's substitute: while armed, every prompt the user sends triggers one sweep of events
addressed to this identity since the watch cursor, filtered to the armed types and excluding your
own events, and matches appear in your context.

`$ARGUMENTS` defaults to `status`.

## Arm

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" listen arm [--correlation-id <id>] [--topic <lane>]
```

Default types are `task.request`, `task.reply`, `patch.ready`. Keep `task.reply` in: a worker
reporting `blocked` or `failed` sends exactly that. The watch cursor starts at the newest event
(like a first `logstream watch`); backlog is the inbox sweep's job.

Then post the announcement the command prints, once, with `mempalace_event_append`:
`type=status`, `room=status`, `to_agent=*`, `correlation_id` if the watch is for one task,
`from_agent=<identity>`. Re-announce only if the filter changes.

If the hook has no path of its own to the hub, each prompt instead places the exact
`mempalace_event_list` call in your context for you to make through the logged-in MCP server,
and you advance the watch cursor afterwards with `setup.sh listen cursor <last event id>`. While
waiting on one known correlation, `mempalace_event_wait` in-turn is the protocol's complement.

## When a wake arrives

The context shows the matched events as excerpts, or the result of the call you made. Fetch each
in full with `mempalace_event_list` (by `correlation_id`), report to the user, act only on a
go-ahead, ack what you take on, and record your inbox cursor (`setup.sh cursor set <id>`). The
watch cursor advanced already when the hook ran the sweep. Advance it yourself when you did.

## Disarm

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" listen disarm
```

Then say or post the declared-idle statement it prints, so requesters know a ping is required
and where you left off. Never claim a watch you do not have.
