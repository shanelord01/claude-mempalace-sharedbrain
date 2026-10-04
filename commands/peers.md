---
description: Show the shared-brain fleet state: hub status, recent MCP clients, and mesh peers when hubs sync their logstreams
---

# Peers and fleet state

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" peers
```

This calls `mempalace_mesh_peers` (the same payload as the hub's `GET /sync/peers`) and, when
the hook has the hub's token, `GET /statusz`. Report:

- Hub: MemPalace version, uptime, writer mode, request counts by status.
- Recent clients: identity hints, user agents and last seen, so the user can tell which machines
  and surfaces are actually talking to the hub.
- Mesh: configured peers, whether each was reachable, its last sync outcome and version vector,
  and replicas known only through gossip. A hub with no peers reports an empty estate, which is
  normal for a single-hub fleet.

Say plainly what peer sync does and does not cover, from the MemPalace shared-brain guide: peer
sync covers the logstream only, so agents on synced hubs share an inbox but not recall. For one
shared memory, every agent points at a single hub.

If the hook has no transport to the hub, call `mempalace_mesh_peers` yourself through the MCP
tools and report that `/statusz` was not read.
