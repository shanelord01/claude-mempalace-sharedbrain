# mempalace-sharedbrain

A Claude Code plugin for a [MemPalace](https://github.com/MemPalace/mempalace) memory palace,
shared between machines through a hub (`mempalace serve`) or kept locally. It makes every
session start from the palace instead of from nothing: the hook checks the palace, reads the
task inbox and names the drawers to fetch before the model gets the first prompt, reminds the
model to file what it learned, and snapshots the conversation before Claude Code compacts it.

The same hooks, commands and rules install on every machine with one command and update with
one more, so each agent on the palace runs the same protocol.

## What it does

**Session start** (new session, resume, `/clear`, and after a compaction). The hook adds a
context block before the first prompt: this machine's agent id, the bootstrap checklist
(`mempalace_status`, inbox check, canonical drawers by id, search before answering), and the
attribution and task-closing rules. When it has a way to reach the palace it also runs a live
check and reports the drawer count and every open task addressed to this agent that this agent
has not yet acknowledged, verbatim. The model cannot skip the inbox: it is already in front of
it.

**Stop.** Every 15 human turns (configurable) the hook blocks the stop once and asks the model to
file the session's durable outcomes and a diary entry. Claude Code shows this as "Stop hook
error" followed by the request. That is its label for any blocking hook.

**Before compaction.** The hook writes the human prompts, assistant replies and tool names since
the last snapshot to a pending file, using no model context, and never blocks. After the
compaction the session-start hook hands that file to the model to file and delete. Nothing said
since the last checkpoint is lost to a compaction.

**Commands.**

| Command | Does |
|---|---|
| `/mempalace-sharedbrain:setup` | Configure this machine: agent id, how the hook reaches the palace, canonical drawers. Tests it. |
| `/mempalace-sharedbrain:bootstrap` | Run the session bootstrap on demand and report. |
| `/mempalace-sharedbrain:inbox` | List delegated tasks verbatim; claim and work one only on a go-ahead; close the loop. |
| `/mempalace-sharedbrain:checkpoint` | File this session's outcomes now, dedup first, diary entry last. |
| `/mempalace-sharedbrain:delegate` | Draft a task for another agent with the user, then post it. |

**Skill.** `mempalace-protocol` holds the full working rules for an agent on a shared palace:
identity, bootstrap, recall, writing, knowledge-graph changes, the logstream, and how to change a
shared rule without leaving two versions behind. The model loads it when a decision needs the
long form.

## Requirements

- Claude Code 2.1 or newer with a MemPalace MCP server registered (`claude mcp list` shows it).
  Any registration works: a local `mempalace-mcp`, a remote hub with a bearer token, or a remote
  hub behind OAuth. The hooks only need the `mempalace_*` tools to exist in the session.
- bash and python3 (3.8 or newer) on the machine. Nothing is installed, no packages are needed.

## Install

```
claude plugin marketplace add shanelord01/claude-mempalace-sharedbrain
claude plugin install mempalace-sharedbrain@shanelord01 --scope user
```

Then, in a Claude Code session:

```
/mempalace-sharedbrain:setup
```

The command walks through the agent id, how the hook should reach the palace, and the canonical
drawers, and runs the live check. The equivalent from a shell is `scripts/setup.sh`; see
[docs/configuration.md](docs/configuration.md) for every key and three ready-made setups
(local stdio, static token, OAuth hub).

Update later with `claude plugin update mempalace-sharedbrain@shanelord01`.

## Agent ids

Every write to the palace carries an agent id, and tasks on the logstream are addressed to one.
Use the machine's hostname, lowercase and hyphenated, and keep it unique across the palace. If a
machine is renamed, record `old -renamed_to-> new` in the knowledge graph and announce it on the
logstream, or history under the old id becomes unattributable.

## How the hook reaches the palace

The model reaches the palace through its MCP server. The hook runs before the model exists, so it
needs its own path, chosen in `setup`:

- a local stdio server (`mempalace-mcp`), started and stopped by the hook.
- an HTTP server (`mempalace serve`, local or remote) with its static bearer token, read from an
  environment variable or a command such as a keychain lookup.
- none, for a hub that only accepts OAuth logins. The bootstrap block still tells the model to run
  the inbox check itself. Only the hook's own live check is skipped.

## Hosting a shared hub

[docs/hub-setup.md](docs/hub-setup.md) is a full walkthrough for running a hub on a private
machine with no open inbound ports: MemPalace and Qdrant behind a Newt/Pangolin tunnel, Pocket ID
as the OAuth 2.1 authorization server, and a small caddy-jwt container that swaps each client's
JWT for the hub's static token. Claude Code, Claude Desktop, the mobile apps and claude.ai all
log in with a passkey. The same guide is on the
[hermes-mempalace-sharedbrain wiki](https://github.com/shanelord01/hermes-mempalace-sharedbrain/wiki/MemPalace-Hub-behind-Newt-Pangolin-OAuth).

For the simpler case, `mempalace serve` with a static token on a LAN or VPN, follow MemPalace's
own [remote server guide](https://mempalaceofficial.com/guide/remote-server.html) and register
the URL with `claude mcp add --transport http --scope user mempalace <url>/mcp --header
"Authorization: Bearer <token>"`.

Hermes Agent users: [hermes-mempalace-sharedbrain](https://github.com/shanelord01/hermes-mempalace-sharedbrain)
is the matching memory provider, so a Hermes gateway and your Claude Code machines share one
palace and one logstream.

## Other Claude surfaces

Claude Desktop's Claude Code tab runs this plugin like the terminal does. The chat side of Claude
Desktop, the mobile apps and claude.ai cannot run plugins or hooks. For those, add a MemPalace
connector, upload `skills/mempalace-protocol` as a skill, and put two lines in Settings >
Personal preferences: your agent id for that surface, and an instruction to call
`mempalace_status` and check the inbox before starting work.

## Tests

```
tests/run.sh
```

Runs every hook against a transcript fixture and a fake MemPalace server over HTTP (JSON and
SSE), stdio, and with a bad token. Needs only bash and python3.

## Licence

MIT.
