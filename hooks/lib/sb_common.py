"""Shared helpers for the mempalace-sharedbrain hooks and scripts.

Configuration lives in one JSON file per machine (XDG config dir by default)
and hook state (inbox cursors, watch state, snapshots, log) in the XDG state
dir. Both paths can be overridden with environment variables, which the tests
use.

Identity follows the MemPalace shared-brain protocol: ``host:harness:project``,
where host is a stable label for the machine, harness is ``claude`` and project
is the current workspace name. ``identity.fixed`` overrides the whole string
for estates that use another convention.
"""
import copy
import json
import os
import re
import socket
import sys
import time

CONFIG_FILE = os.environ.get("MEMPALACE_SHAREDBRAIN_CONFIG") or os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "mempalace-sharedbrain",
    "config.json",
)
STATE_DIR = os.environ.get("MEMPALACE_SHAREDBRAIN_STATE") or os.path.join(
    os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
    "mempalace-sharedbrain",
)
PENDING_DIR = os.path.join(STATE_DIR, "pending")
CURSOR_DIR = os.path.join(STATE_DIR, "cursors")
WATCH_DIR = os.path.join(STATE_DIR, "watch")
PRESENCE_DIR = os.path.join(STATE_DIR, "presence")
BRIDGE_DIR = os.path.join(STATE_DIR, "bridge")
BRIDGE_LOCK_STALE_SECONDS = 6 * 3600
LOG_FILE = os.path.join(STATE_DIR, "hook.log")
LOG_MAX_BYTES = 1024 * 1024

# Same shape upstream validates in `mempalace rules`.
COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

DEFAULTS = {
    "identity": {
        "host": "",
        "harness": "claude",
        "project": "auto",
        "fixed": "",
    },
    "rules": {
        "target": "~/.claude/CLAUDE.md",
        "mcp": "full",
        "project_example": "",
        "prefer_cli": True,
    },
    "hub": {
        "transport": "auto",
        "url": "",
        "token_env": "MEMPALACE_MCP_HTTP_TOKEN",
        "token_command": "",
        "oauth": {
            "issuer": "",
            "token_url": "",
            "client_id": "",
            "client_secret_env": "",
            "client_secret_command": "",
            "scope": "mempalace:use",
            "resource": "",
        },
        "stdio_command": [],
        "timeout_seconds": 8,
        "mcp_server": "",
    },
    "probe": {
        "enabled": True,
        "inbox_limit": 10,
        "model_sweep": True,
    },
    "wake": {
        "types": ["task.request", "task.reply", "patch.ready"],
        "limit": 50,
    },
    "checkpoint": {
        "save_interval": 15,
    },
    "capabilities": {
        "enabled": True,
        "profile_drawer_id": "",
        "wing": "fleet",
        "room": "machines",
        "custom": {},
    },
    "presence": {
        "enabled": True,
        "wing": "",
        "room": "presence",
        "interval_minutes": 30,
    },
    # The hub as a message bridge (docs/bridge.md): listening is on unless switched off, and new
    # mail starts a turn. mode: read (every message is reported only), act (tasks addressed to this
    # identity by name, signed with a key the person approved, are carried out) or off (mail waits
    # for the next prompt).
    "bridge": {
        "mode": "read",
        "max_turns_per_hour": 12,
        "max_turns_per_thread": 4,
        # Signing a task another machine will carry out: ask each time, ask once per recipient per
        # session (the default), or sign without asking (never in a turn hub mail started or carried).
        "sign_tasks": "session",
    },
    "extra_context": [],
}


def ensure_dirs():
    """State dirs, readable by this user only (snapshots hold conversation text)."""
    for path in (STATE_DIR, PENDING_DIR, CURSOR_DIR, WATCH_DIR, PRESENCE_DIR, BRIDGE_DIR):
        os.makedirs(path, exist_ok=True)
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass


def open_private(path, mode="w"):
    """Open a file for writing that only this user can read, whatever the umask."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if "a" in mode else os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
    except OSError:
        pass
    return os.fdopen(fd, mode)


def rotate_log():
    try:
        if os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
            os.replace(LOG_FILE, LOG_FILE + ".1")
    except OSError:
        pass


def log(message):
    try:
        ensure_dirs()
        with open_private(LOG_FILE, "a") as fh:
            fh.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except OSError:
        pass


def _merge(base, override):
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config():
    try:
        with open(CONFIG_FILE) as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict):
            raise ValueError("top level is not an object")
    except FileNotFoundError:
        raw = {}
    except (OSError, ValueError) as exc:
        log("config unreadable at %s: %s" % (CONFIG_FILE, exc))
        raw = {}
    cfg = _merge(DEFAULTS, raw)
    # 0.1.x wrote a flat agent_id; carry it as a fixed identity.
    if raw.get("agent_id") and not cfg["identity"].get("fixed"):
        cfg["identity"]["fixed"] = str(raw["agent_id"]).strip()
    cfg["_config_file"] = CONFIG_FILE
    cfg["_config_present"] = bool(raw)
    return cfg


def save_config(cfg):
    clean = {k: v for k, v in cfg.items() if not k.startswith("_") and k != "agent_id"}
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open_private(tmp, "w") as fh:
        json.dump(clean, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, CONFIG_FILE)


def component(value, fallback):
    """Coerce a string into a valid identity component, or return fallback."""
    text = re.sub(r"[^a-z0-9._-]+", "-", str(value or "").strip().lower()).strip("-._")
    text = re.sub(r"^[^a-z0-9]+", "", text)
    return text if text and COMPONENT_RE.fullmatch(text) else fallback


def default_host_label():
    return component(socket.gethostname().split(".")[0], "host")


def host_label(cfg):
    return component(cfg["identity"].get("host"), "") or default_host_label()


def project_from_cwd(cwd=None):
    cwd = cwd or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return component(os.path.basename(os.path.normpath(cwd)), "workspace")


def identity(cfg, cwd=None):
    """The from_agent identity for this session."""
    fixed = (cfg["identity"].get("fixed") or "").strip()
    if fixed:
        return fixed
    project_setting = (cfg["identity"].get("project") or "auto").strip()
    project = project_from_cwd(cwd) if project_setting in ("", "auto") else component(project_setting, "workspace")
    harness = component(cfg["identity"].get("harness"), "claude")
    return "%s:%s:%s" % (host_label(cfg), harness, project)


def diary_name(ident):
    """A name mempalace_diary_write accepts: its sanitize_name rejects colons, so they become underscores."""
    return ident.replace(":", "_")


def identity_is_canonical(ident):
    parts = ident.split(":")
    return len(parts) == 3 and all(COMPONENT_RE.fullmatch(p) for p in parts)


def identity_filename(ident):
    """Mirror the CLI: double any underscore, then turn colons into underscores."""
    return ident.replace("_", "__").replace(":", "_")


def _read_json(path):
    try:
        with open(path) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path, data):
    ensure_dirs()
    with open_private(path, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def cursor_path(ident):
    return os.path.join(CURSOR_DIR, identity_filename(ident) + ".json")


def read_cursor(ident):
    """The inbox cursor: id of the last event this identity processed, or ''."""
    return str(_read_json(cursor_path(ident)).get("since_event_id") or "")


def write_cursor(ident, event_id):
    _write_json(cursor_path(ident), {
        "identity": ident,
        "since_event_id": event_id,
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })


def clear_cursor(ident):
    try:
        os.remove(cursor_path(ident))
    except OSError:
        pass


def watch_path(ident):
    return os.path.join(WATCH_DIR, identity_filename(ident) + ".json")


def read_watch(ident):
    """Armed watch state for this identity, or {} when not listening."""
    return _read_json(watch_path(ident))


def write_watch(ident, state):
    state = dict(state)
    state["identity"] = ident
    state["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write_json(watch_path(ident), state)


def clear_watch(ident):
    try:
        os.remove(watch_path(ident))
    except OSError:
        pass


def presence_path(ident):
    return os.path.join(PRESENCE_DIR, "%s.json" % identity_filename(ident))


def read_presence(ident):
    return _read_json(presence_path(ident))


def write_presence(ident, drawer_id):
    _write_json(presence_path(ident), {"identity": ident, "drawer_id": drawer_id,
                                       "updated": time.strftime("%Y-%m-%dT%H:%M:%S")})


def bridge_lock(ident, event_id, owner):
    """Takes this identity's lock on one event, so of two sessions sharing the identity only one acts
    on it. True when this owner holds it (newly, already, or over a stale lock)."""
    ensure_dirs()
    folder = os.path.join(BRIDGE_DIR, identity_filename(ident))
    os.makedirs(folder, mode=0o700, exist_ok=True)
    path = os.path.join(folder, safe_id(event_id) + ".lock")
    record = {"event_id": event_id, "owner": owner, "taken": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        held = _read_json(path)
        if held.get("owner") == owner:
            return True
        try:
            age = time.time() - os.path.getmtime(path)
        except OSError:
            age = 0
        if age < BRIDGE_LOCK_STALE_SECONDS:
            return False
        _write_json(path, record)
        return True
    with os.fdopen(fd, "w") as fh:
        json.dump(record, fh)
    return True


def bridge_state_path(ident):
    return os.path.join(BRIDGE_DIR, identity_filename(ident) + ".threads.json")


def read_bridge_state(ident):
    state = _read_json(bridge_state_path(ident))
    state.setdefault("threads", {})
    state.setdefault("turns", [])
    return state


def write_bridge_state(ident, state):
    _write_json(bridge_state_path(ident), state)


def bridge_turn(ident, threads, per_thread, per_hour, now=None):
    """Counts one automatic turn covering `threads`. Returns {allowed, reason, threads: {t: {turns,
    is_last}}}. A paused thread, or a full hour, refuses the turn and counts nothing."""
    now = time.time() if now is None else now
    state = read_bridge_state(ident)
    recent = [t for t in state["turns"] if now - t < 3600]
    paused = [t for t in threads if (state["threads"].get(t) or {}).get("paused")]
    if paused:
        return {"allowed": False, "reason": "paused", "paused": paused, "threads": {}}
    if len(recent) >= per_hour:
        return {"allowed": False, "reason": "hourly limit", "paused": [], "threads": {}}
    out = {}
    for t in threads:
        entry = state["threads"].get(t) or {"turns": 0, "paused": False}
        entry["turns"] = int(entry.get("turns", 0)) + 1
        entry["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
        is_last = entry["turns"] >= per_thread
        if is_last:
            entry["paused"] = True
        state["threads"][t] = entry
        out[t] = {"turns": entry["turns"], "is_last": is_last}
    state["turns"] = recent + [now]
    # Keep the file small: forget threads untouched for a fortnight that are not paused.
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - 14 * 86400))
    state["threads"] = {k: v for k, v in state["threads"].items() if v.get("paused") or v.get("updated", "") >= cutoff}
    write_bridge_state(ident, state)
    return {"allowed": True, "reason": "", "paused": [], "threads": out}


def bridge_continue(ident, threads=None):
    """Resets the count of the given threads (every paused one when none are given). Returns them."""
    state = read_bridge_state(ident)
    names = list(threads or [k for k, v in state["threads"].items() if v.get("paused")])
    for name in names:
        state["threads"].pop(name, None)
    write_bridge_state(ident, state)
    return names


def bridge_paused(ident):
    return sorted(k for k, v in read_bridge_state(ident)["threads"].items() if v.get("paused"))


def safe_id(value):
    return re.sub(r"[^a-zA-Z0-9_.\-]", "", str(value or "")) or "unknown"


def read_hook_input():
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def plugin_root():
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return env
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def plugin_version():
    try:
        with open(os.path.join(plugin_root(), ".claude-plugin", "plugin.json")) as fh:
            return json.load(fh).get("version", "?")
    except (OSError, ValueError):
        return "?"


MOD_MARK = "mempalace_sharedbrain_mod"


def mod_active(payload):
    """True when the plugin's mod (Claude Code function hooks) is loaded and has tagged this event:
    it then makes the hub calls itself, so the command hooks leave those parts out."""
    return bool(isinstance(payload, dict) and payload.get(MOD_MARK))


def clean_line(value, limit):
    """One printable line, control characters removed, whitespace collapsed, truncated."""
    text = "".join(ch if ch.isprintable() else " " for ch in str(value or ""))
    text = " ".join(text.split())
    return text[:limit]


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")
    sys.stdout.flush()
