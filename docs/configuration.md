# Configuration

One JSON file per machine. `scripts/setup.sh` writes it; you can also edit it by hand.

| Path | Purpose | Override |
|---|---|---|
| `~/.config/mempalace-sharedbrain/config.json` | Settings | `MEMPALACE_SHAREDBRAIN_CONFIG` |
| `~/.local/state/mempalace-sharedbrain/` | Checkpoint counters, pending snapshots, `hook.log` | `MEMPALACE_SHAREDBRAIN_STATE` |

`$XDG_CONFIG_HOME` and `$XDG_STATE_HOME` are honoured when set. `MEMPALACE_SHAREDBRAIN_PYTHON`
pins the interpreter the hooks use; otherwise they try Homebrew, `/usr/local`, `$PATH`, then
`/usr/bin/python3`, and print `{}` (do nothing) if none exists.

## Keys

```json
{
  "agent_id": "office-desktop",
  "hub": {
    "transport": "auto",
    "url": "https://hub.example.com/mcp",
    "token_env": "MEMPALACE_MCP_HTTP_TOKEN",
    "token_command": "",
    "stdio_command": [],
    "timeout_seconds": 8
  },
  "probe": {
    "enabled": true,
    "inbox_limit": 10
  },
  "canonical_drawers": [
    {"id": "drawer_team_onboarding_0123456789abcdef01234567", "note": "house rules"}
  ],
  "extra_context": [],
  "checkpoint": {
    "save_interval": 15
  }
}
```

| Key | Default | Meaning |
|---|---|---|
| `agent_id` | hostname, lowercased, non-alphanumerics to `-` | Identity on every write and the address for delegated tasks. Set it explicitly on any machine whose hostname is not the id you want. |
| `hub.transport` | `auto` | `http`, `stdio` or `none`. `auto` picks `stdio` when `stdio_command` is set, else `http` when `url` is set, else `none`. |
| `hub.url` | empty | The MCP endpoint for `http`, including the `/mcp` path. A remote hub or a local `mempalace serve`. |
| `hub.token_env` | `MEMPALACE_MCP_HTTP_TOKEN` | Environment variable holding the bearer token. Checked first. |
| `hub.token_command` | empty | Shell command that prints the token (keychain, `secret-tool`, `op read`...). Used when the variable is unset. The token never lands in the config file. |
| `hub.stdio_command` | empty | Command and arguments for a stdio MCP server, as a list or one string. The hook starts it, asks its questions, and stops it. |
| `hub.timeout_seconds` | `8` | Total time budget for the live check. The hook's own timeout is 25 seconds. |
| `probe.enabled` | `true` | Run the live check at session start. Set `false` for a hub that only accepts OAuth logins. |
| `probe.inbox_limit` | `10` | How many open task requests to fetch. |
| `canonical_drawers` | `[]` | Drawers the bootstrap tells the model to fetch by id every session. Each entry is `{"id", "note"}` or a bare id string. |
| `extra_context` | `[]` | Lines appended to the bootstrap block as written. For rules that must load every session and have no better home. |
| `checkpoint.save_interval` | `15` | Human turns between checkpoint reminders. `0` disables the Stop hook's reminder. |

## Three common setups

Local palace over stdio, the same server Claude Code uses:

```
scripts/setup.sh init --agent-id my-laptop --stdio-command "mempalace-mcp"
```

Local or remote `mempalace serve` with its static token, token kept in the macOS keychain:

```
scripts/setup.sh init --agent-id my-laptop \
  --url http://127.0.0.1:8765/mcp \
  --token-env "" \
  --token-command "security find-generic-password -s MEMPALACE_MCP_HTTP_TOKEN -w"
```

The same on Linux with libsecret:

```
scripts/setup.sh init --agent-id my-laptop \
  --url https://hub.example.com/mcp \
  --token-env "" \
  --token-command "secret-tool lookup service MEMPALACE_MCP_HTTP_TOKEN account my-laptop"
```

Remote hub behind an OAuth login (see [hub-setup.md](hub-setup.md)). The model authenticates
through Claude Code's own OAuth flow. A hook script cannot borrow that token, so the live check is
turned off and the model does the inbox check itself from the bootstrap block:

```
scripts/setup.sh init --agent-id my-laptop --transport none
```

If the hub host also exposes the plain `mempalace serve` port on a private network (a VPN or
tailnet), point `--url` at that and the live check works again with the hub's static token.

## Checking it

```
scripts/setup.sh show     # effective settings and where they came from
scripts/setup.sh probe    # what the SessionStart hook will see
tail -f ~/.local/state/mempalace-sharedbrain/hook.log
```

The log records every hook run: session id, source, whether the palace was reached, how many
tasks were open and unacked, and any snapshot written. It rotates at 1 MB.
