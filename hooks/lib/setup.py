"""Configure the plugin for this machine.

    setup.py show
    setup.py init [--agent-id ID] [--transport auto|http|stdio|none] [--url URL]
                  [--token-env NAME] [--token-command CMD] [--stdio-command "CMD ARGS"]
                  [--save-interval N] [--no-probe]
    setup.py set KEY VALUE          dotted key, JSON value if it parses, else a string
    setup.py add-drawer ID [NOTE]   add a canonical drawer the bootstrap fetches by id
    setup.py remove-drawer ID
    setup.py probe                  run the live check and print what the hook would see
    setup.py path                   print the config file path

init keeps any existing settings and only changes the flags you pass.
"""
import argparse
import json
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(__file__))
import sb_common as C  # noqa: E402


def cmd_show(cfg, _args):
    print("config file: %s%s" % (cfg["_config_file"], "" if cfg["_config_present"] else " (not written yet, showing defaults)"))
    print("agent_id:    %s%s" % (C.agent_id(cfg), "" if cfg.get("agent_id") else " (derived from hostname, set one with init --agent-id)"))
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    print(json.dumps(clean, indent=2, sort_keys=True))


def cmd_init(cfg, args):
    if args.agent_id:
        cfg["agent_id"] = args.agent_id
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


def cmd_add_drawer(cfg, args):
    drawers = [d for d in cfg.get("canonical_drawers") or [] if (d.get("id") if isinstance(d, dict) else d) != args.id]
    drawers.append({"id": args.id, "note": args.note or ""})
    cfg["canonical_drawers"] = drawers
    C.save_config(cfg)
    print("canonical drawers: %d" % len(drawers))


def cmd_remove_drawer(cfg, args):
    before = cfg.get("canonical_drawers") or []
    after = [d for d in before if (d.get("id") if isinstance(d, dict) else d) != args.id]
    cfg["canonical_drawers"] = after
    C.save_config(cfg)
    print("removed %d" % (len(before) - len(after)))


def cmd_probe(cfg, _args):
    import sb_probe as P
    agent = C.agent_id(cfg)
    outcome = P.run_probe(cfg, agent)
    print(json.dumps(outcome, indent=2))
    print()
    print(P.format_probe(outcome, agent))
    return 0 if outcome.get("reachable") or outcome.get("transport") == "none" else 1


def cmd_path(_cfg, _args):
    print(C.CONFIG_FILE)


def build_parser():
    parser = argparse.ArgumentParser(prog="setup", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show").set_defaults(func=cmd_show)
    sub.add_parser("path").set_defaults(func=cmd_path)
    sub.add_parser("probe").set_defaults(func=cmd_probe)

    p_init = sub.add_parser("init")
    p_init.add_argument("--agent-id")
    p_init.add_argument("--transport", choices=["auto", "http", "stdio", "none"])
    p_init.add_argument("--url")
    p_init.add_argument("--token-env")
    p_init.add_argument("--token-command")
    p_init.add_argument("--stdio-command")
    p_init.add_argument("--timeout", type=float)
    p_init.add_argument("--save-interval", type=int)
    p_init.add_argument("--no-probe", action="store_true")
    p_init.add_argument("--probe", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_set = sub.add_parser("set")
    p_set.add_argument("key")
    p_set.add_argument("value")
    p_set.set_defaults(func=cmd_set)

    p_add = sub.add_parser("add-drawer")
    p_add.add_argument("id")
    p_add.add_argument("note", nargs="?")
    p_add.set_defaults(func=cmd_add_drawer)

    p_rm = sub.add_parser("remove-drawer")
    p_rm.add_argument("id")
    p_rm.set_defaults(func=cmd_remove_drawer)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    cfg = C.load_config()
    rc = args.func(cfg, args)
    return rc or 0


if __name__ == "__main__":
    sys.exit(main())
