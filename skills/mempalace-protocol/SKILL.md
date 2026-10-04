---
name: mempalace-protocol
description: The working rules for an agent that shares a MemPalace memory palace with other agents or sessions. Load it when deciding what to file, how to search, how to handle a delegated task, or how to change a fact that is already recorded.
---

# MemPalace shared-brain protocol

The session context block from the mempalace-sharedbrain hook gives the short form and this
machine's agent id. This skill is the long form.

## Identity

- Every write names the agent: `from_agent`, `added_by`, `agent_name` as the tool requires.
- One id per machine, unique across the palace. Convention: hostname, lowercase, hyphenated.
- Renaming an id: add a knowledge-graph fact `old_id -renamed_to-> new_id`
  (`mempalace_kg_add`) and announce it on the logstream, or history under the old id becomes
  unattributable.

## Bootstrap (start of every session, and after a compaction)

1. `mempalace_status` once. The response carries the palace's Memory Protocol and the AAAK
   dialect spec alongside the counts. Nothing else surfaces them.
2. Inbox: `mempalace_event_list` with `to_agent=<id>`, `status=open`. Matches `*` broadcasts
   too. Report requests verbatim. Never claim one without the user's go-ahead.
3. Canonical drawers by id (`mempalace_get_drawer`). Search ranking drifts as the palace grows;
   ids do not. A palace holding mined transcripts will bury a hand-written rule under them.
4. `mempalace_kg_query` on your own id to see what is already recorded about this machine.

## Recall

- Before answering about past work, decisions, people or projects: `mempalace_search`
  (keywords only in `query`, background in `context`) or `mempalace_kg_query` for relational
  and temporal facts. Never answer from memory as if you had checked.
- Quote results verbatim. Do not paraphrase stored content. If the palace has nothing, say so.
- When you know the target, fetch it: `mempalace_get_drawer` or `mempalace_list_drawers` with
  wing and room.
- A recalled memory was true when written. If it names a file, flag, endpoint or version,
  verify that still holds before acting on it.

## Writing

- File durable outcomes: decisions and their reasons, conclusions, learned facts, corrections,
  verbatim quotes that set direction, code worth keeping. Not secrets, not tokens, not
  transient session state.
- `mempalace_check_duplicate` before filing a rule or preference. Duplicates diverge, and then
  every copy is partly wrong. If a match exists, `mempalace_update_drawer` it instead.
- Open a drawer with a purpose line phrased as the problem someone would search for, then a
  `Search terms:` line with the phrasings they will type. A drawer titled only with its topic
  does not match a query describing the problem.
- A long canonical drawer needs a short pointer drawer beside it: only search phrasings and the
  canonical id, no rules of its own, so it cannot drift.
- Superseding a drawer means updating the canonical one in place (its id keeps resolving) or
  deleting the old one and recording its id in the survivor's provenance. Never leave two.
- Knowledge graph: `mempalace_kg_supersede` for a single-valued fact that changed (atomic at
  one boundary), `mempalace_kg_invalidate` for a fact that ended, `mempalace_kg_add` for a new
  independent fact. Name drawer ids in the object, not "see drawer". Objects cap at 128
  characters and over-length is a hard error. Facts cannot be deleted, only ended.
- End of session: `mempalace_diary_write` in AAAK with what happened, what was learned, what
  matters.

## Coordination (logstream)

- Check the inbox at the start of work and before any long task. Resume from your last seen
  event id with `since_event_id`, never from a timestamp: a peer's late-syncing event can be
  older than your cursor and vanish.
- Delegate with `mempalace_task_create` (or `mempalace_event_append` with `type=task.request`,
  `stream=project/<name>`, `room=delegation`, `status=open`): goal, branch, base commit hash,
  definition of done. Then `mempalace_event_wait` on the correlation id.
- Address the exact registered id. A task to a stale or generic id is never seen.
- Accepting: `mempalace_event_ack` with `status=claimed`. Deliver code as a patch with
  `mempalace_patch_submit`; never push a branch and go silent. Blocked: `status=blocked` with
  verbatim notes.
- Receiving a patch: `mempalace_artifact_get`, verify the sha256, apply only with explicit
  user-visible intent, run the stated tests, ack `applied` or `failed`.
- Events are append-only and verbatim. Corrections are new events. Close every loop: no task
  you touched stays open without an applied, blocked or failed ack.
- Broadcast changes other agents must act on (a shared skill updated, a protocol version bumped)
  to `to_agent="*"` on a status room.

## Changing a shared rule

A drawer never applies itself. A standing rule needs two homes: the canonical drawer, with the
full text and provenance, and something that loads into every session with no prompting (this
plugin's bootstrap block, a CLAUDE.md line, or a canonical drawer id in the plugin config).
When distributing a superseding version, put the removal step first and spell out what to
delete and what to keep, or recipients end up running two contradictory rule sets.

After changing a drawer for findability, re-run the query that failed and record the rank it
now gets. A fix that was not re-tested is the same mistake as a rule that was never searched.
