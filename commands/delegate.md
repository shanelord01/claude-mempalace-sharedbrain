---
description: Delegate a task to another agent on the shared MemPalace logstream, previewed with the user first
argument-hint: "<to-agent> <what to do>"
---

# Delegate a task over the logstream

Use this agent's id from the MEMPALACE SHARED BRAIN block as `from_agent`.

1. Resolve the worker. `$ARGUMENTS` starts with the target agent id. Confirm it is a live id:
   `mempalace_kg_query` on it, and `mempalace_event_list` with `from_agent=<id>` to see recent
   activity. A task sent to a stale or generic id is never seen and dies silently. If the id is
   unknown, ask the user.
2. Draft the request with the user: goal (verbatim where the user said it), project name, git
   branch, base commit (a commit hash, not a branch name), and an exact definition of done.
   Include the user's own words that set the scope.
3. Show the complete draft and wait for the user's confirmation.
4. Create it with `mempalace_task_create` (project, from_agent, to_agent, goal, branch,
   base_commit, done). For a non-code task use `mempalace_event_append` with
   `type=task.request`, `stream=project/<name>`, `room=delegation`, `status=open`, a
   `correlation_id` of the form `task_<slug>_<yyyymmdd>`, and the same body fields in prose.
5. Report the event id and correlation id. Offer to wait with `mempalace_event_wait` on the
   correlation id if the user wants the reply in this session.
