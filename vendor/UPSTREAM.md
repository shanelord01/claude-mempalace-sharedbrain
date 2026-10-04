# Vendored MemPalace files

These files are copied unchanged from the MemPalace repository (MIT licence,
https://github.com/MemPalace/mempalace). The plugin renders them exactly as
`mempalace rules` does, so a machine without the `mempalace` package gets the
same block as one with it. When the package is installed, the plugin uses it
instead and these copies are not read.

| File | Upstream path | Version | Commit | sha256 |
|---|---|---|---|---|
| `shared_brain_rules.md` | `mempalace/instructions/shared_brain_rules.md` | 3.10.0 (release; identical on `develop` 43122ae) | 22fd87f09c19d5ffb2d6966486483353937931c0 | aad08b8d57bf5f13dacdec2a4e6e790ef324642c5fde28adad0dde9d50b0d688 |

Upstream keeps `shared_brain_rules.md` test-pinned to the System-Prompt Snippet
in `integrations/shared/coordination-protocol.md`, the single source of truth
for the shared-brain protocol.

## Refreshing

```
scripts/setup.sh vendor-check          # compares against the upstream main branch
scripts/setup.sh vendor-check --update # replaces the copy and rewrites this table
```
