---
description: Configure this machine as a client of a MemPalace shared-brain hub (identity, rules block, how the hook reaches the hub) and test it
argument-hint: "[host-label]"
---

# Set up mempalace-sharedbrain on this machine

Work through this with the user. Each step has a command. Run it, show the result, move on.

## 1. Current state

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" show
```

If a config file already exists, confirm with the user before changing anything.

## 2. Identity

The MemPalace shared-brain protocol names every agent `host:harness:project`: a short stable
label for the machine (not a DHCP hostname), the runtime family (`claude` here), and the current
workspace name, which the plugin derives from the working directory each session. Agree the host
label with the user (`$ARGUMENTS` if given, otherwise propose the hostname-derived default from
step 1), then:

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" init --host <label>
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" identity
```

If this hub already uses a different convention for this machine, `--fixed-id <id>` uses that
exact string instead. Say that it falls outside the canonical form and that the protocol expects
a one-time cutover: sweep the old inbox once, then stop using the old name.

## 3. The model's path to the hub

Run `claude mcp list` and find the MemPalace server. The hooks only need the `mempalace_*` tools
to exist in the session. The server name becomes a prefix on the tool names and nothing else.

If there is none, help the user add one (from the MemPalace remote-server guide):

```
claude mcp add --transport http --scope user mempalace https://hub.example.com/mcp \
  --header "Authorization: Bearer $MEMPALACE_MCP_HTTP_TOKEN"
```

For a hub behind an OAuth login, the same without `--header`, then `/mcp` and Authenticate.

## 4. The hook's path to the hub

The hooks run before the model exists, so the live check and the wake check need their own
path. Pick one with the user:

- HTTP hub with its static bearer token: `--url <hub>/mcp` plus `--token-env NAME` (the hook
  reads that variable) or `--token-command "<command that prints the token>"` (a keychain or
  secret-store lookup, so the token never enters the config file).
- A local `mempalace-mcp` that proxies to a local hub: `--stdio-command "mempalace-mcp"`.
- A hub that only accepts OAuth logins: `--transport none`. The hook cannot borrow the model's
  OAuth token, so the live check and the wake check are off and the model does the sweeps itself.

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" init <transport flags>
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" probe
```

A reachable hub prints its drawer count and the open tasks addressed to this identity. A 401
means the token is missing or wrong, or the hub is OAuth-only.

## 5. The rules block

Install MemPalace's canonical shared-brain block into the instruction file (default
`~/.claude/CLAUDE.md`). Show the diff first and ask before writing:

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" rules install
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" rules install --write
```

The block sits between `<!-- mempalace-shared-brain:start ... -->` and
`<!-- mempalace-shared-brain:end -->` markers and is replaced in place on later updates. If the
file already has a hand-written section covering the same ground, point it out: two statements
of one protocol drift apart. The user decides what to remove.

## 6. Finish

Tell the user: every new session now starts with the identity, the rules-block status, the inbox
cursor and (with a transport) the live check. `/mempalace-sharedbrain:inbox` sweeps the inbox,
`/mempalace-sharedbrain:listen` arms the wake check when a coordination loop starts, and the
config lives at the path from `setup.sh path`.
