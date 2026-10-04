"""Configure and operate the plugin on this machine.

    setup.py show
    setup.py path
    setup.py identity [--cwd DIR]
    setup.py init [--host LABEL] [--harness X] [--project auto|NAME]
                  [--fixed-id ID | --no-fixed-id]
                  [--transport auto|http|stdio|none] [--url URL] [--token-env NAME]
                  [--token-command CMD] [--stdio-command "CMD ARGS"] [--timeout S]
                  [--rules-target FILE] [--mcp full|light] [--project-example NAME]
                  [--save-interval N] [--no-probe | --probe]
    setup.py set KEY VALUE              dotted key, JSON value if it parses, else a string
    setup.py probe                      what the SessionStart hook will see
    setup.py cursor get | set EVENT_ID | clear
    setup.py listen arm [--type T ...] [--correlation-id ID] [--topic T] [--from EVENT_ID]
    setup.py listen cursor EVENT_ID     advance the watch cursor (the model does this after a sweep it ran itself)
    setup.py listen disarm | status
    setup.py peers                      mempalace_mesh_peers and /statusz
    setup.py rules render|check|install [--write] [--host ..] [--project ..] [--mcp ..] [--target ..]
    setup.py vendor-check [--update]    compare the vendored rules template with upstream
    setup.py capabilities probe [--json]   what this machine can do, in the plugin's vocabulary
    setup.py capabilities status        probe compared with what was last published to the hub
    setup.py capabilities plan          the facts and profile drawer to publish (the model makes the MCP calls)
    setup.py capabilities published HASH DRAWER_ID   record a completed publish
    setup.py capabilities check REQ...  does this machine meet requirements like xcode>=27 memory-gb>=32

init keeps any existing settings and changes only the flags you pass.
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
import sb_common as C  # noqa: E402

UPSTREAM_RAW = "https://raw.githubusercontent.com/MemPalace/mempalace/main/"
UPSTREAM_API_COMMIT = "https://api.github.com/repos/MemPalace/mempalace/commits/main"


def _print_config(cfg):
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    print(json.dumps(clean, indent=2, sort_keys=True))


def cmd_show(cfg, _args):
    print("config file: %s%s" % (cfg["_config_file"], "" if cfg["_config_present"] else " (not written yet, showing defaults)"))
    ident = C.identity(cfg)
    print("identity:    %s%s" % (ident, "" if C.identity_is_canonical(ident) else "  (not in host:harness:project form)"))
    print("cursor:      %s" % (C.read_cursor(ident) or "(none)"))
    watch = C.read_watch(ident)
    print("listening:   %s" % ("armed, types %s, since %s" % (", ".join(watch.get("types") or []), watch.get("since_event_id") or "(start)") if watch.get("armed") else "no"))
    _print_config(cfg)


def cmd_path(_cfg, _args):
    print(C.CONFIG_FILE)


def cmd_identity(cfg, args):
    ident = C.identity(cfg, args.cwd)
    print(C.diary_name(ident) if args.diary else ident)
    return 0


def cmd_init(cfg, args):
    ident = cfg["identity"]
    if args.host is not None:
        ident["host"] = C.component(args.host, "")
        if not ident["host"]:
            print("--host must be a lowercase token (letters, digits, '.', '_', '-')", file=sys.stderr)
            return 1
    if args.harness is not None:
        ident["harness"] = C.component(args.harness, "claude")
    if args.project is not None:
        ident["project"] = args.project if args.project == "auto" else C.component(args.project, "workspace")
    if args.fixed_id is not None:
        ident["fixed"] = args.fixed_id.strip()
    if args.no_fixed_id:
        ident["fixed"] = ""
    rules = cfg["rules"]
    if args.rules_target is not None:
        rules["target"] = args.rules_target
    if args.mcp is not None:
        rules["mcp"] = args.mcp
    if args.project_example is not None:
        rules["project_example"] = C.component(args.project_example, "")
    hub = cfg["hub"]
    if args.transport:
        hub["transport"] = args.transport
    if args.url is not None:
        hub["url"] = args.url
    if args.token_env is not None:
        hub["token_env"] = args.token_env
    if args.token_command is not None:
        hub["token_command"] = args.token_command
    if args.stdio_command is not None:
        hub["stdio_command"] = shlex.split(args.stdio_command) if args.stdio_command else []
    if args.timeout is not None:
        hub["timeout_seconds"] = args.timeout
    if args.save_interval is not None:
        cfg["checkpoint"]["save_interval"] = args.save_interval
    if args.no_probe:
        cfg["probe"]["enabled"] = False
    if args.probe:
        cfg["probe"]["enabled"] = True
    C.save_config(cfg)
    print("wrote %s" % C.CONFIG_FILE)
    cmd_show(C.load_config(), args)
    return 0


def _coerce(value):
    try:
        return json.loads(value)
    except ValueError:
        return value


def cmd_set(cfg, args):
    node = cfg
    keys = args.key.split(".")
    for key in keys[:-1]:
        if not isinstance(node.get(key), dict):
            node[key] = {}
        node = node[key]
    node[keys[-1]] = _coerce(args.value)
    C.save_config(cfg)
    print("set %s" % args.key)
    return 0


def cmd_probe(cfg, _args):
    import sb_probe as P
    ident = C.identity(cfg)
    outcome = P.run_probe(cfg, ident, C.read_cursor(ident))
    print(json.dumps(outcome, indent=2))
    print()
    print(P.format_probe(outcome, ident))
    return 0 if outcome.get("reachable") or outcome.get("transport") == "none" else 1


def cmd_cursor(cfg, args):
    ident = C.identity(cfg)
    if args.action == "get":
        print(C.read_cursor(ident) or "")
        return 0
    if args.action == "clear":
        C.clear_cursor(ident)
        print("cursor cleared for %s" % ident)
        return 0
    event_id = (args.event_id or "").strip()
    if not re.fullmatch(r"evt_[A-Za-z0-9_.\-]+", event_id):
        print("cursor set needs an event id like evt_20260101T000000_abcdef012345", file=sys.stderr)
        return 1
    C.write_cursor(ident, event_id)
    print("cursor for %s is now %s" % (ident, event_id))
    return 0


def _tip_event_id(cfg, ident):
    """Newest event id addressed to this identity, or '' when unknown."""
    import sb_probe as P
    client = None
    try:
        client, transport, _token = P.open_client(cfg)
        if client is None:
            return ""
        client.initialize()
        events = P.list_events(client, to_agent=ident, limit=1)
        return (events[0].get("id") or "") if events else ""
    except Exception:
        return ""
    finally:
        if client is not None:
            client.close()


def cmd_listen(cfg, args):
    ident = C.identity(cfg)
    if args.action == "status":
        watch = C.read_watch(ident)
        print(json.dumps(watch or {"armed": False, "identity": ident}, indent=2))
        return 0
    if args.action == "cursor":
        watch = C.read_watch(ident)
        if not watch.get("armed"):
            print("listening is not armed for %s" % ident, file=sys.stderr)
            return 1
        event_id = (args.since or "").strip()
        if not re.fullmatch(r"evt_[A-Za-z0-9_.\-]+", event_id):
            print("listen cursor needs an event id like evt_20260101T000000_abcdef012345 (pass it with --from or as the next argument)", file=sys.stderr)
            return 1
        watch["since_event_id"] = event_id
        C.write_watch(ident, watch)
        print("watch cursor for %s is now %s" % (ident, event_id))
        return 0
    if args.action == "disarm":
        C.clear_watch(ident)
        print("listening disarmed for %s" % ident)
        print()
        print("Declared-idle statement to post or say, per the protocol:")
        print("%s is NOT monitoring — turn-based, no background watcher." % ident)
        print("Last seen: %s" % (C.read_cursor(ident) or "(no cursor recorded)"))
        print("Ping the operator to wake me; I sweep to_agent=%s on every start." % ident)
        return 0
    types = args.type or cfg["wake"].get("types") or ["task.request", "task.reply", "patch.ready"]
    since = (args.since or "").strip() or _tip_event_id(cfg, ident) or C.read_cursor(ident)
    state = {"armed": True, "types": types, "correlation_id": args.correlation_id or "",
             "topic": args.topic or "", "since_event_id": since}
    C.write_watch(ident, state)
    import sb_probe as P
    transport = P.resolve_transport(cfg["hub"])
    print("listening armed for %s: types %s%s%s, watch cursor %s" % (
        ident, ", ".join(types),
        (", correlation %s" % args.correlation_id) if args.correlation_id else "",
        (", topic %s" % args.topic) if args.topic else "", since or "(start)"))
    if transport == "none":
        print("NOTE: the hook has no transport to the hub, so each prompt will ask the model to make the sweep "
              "itself through the logged-in MCP server and to advance the watch cursor with `listen cursor <id>`. "
              "While waiting on one known correlation, mempalace_event_wait in-turn is the protocol's complement.")
    print()
    print("Announcement to post once (type=status, room=status, to_agent=*%s):" % (
        (", correlation_id=%s" % args.correlation_id) if args.correlation_id else ""))
    print("%s is MONITORING for coordination replies (%s)." % (ident, " / ".join(types)))
    print("Watching: to_agent=%s%s%s. Mode: per-prompt wake check (turn-based client, no background process)." % (
        ident, (" and correlation_id=%s" % args.correlation_id) if args.correlation_id else "",
        (" on topic %s" % args.topic) if args.topic else ""))
    print("Cursor after: %s" % (since or "(start)"))
    return 0


def cmd_listen_entry(cfg, args):
    if args.action == "cursor" and args.event_id and not args.since:
        args.since = args.event_id
    return cmd_listen(cfg, args)


def cmd_peers(cfg, _args):
    import sb_probe as P
    out = P.peers(cfg)
    print(json.dumps(out, indent=2))
    return 0 if not out.get("error") else 1


def cmd_rules(_cfg, args):
    import rules as R
    argv = [args.action]
    for flag in ("host", "harness", "project", "mcp", "target"):
        value = getattr(args, flag, None)
        if value:
            argv += ["--" + flag, value]
    if args.write:
        argv.append("--write")
    return R.main(argv)


def _fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "mempalace-sharedbrain"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def cmd_vendor_check(_cfg, args):
    vendor_dir = os.path.join(C.plugin_root(), "vendor")
    local_path = os.path.join(vendor_dir, "shared_brain_rules.md")
    try:
        local = open(local_path, "rb").read()
        remote = _fetch(UPSTREAM_RAW + "mempalace/instructions/shared_brain_rules.md")
        pyproject = _fetch(UPSTREAM_RAW + "pyproject.toml").decode("utf-8", "replace")
        commit = json.loads(_fetch(UPSTREAM_API_COMMIT).decode("utf-8", "replace")).get("sha", "")
    except Exception as exc:
        print("vendor-check failed: %s" % exc, file=sys.stderr)
        return 1
    version_match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    version = version_match.group(1) if version_match else "?"
    local_sha, remote_sha = hashlib.sha256(local).hexdigest(), hashlib.sha256(remote).hexdigest()
    if local_sha == remote_sha:
        print("vendored shared_brain_rules.md matches upstream main (%s, %s)" % (version, commit[:12]))
        return 0
    print("vendored shared_brain_rules.md DIFFERS from upstream main (%s, %s)" % (version, commit[:12]))
    if not args.update:
        print("run with --update to replace the copy and record the new provenance")
        return 4
    with open(local_path, "wb") as fh:
        fh.write(remote)
    upstream_md = os.path.join(vendor_dir, "UPSTREAM.md")
    try:
        text = open(upstream_md, encoding="utf-8").read()
        text = re.sub(r"^\| `shared_brain_rules\.md` \|.*$",
                      "| `shared_brain_rules.md` | `mempalace/instructions/shared_brain_rules.md` | %s | %s | %s |" % (version, commit, remote_sha),
                      text, flags=re.M)
        open(upstream_md, "w", encoding="utf-8").write(text)
    except OSError as exc:
        print("updated the template but could not rewrite UPSTREAM.md: %s" % exc, file=sys.stderr)
        return 1
    print("updated vendor/shared_brain_rules.md and vendor/UPSTREAM.md; run tests/run.sh, then commit")
    return 0


def cmd_capabilities(cfg, args):
    import capabilities as K
    if args.action == "published":
        if not args.items or len(args.items) != 2:
            print("usage: capabilities published HASH DRAWER_ID", file=sys.stderr)
            return 2
        hash_value, drawer_id = args.items
        K.save_published(hash_value, drawer_id)
        cfg.setdefault("capabilities", {})["profile_drawer_id"] = drawer_id
        C.save_config(cfg)
        print("recorded publish %s, profile drawer %s" % (hash_value, drawer_id))
        return 0
    result = K.probe(cfg)
    K.save_cached(result)
    if args.action == "probe":
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("host %s, probe hash %s" % (result["host"], result["hash"]))
            for name, c in sorted(result["capabilities"].items()):
                print("  %-18s %s" % (name, (c.get("summary") or "yes") if c["present"] else "no"))
        return 0
    if args.action == "check":
        met, unmet = K.check_requirements(result, args.items or [])
        print(json.dumps({"host": result["host"], "met": met, "unmet": unmet}, indent=2))
        return 0 if not unmet else 3
    published = K.load_published()
    caps_cfg = cfg.get("capabilities") or {}
    drawer_id = caps_cfg.get("profile_drawer_id") or published.get("drawer_id") or ""
    state = "current" if published.get("hash") == result["hash"] else ("changed" if published.get("hash") else "never-published")
    if args.action == "status":
        print(json.dumps({"host": result["host"], "state": state, "probe_hash": result["hash"],
                          "published_hash": published.get("hash"), "published_at": published.get("published_at"),
                          "profile_drawer_id": drawer_id}, indent=2))
        return 0 if state == "current" else 3
    # plan
    ident = C.identity(cfg)
    print(json.dumps({
        "host": result["host"],
        "identity": ident,
        "state": state,
        "probe_hash": result["hash"],
        "published_hash": published.get("hash"),
        "profile_drawer_id": drawer_id,
        "wing": caps_cfg.get("wing") or "fleet",
        "room": caps_cfg.get("room") or "machines",
        "facts": K.facts(result),
        "profile": K.profile_text(result, ident),
    }, indent=2))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="setup", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show").set_defaults(func=cmd_show)
    sub.add_parser("path").set_defaults(func=cmd_path)
    sub.add_parser("probe").set_defaults(func=cmd_probe)
    sub.add_parser("peers").set_defaults(func=cmd_peers)

    p = sub.add_parser("identity")
    p.add_argument("--cwd")
    p.add_argument("--diary", action="store_true", help="print the diary-safe form (colons become underscores)")
    p.set_defaults(func=cmd_identity)

    p = sub.add_parser("init")
    p.add_argument("--host")
    p.add_argument("--harness")
    p.add_argument("--project", help="auto (from the workspace) or a fixed project component")
    p.add_argument("--fixed-id", help="use this exact identity instead of host:harness:project")
    p.add_argument("--no-fixed-id", action="store_true")
    p.add_argument("--transport", choices=["auto", "http", "stdio", "none"])
    p.add_argument("--url")
    p.add_argument("--token-env")
    p.add_argument("--token-command")
    p.add_argument("--stdio-command")
    p.add_argument("--timeout", type=float)
    p.add_argument("--rules-target")
    p.add_argument("--mcp", choices=["full", "light"])
    p.add_argument("--project-example")
    p.add_argument("--save-interval", type=int)
    p.add_argument("--no-probe", action="store_true")
    p.add_argument("--probe", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("set")
    p.add_argument("key")
    p.add_argument("value")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("cursor")
    p.add_argument("action", choices=["get", "set", "clear"])
    p.add_argument("event_id", nargs="?")
    p.set_defaults(func=cmd_cursor)

    p = sub.add_parser("listen")
    p.add_argument("action", choices=["arm", "disarm", "status", "cursor"])
    p.add_argument("event_id", nargs="?", help="for `listen cursor`: the event id to advance the watch cursor to")
    p.add_argument("--type", action="append")
    p.add_argument("--correlation-id")
    p.add_argument("--topic")
    p.add_argument("--from", dest="since", help="watch cursor to start from (default: the newest event, like a first `logstream watch`)")
    p.set_defaults(func=cmd_listen_entry)

    p = sub.add_parser("rules")
    p.add_argument("action", choices=["render", "check", "install"])
    p.add_argument("--host")
    p.add_argument("--harness")
    p.add_argument("--project")
    p.add_argument("--mcp", choices=["full", "light"])
    p.add_argument("--target")
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=cmd_rules)

    p = sub.add_parser("capabilities")
    p.add_argument("action", choices=["probe", "status", "plan", "published", "check"])
    p.add_argument("items", nargs="*")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_capabilities)

    p = sub.add_parser("vendor-check")
    p.add_argument("--update", action="store_true")
    p.set_defaults(func=cmd_vendor_check)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    cfg = C.load_config()
    return args.func(cfg, args) or 0


if __name__ == "__main__":
    sys.exit(main())
