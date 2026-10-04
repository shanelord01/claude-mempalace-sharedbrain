"""Shared helpers for the mempalace-sharedbrain hooks and scripts.

Configuration lives in one JSON file per machine (XDG config dir by default)
and hook state (counters, snapshots, log) in the XDG state dir. Both paths can
be overridden with environment variables, which the tests use.
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
LOG_FILE = os.path.join(STATE_DIR, "hook.log")
LOG_MAX_BYTES = 1024 * 1024

DEFAULTS = {
    "agent_id": "",
    "hub": {
        "transport": "auto",
        "url": "",
        "token_env": "MEMPALACE_MCP_HTTP_TOKEN",
        "token_command": "",
        "stdio_command": [],
        "timeout_seconds": 8,
    },
    "probe": {
        "enabled": True,
        "inbox_limit": 10,
    },
    "canonical_drawers": [],
    "extra_context": [],
    "checkpoint": {
        "save_interval": 15,
    },
}


def ensure_dirs():
    os.makedirs(PENDING_DIR, exist_ok=True)


def rotate_log():
    try:
        if os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
            os.replace(LOG_FILE, LOG_FILE + ".1")
    except OSError:
        pass


def log(message):
    try:
        ensure_dirs()
        with open(LOG_FILE, "a") as fh:
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
    cfg["_config_file"] = CONFIG_FILE
    cfg["_config_present"] = bool(raw)
    return cfg


def save_config(cfg):
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(clean, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, CONFIG_FILE)


def default_agent_id():
    host = socket.gethostname().split(".")[0].lower()
    host = re.sub(r"[^a-z0-9]+", "-", host).strip("-")
    return host or "claude-code"


def agent_id(cfg):
    return (cfg.get("agent_id") or "").strip() or default_agent_id()


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


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")
    sys.stdout.flush()
