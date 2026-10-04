# Configuration

One JSON file per machine. `scripts/setup.sh` writes it; you can also edit it by hand.

| Path | Purpose | Override |
|---|---|---|
| `~/.config/mempalace-sharedbrain/config.json` | Settings | `MEMPALACE_SHAREDBRAIN_CONFIG` |
| `~/.local/state/mempalace-sharedbrain/` | Inbox cursors, watch state, snapshots, saved instruction files, `hook.log` | `MEMPALACE_SHAREDBRAIN_STATE` |

`$XDG_CONFIG_HOME` and `$XDG_STATE_HOME` are honoured when set. `MEMPALACE_SHAREDBRAIN_PYTHON`
pins the interpreter the hooks use; otherwise they try Homebrew, `/usr/local`, `$PATH`, then
`/usr/bin/python3`, and print `{}` (do nothing) if none exists. Everything under the state
directory is created readable by the current user only.

## Keys

```json
{
  "identity": {"host": "office-desktop", "harness": "claude", "project": "auto", "fixed": ""},
  "rules": {"target": "~/.claude/CLAUDE.md", "mcp": "full", "project_example": "", "prefer_cli": true},
  "hub": {
    "transport": "auto",
    "url": "https://hub.example.com/mcp",
    "token_env": "MEMPALACE_MCP_HTTP_TOKEN",
    "token_command": "",
    "stdio_command": [],
    "timeout_seconds": 8
  },
  "probe": {"enabled": true, "inbox_limit": 10},
  "wake": {"types": ["task.request", "task.reply", "patch.ready"], "limit": 50},
  "checkpoint": {"save_interval": 15},
  "extra_context": []
}
```

| Key | Default | Meaning |
|---|---|---|
| `identity.host` | hostname, sanitised | The stable machine label in `host:harness:project`. The protocol wants a label you choose, not a DHCP hostname, so set it. |
| `identity.harness` | `claude` | Runtime family. |
| `identity.project` | `auto` | `auto` takes the workspace name from the session's working directory each time, as the protocol describes. A fixed value pins it. |
| `identity.fixed` | empty | Use this exact string as the identity instead of composing one. For hubs that already use another convention. The session context says when an identity is outside the canonical form. A 0.1.x `agent_id` key is read as this. |
| `rules.target` | `~/.claude/CLAUDE.md` | The instruction file the rules block is installed into and checked against. |
| `rules.mcp` | `full` | `light` renders tool names for MemPalace's 3-tool lightweight server. |
| `rules.project_example` | workspace name | The example project shown in the block's "e.g." line. The runtime identity composes the real one. |
| `rules.prefer_cli` | `true` | Render with the installed `mempalace` CLI when there is one, so a newer upstream template wins over the vendored copy. |
| `hub.transport` | `auto` | `http`, `stdio` or `none`. `auto` picks `stdio` when `stdio_command` is set, else `http` when `url` is set, else `none`. |
| `hub.url` | empty | The hub's MCP endpoint, including `/mcp`. `/healthz` and `/statusz` are derived from it. |
| `hub.token_env` | `MEMPALACE_MCP_HTTP_TOKEN` | Environment variable holding the bearer token. Checked first. |
| `hub.token_command` | empty | Command (no shell) that prints the token: a keychain or secret-store lookup. Used when the variable is unset. The token never lands in the config file. |
| `hub.stdio_command` | empty | Command for a stdio MCP server such as `mempalace-mcp`, which proxies to a local hub. The hook starts it, asks, stops it. |
| `hub.timeout_seconds` | `8` | Total time budget for one hook's hub traffic. |
| `probe.enabled` | `true` | Run the live check at session start. |
| `probe.inbox_limit` | `10` | How many events to fetch per inbox query. |
| `wake.types` | `task.request`, `task.reply`, `patch.ready` | Default event types a `listen arm` watches for. The protocol's recommended set. |
| `wake.limit` | `50` | Events examined per wake check. |
| `checkpoint.save_interval` | `15` | Human turns between checkpoint requests. `0` disables the Stop hook's request. |
| `extra_context` | `[]` | Lines appended to the session-start block as written. For machine notes that must load every session and have no better home. |

## Three common setups

A remote hub with its static token, token kept in the macOS keychain:

```
scripts/setup.sh init --host mac \
  --url https://hub.example.com/mcp --token-env "" \
  --token-command "security find-generic-password -s MEMPALACE_MCP_HTTP_TOKEN -w"
```

The same on Linux with libsecret:

```
scripts/setup.sh init --host office-desktop \
  --url https://hub.example.com/mcp --token-env "" \
  --token-command "secret-tool lookup service MEMPALACE_MCP_HTTP_TOKEN account office-desktop"
```

A hub behind an OAuth login (see [hub-setup.md](hub-setup.md)). The model authenticates through
Claude Code's own OAuth flow. A hook cannot borrow that token, so the live check and the wake
check are off and the model runs the sweeps itself from the rules block:

```
scripts/setup.sh init --host office-desktop --transport none
```

If the same hub is also reachable with its static token on a private path (a tailnet name, a
VPN address), point `--url` at that path and the hook's checks work again.

## State files

| File | Holds |
|---|---|
| `cursors/<identity>.json` | The inbox cursor: id of the last event this identity processed. `setup.sh cursor get|set|clear`. |
| `watch/<identity>.json` | Armed watch: types, optional correlation id and topic, and the watch cursor. `setup.sh listen arm|disarm|status`. |
| `pending/<session>.md` | Pre-compaction snapshot awaiting filing. |
| `rules/<file>.<timestamp>` | The instruction file as it was before each `rules install --write`. |
| `hook.log` | One line per hook run. Rotates at 1 MB. |

Identity file names follow the MemPalace CLI: underscores doubled, then colons turned into
underscores, so two identities never share a file.

## Checking it

```
scripts/setup.sh show       # effective settings, identity, cursor, listening state
scripts/setup.sh probe      # what the SessionStart hook will see
scripts/setup.sh rules check
tail -f ~/.local/state/mempalace-sharedbrain/hook.log
```
