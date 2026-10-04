---
description: Show the shared-brain fleet state: hub status, recent MCP clients, and mesh peers when hubs sync their logstreams
---

# Peers and fleet state

1. Call `mempalace_mesh_peers` through the session's MCP tools. That is the same payload as the
   hub's `GET /sync/peers`, and it works on every machine.
2. For hub uptime, writer mode, request counts and recent clients, the hub's `GET /statusz` needs
   its token, which only a hook-side transport has. Check with
   `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" show`: when `hub.transport` is `http`, run
   `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" peers` for `/statusz`. When it is `none` (or
   `auto` with no URL), skip it and say `/statusz` was not read; that is the normal setup, not an
   error.

Report:

- Hub: MemPalace version, uptime, writer mode, request counts by status.
- Recent clients: identity hints, user agents and last seen, so the user can tell which machines
  and surfaces are actually talking to the hub.
- Mesh: configured peers, whether each was reachable, its last sync outcome and version vector,
  and replicas known only through gossip. A hub with no peers reports an empty estate, which is
  normal for a single-hub fleet.

Say plainly what peer sync does and does not cover, from the MemPalace shared-brain guide: peer
sync covers the logstream only, so agents on synced hubs share an inbox but not recall. For one
shared memory, every agent points at a single hub.

