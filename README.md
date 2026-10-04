# mempalace-sharedbrain

A Claude Code plugin for machines that join a [MemPalace](https://github.com/MemPalace/mempalace)
shared-brain hub: one `mempalace serve` process that several agents, on several machines, read
and write through. MemPalace's own plugin covers a palace on the local machine. This one covers
the client side of the hub, where the machine has no `mempalace` package, no local palace, and
reaches the hub over HTTP.

It implements the client half of MemPalace's
[shared-brain guide](https://mempalaceofficial.com/guide/shared-brain.html) inside Claude Code,
using MemPalace's own texts and tools throughout. The plugin adds no protocol wording of its own.

## What it does

**Wires the protocol into CLAUDE.md** (guide, section 5). `mempalace rules` prints the canonical
shared-brain block for an agent's instruction file, wrapped in markers for in-place re-rendering.
The plugin renders the same block from a vendored copy of the same template (see
`vendor/UPSTREAM.md`), or from the CLI when it is installed, and installs, checks or refreshes it
in `~/.claude/CLAUDE.md`. Every session start reports whether the installed block is current,
stale or missing.

**Composes the identity.** `host:harness:project`, with the project taken from the session's
working directory, as the protocol describes. A fixed identity is available for hubs that already
use another convention.

**Carries the inbox cursor.** The protocol's cursor is the id of the last event you processed,
resumed with `since_event_id`, never a timestamp. The plugin stores it per identity, shows it at
session start, and the inbox command records it.

**Sweeps the inbox at session start.** By default the SessionStart hook tells the model exactly
which `mempalace_event_list` calls to make, from the stored cursor, before the first task. With a
hook-side path to the hub it makes them itself: `/healthz`, `mempalace_status`, events since the
cursor, open task requests this identity has not acknowledged, placed in context before the first
prompt. Event bodies are shown as excerpts and labelled as data.

**Wakes the session on coordination events** (guide, section 7). A chat session has no
background loop and a remote client should not run `mempalace logstream watch`. When the user
arms listening, each prompt triggers one sweep since the watch cursor for the armed event types,
excluding the identity's own events: run by the hook when it has a path to the hub, otherwise
requested of the model in that turn. Arming prints the announcement the protocol asks for, and
disarming prints the declared-idle statement.

**Keeps saves working for a remote client.** MemPalace's Stop and PreCompact hooks save through
the local package, which a hub client does not have. Here the Stop hook asks the model, in
MemPalace's own words, to save through the MCP tools every 15 human turns, and the PreCompact hook
snapshots the conversation to a private file without blocking, handed back after compaction.

**Routes work to machines that can do it.** Each machine probes what it can do: OS, CPU threads,
memory, GPU, Xcode release and beta versions, iOS simulators, git, gh, linode-cli, Docker, Podman,
distrobox, Tailscale, Node, Python, an agent signing key, plus any checks you add. The probe reads
local facts only, no secret values. `/mempalace-sharedbrain:capabilities` publishes the result to the
hub as knowledge-graph facts on the host label (`has_capability`, `lacks`) and one profile drawer
per host. Session start shows the machine's capabilities and nudges when the hub's copy is out of
date. A task names its requirements in `metadata.requires` or a `Requires:` line, such as
`xcode>=27, memory-gb>=32`. Delegation finds a host that meets them, and the inbox, the session-start
sweep and the wake check flag any task this machine cannot meet before anyone claims it.

**Runs as a mod where Claude Code supports one.** The plugin carries a hooks module
(`hooks/register.tsx`) beside its command hooks. On a Claude Code build that loads mods, the module
makes the hub calls itself through `$.mcp.call`, with the session's own logged-in MCP connection, so
no token and no hook-side transport are needed: it sweeps the inbox with the first prompt and flags
tasks this machine cannot meet. It records the cursor only once the conversation shows its message
reached the model, so a dropped message is shown again rather than skipped. While listening is armed it checks every minute
in the background, raises a toast and hands new mail over with the next prompt. The status line
shows the identity, open tasks and new mail. `/mempalace` opens a pane with the same and closes it
again (`/mempalace open` and `/mempalace close` say which); Escape and the pane's Close button
close it too. The
module tags each event it passes down, and the command hooks beneath leave out what it now does.
Where mods do not load (older builds, or a Claude Code plugin running in another harness through a
bridge), the command hooks work as before.

**Commands.**

| Command | Does |
|---|---|
| `/mempalace-sharedbrain:setup` | Identity, the model's and the hook's path to the hub, rules block, live check. |
| `/mempalace-sharedbrain:rules` | Render, check or install the canonical rules block, diff first. |
| `/mempalace-sharedbrain:inbox` | Sweep from the cursor, report verbatim, claim only on a go-ahead, record the cursor. |
| `/mempalace-sharedbrain:listen` | Arm or disarm the wake check and post the announcement. |
| `/mempalace-sharedbrain:delegate` | `mempalace_task_create` with a preview, optional `--requires` to pick a capable host, then arm, wait, verify, ack, file the outcome. |
| `/mempalace-sharedbrain:checkpoint` | `mempalace_checkpoint`: drawers and a diary entry in one call. |
| `/mempalace-sharedbrain:capabilities` | Probe this machine, publish its profile, check requirements, find hosts that meet them. |
| `/mempalace-sharedbrain:sessions` | The agents writing to the hub (`host:harness:project` identities), newest first, with when each was last active: who to send work to. The mod answers it directly. |
| `/mempalace-sharedbrain:peers` | `mempalace_mesh_peers` and `/statusz`: hub, recent clients, mesh peers. Under the mod it leaves the menu on a single hub with no hook-side transport, where it has nothing to report. |

## Requirements

- Claude Code 2.1 or newer with a MemPalace MCP server registered (`claude mcp list` shows it).
  Any registration works: a remote hub with a bearer token, a remote hub behind OAuth, or a local
  `mempalace-mcp` proxying to a local hub. The hooks only need the `mempalace_*` tools to exist.
- bash and python3 (3.8 or newer). Nothing is installed and no packages are needed.

## Install

```
claude plugin marketplace add shanelord01/claude-mempalace-sharedbrain
claude plugin install mempalace-sharedbrain@shanelord01 --scope user
```

Then, in a Claude Code session:

```
/mempalace-sharedbrain:setup
```

From a shell the same steps are `scripts/setup.sh init`, `scripts/setup.sh rules install --write`
and `scripts/setup.sh probe`. Every key is in [docs/configuration.md](docs/configuration.md).
Update later with `claude plugin update mempalace-sharedbrain@shanelord01`.

## No credentials needed

The model reaches the hub through its logged-in MCP server, and that is the only connection the
plugin relies on. By default the hooks hold no credential at all. They compute what the model
cannot know on its own (identity, cursor, watch state, rules-block status) and, where a hub call
is due, ask the model to make that one call through its own server in the same turn: the inbox
sweep at session start, and the wake check on each prompt while listening is armed.

Optionally the hooks can read the hub themselves, so the session-start check and the wake check
run before the model is involved and cost it nothing. `setup` offers three paths:

- the hub's HTTP endpoint with its static bearer token, read from an environment variable or a
  command such as a keychain lookup (the setup MemPalace's remote-server guide describes).
- the OAuth client credentials grant against the hub's authorization server, for a hub behind an
  OAuth login: a confidential client per machine, its secret in the keyring, the access token
  cached until it expires, no static hub token on any machine.
- a local `mempalace-mcp`, which proxies to a hub on the same machine.

## Hosting a hub

MemPalace's [remote server guide](https://mempalaceofficial.com/guide/remote-server.html) covers
`mempalace serve` with a static token. [docs/hub-setup.md](docs/hub-setup.md) adds an OAuth login
in front of it: the hub and Qdrant on a private machine with no open inbound ports, reached through
a Newt/Pangolin tunnel, Pocket ID as the OAuth 2.1 authorization server, and a small caddy-jwt
container that swaps each client's JWT for the hub's static token. Claude Code, Claude Desktop,
the mobile apps and claude.ai all log in with a passkey. The same guide is on the
[hermes-mempalace-sharedbrain wiki](https://github.com/shanelord01/hermes-mempalace-sharedbrain/wiki/MemPalace-Hub-behind-Newt-Pangolin-OAuth).

Hermes Agent users: [hermes-mempalace-sharedbrain](https://github.com/shanelord01/hermes-mempalace-sharedbrain)
is the matching memory provider, so a Hermes gateway and your Claude Code machines share one hub
and one logstream.

## Other Claude surfaces

Claude Desktop's Claude Code tab runs this plugin like the terminal does. The chat side of Claude
Desktop, the mobile apps and claude.ai cannot run plugins or hooks. For those, add the hub as a
connector and paste the rendered rules block (`scripts/setup.sh rules render`) into Settings >
Personal preferences, as the guide's instruction-file table suggests for harnesses without a
file.

## Tests

```
tests/run.sh
```

Runs every hook and the setup tool against a transcript fixture and a fake hub over HTTP (JSON
and SSE, with and without a token, with and without the `writer` filter) and stdio. Needs only
bash and python3.

## Licence

MIT. The vendored MemPalace template keeps its own MIT licence and copyright.
