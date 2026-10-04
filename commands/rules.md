---
description: Render, check or install MemPalace's canonical shared-brain rules block in this machine's CLAUDE.md, in place, without needing the mempalace package
argument-hint: "[render | check | install]"
---

# The shared-brain rules block

MemPalace's `mempalace rules --host H --harness claude --project P` prints the canonical protocol
block for an agent's instruction file, wrapped in markers so a later render replaces it in place.
This plugin renders the same block from a vendored copy of the same template when the package is
not installed, and uses the CLI when it is.

`$ARGUMENTS` picks the action (default `check`).

- `render`: print the block as it would be installed.
  `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" rules render`
- `check`: report whether the instruction file has the block and whether it matches.
  `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" rules check`
  Exit 0 current, 3 missing, 4 stale.
- `install`: show the diff, then on the user's confirmation apply it.
  `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" rules install`
  `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" rules install --write`
  The previous file is saved under the plugin's state directory before writing.

Never write without showing the diff and getting a yes. The block's wording belongs to MemPalace
(`integrations/shared/coordination-protocol.md` in its repository); do not edit it locally. If the
user wants it changed, the change goes upstream. If the vendored template may be behind upstream,
`bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" vendor-check` compares them.

Options: `--host`, `--project` (the example project name shown in the block; the runtime identity
composes the real one from the workspace), `--mcp light` for the 3-tool lightweight server,
`--target FILE` for an instruction file other than `~/.claude/CLAUDE.md`.
