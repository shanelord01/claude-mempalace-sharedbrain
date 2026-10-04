---
description: Configure the MemPalace plugin on this machine (agent id, how the hook reaches the palace, canonical drawers) and test it
argument-hint: "[agent-id]"
---

# Set up mempalace-sharedbrain on this machine

Work through this with the user. Each step has a command. Run it, show the result, move on.

## 1. Current state

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" show
```

If a config file already exists, confirm with the user before changing anything.

## 2. Agent id

Every write to the palace is attributed to an agent id, and tasks are addressed to one. The
convention is the machine's hostname, lowercase, hyphenated (for example `work-laptop`,
`office-desktop`). It must be unique across every machine that shares the palace. If
`$ARGUMENTS` names one, use it. Otherwise propose the hostname-derived default from step 1 and
ask the user to confirm or change it. Never reuse another machine's id.

## 3. How the model reaches the palace

Run `claude mcp list` and find the MemPalace server. Note its name: the model's tool names carry
that name as a prefix (for example `mcp__mempalace__mempalace_search`). The hooks only need the
`mempalace_*` tools to exist; they do not care about the prefix.

If there is no MemPalace server, stop and help the user add one first:
- Local palace: `claude mcp add mempalace -- mempalace-mcp` (needs the `mempalace` Python package).
- Remote hub with a static token: `claude mcp add --transport http --scope user mempalace <url>/mcp --header "Authorization: Bearer <token>"`.
- Remote hub with OAuth: `claude mcp add --transport http --scope user mempalace <url>/mcp`, then `/mcp` and Authenticate.

## 4. How the hook reaches the palace (the live check)

The SessionStart hook runs before the model exists, so it needs its own path to the palace.
Pick one with the user:

- Local stdio server: `--stdio-command "mempalace-mcp"` (whatever `claude mcp get mempalace` shows as the command).
- Local or remote HTTP server with a static bearer token: `--url <url>/mcp` plus either
  `--token-env MEMPALACE_MCP_HTTP_TOKEN` (the variable the hook reads) or
  `--token-command "<command that prints the token>"` (a keychain or secret-store lookup; the
  token itself is never written to the config file).
- Remote hub that only accepts OAuth logins: `--transport none`. The hook cannot borrow the
  model's OAuth token, so the live check is skipped and the model runs the inbox check itself.

Write the config:

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" init --agent-id <id> <transport flags>
```

## 5. Canonical drawers (optional)

Drawers the bootstrap should fetch by id every session: a protocol or house-rules drawer, an agent
roster, a style guide. Ask the user for ids and a short note each:

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" add-drawer <drawer_id> "<note>"
```

## 6. Test

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" probe
```

A reachable palace prints its drawer count and the open tasks addressed to this agent. A 401
means the token is missing or wrong, or the hub only accepts OAuth (use `--transport none`).
A connection error means the URL or the network, not the plugin.

## 7. Finish

Tell the user: the bootstrap block appears at the start of every new session from now on
(`/mempalace-sharedbrain:bootstrap` runs it on demand), and the config lives at the path printed
by `setup.sh path`. If the palace is shared with other agents, suggest filing a short drawer
announcing this agent id so the others know who is on the palace.
