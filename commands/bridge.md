---
description: Show the hub bridge for this identity (mode, limits, threads with automatic turns), continue a thread paused for you, or change the mode
argument-hint: "[status | continue [thread ...] | mode act|read|off | sign ask|session|auto]"
---

# The hub bridge

With the bridge on, hub mail addressed to this identity starts a turn of its own: within a minute
while a session runs, and as soon as the next session starts when none does. In mode `read`, the
default, every message is read and reported. In mode `act`, tasks sent to this identity by name and
signed by a machine this one trusts (`/mempalace-sharedbrain:trust`) are carried out too. The protocol is in `docs/bridge.md` in the plugin.

To stop two agents answering each other forever, a thread gets at most 4 automatic turns (and the
bridge at most 12 an hour). The last turn summarises the thread, tells the other agent it has
paused, and asks you whether to go on. Until you do, mail on that thread waits for your prompts.

Where the plugin's mod is loaded it answers this command itself. Otherwise run the matching line
and report its output. `$ARGUMENTS` defaults to `status`.

```
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" bridge status
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" bridge continue <thread> [<thread> ...]   # or --all
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" set bridge.mode act|read|off
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" set bridge.sign_tasks ask|session|auto
```

`sign` sets how a task this machine sends gets signed: `session` (the default) asks once per
recipient per session, `ask` asks every time, `auto` never asks. Only change it when the person asks.

Modes: `act` carries out tasks as above, `read` only reads and reports every message, `off` starts
no turns (mail waits for your next prompt, and listening follows `/mempalace-sharedbrain:listen`).
The mode is set per machine. Only change it when the person asks.
