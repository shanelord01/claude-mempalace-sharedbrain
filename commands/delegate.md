---
description: Delegate a task to another agent on the shared MemPalace logstream with mempalace_task_create, previewed with the user, then arm the wake check and wait
argument-hint: "<to-agent | --requires REQ,...> <what to do>"
---

# Delegate work

The shared-brain block's "To delegate" bullet, as a procedure. Your identity is in the
MEMPALACE SHARED BRAIN block in this session's context.

1. Resolve the worker. `$ARGUMENTS` starts with the target identity (`host:harness:project`
   form, or whatever that machine registered), or with `--requires` and a list such as
   `xcode>=27,memory-gb>=32`. With requirements and no target, follow the `who` section of
   `/mempalace-sharedbrain:capabilities` to find hosts whose published profile meets them, and
   propose a live identity on one. If none qualifies, say so; a broadcast to `*` is the fallback
   only when the user agrees. Check the chosen identity is live: `mempalace_event_list` with
   `writer=<id>` (or `from_agent=<id>`) for recent activity, and `mempalace_kg_query` on it. A task
   sent to a stale or generic id is never seen. If unsure, ask the user.
2. Draft with the user: goal (the user's words where they set it), project, git branch, base
   commit (a commit hash, not a branch name), exact definition of done, and `topic` if the work is
   a named lane. Show the complete draft and wait for confirmation.
   Requirements, when the work needs them, are part of the draft.
3. Create it with `mempalace_task_create` (project, from_agent, to_agent, goal, branch,
   base_commit, done). When there are requirements, the goal's first line is
   `Requires: <req>, <req>`; task_create has no metadata field, and workers read that line. It returns the stored `task.request` and a handoff line. For non-code work
   use `mempalace_event_append` with `type=task.request`, `stream=project/<name>`,
   `room=delegation`, `status=open`, a `correlation_id` like `task_<slug>_<entropy>`, the same
   fields in the body, and requirements as `metadata.requires` (a list) plus the same
   `Requires:` first line.
4. Delegating is a watch trigger: run `/mempalace-sharedbrain:listen arm --correlation-id <id>`
   and post the announcement it prints.
5. Wait: `mempalace_event_wait` with the `correlation_id` and `to_agent=<identity>`. It caps at
   five minutes and returns `{timed_out: true}` as a normal result; loop, passing
   `since_event_id` of the last event seen, and do not wrap it in a tight retry.
6. On `patch.ready`: `mempalace_artifact_get`, verify the `sha256` against the content, apply only
   with the user's explicit go-ahead, run the stated verification, then `mempalace_event_ack`
   with `status=applied` or `status=failed` and verbatim evidence.
7. File the outcome: one `mempalace_add_drawer` recording what was decided or learned, so the
   result is searchable without replaying the event trail. Disarm the watch when the loop closes.
