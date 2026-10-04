"""Render, check and install the canonical MemPalace shared-brain rules block.

This mirrors `mempalace rules --host H --harness X --project P [--mcp full|light]`
from the MemPalace package (instructions_cli.py): the same template, the same
placeholder substitution, the same light-MCP tool-name swaps and the same
HTML-comment markers, so a machine without the package produces a block
byte-identical to one with it. When the `mempalace` command is on PATH and
rules.prefer_cli is true, the CLI renders instead and the vendored template is
not read.

    rules.py render  [--host H] [--harness X] [--project P] [--mcp full|light]
    rules.py check   [--target FILE]      exit 0 current, 3 missing, 4 stale
    rules.py install [--target FILE] [--write]   diff by default, --write applies
"""
import argparse
import difflib
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import sb_common as C  # noqa: E402

VENDOR_FILE = os.path.join(C.plugin_root(), "vendor", "shared_brain_rules.md")

# Verbatim from mempalace/instructions_cli.py.
MARKER_START = (
    "<!-- mempalace-shared-brain:start (canonical source: mempalace repo "
    "integrations/shared/coordination-protocol.md — edit there, re-render "
    "with `mempalace rules --host {host} --harness {harness} --project {project}`) -->"
)
MARKER_END = "<!-- mempalace-shared-brain:end -->"

# Longest-first so mempalace_kg_add cannot eat a prefix of a longer name.
MCP_LIGHT_SUBSTITUTIONS = (
    ("mempalace_kg_supersede", "palace_exec KG SUPERSEDE"),
    ("mempalace_kg_invalidate", "palace_exec KG INVALIDATE"),
    ("mempalace_kg_query", "palace_query KG"),
    ("mempalace_kg_add", "palace_exec KG ADD"),
    ("mempalace_add_drawer", "palace_exec ADD"),
    ("mempalace_event_append", "palace_coordinate EVENT APPEND"),
    ("mempalace_event_list", "palace_coordinate EVENT LIST"),
    ("mempalace_event_wait", "palace_coordinate EVENT WAIT"),
    ("mempalace_event_ack", "palace_coordinate EVENT ACK"),
    ("mempalace_patch_submit", "palace_coordinate PATCH SUBMIT"),
    ("mempalace_artifact_get", "palace_coordinate ARTIFACT GET"),
    ("mempalace_search", "palace_query FIND"),
)

BLOCK_RE = re.compile(
    r"<!-- mempalace-shared-brain:start\b.*?-->\n.*?\n" + re.escape(MARKER_END),
    re.DOTALL,
)


class RulesError(Exception):
    pass


def validate_component(name, value):
    value = (value or "").strip()
    if not C.COMPONENT_RE.fullmatch(value):
        raise RulesError(
            "--%s must be a stable lowercase token like windows, grok, or mempalace "
            "(letters, digits, '.', '_', '-'; no colons, no uppercase)" % name
        )
    return value


def apply_mcp_shape(body, mcp):
    if mcp == "full":
        return body
    if mcp != "light":
        raise RulesError("--mcp must be 'full' or 'light'")
    for full_name, light_name in MCP_LIGHT_SUBSTITUTIONS:
        body = body.replace(full_name, light_name)
    return body


def render_vendored(host, harness, project, mcp="full"):
    host = validate_component("host", host)
    harness = validate_component("harness", harness)
    project = validate_component("project", project)
    try:
        with open(VENDOR_FILE, encoding="utf-8") as fh:
            body = fh.read()
    except OSError as exc:
        raise RulesError("vendored rules template not readable: %s" % exc)
    body = body.replace("<HOST>", host).replace("<HARNESS>", harness).replace("<PROJECT>", project)
    body = apply_mcp_shape(body, mcp)
    return "\n".join([
        MARKER_START.format(host=host, harness=harness, project=project),
        "",
        body.rstrip("\n"),
        "",
        MARKER_END,
    ])


def render_with_cli(host, harness, project, mcp="full"):
    """Ask the installed MemPalace CLI to render, or return None when it cannot."""
    if not shutil.which("mempalace"):
        return None
    cmd = ["mempalace", "rules", "--host", host, "--harness", harness, "--project", project, "--mcp", mcp]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or MARKER_END not in proc.stdout:
        return None
    return proc.stdout.rstrip("\n")


def render(cfg, host=None, harness=None, project=None, mcp=None):
    """Return (block, source) where source is 'cli' or 'vendored'."""
    host = host or C.host_label(cfg)
    harness = harness or C.component(cfg["identity"].get("harness"), "claude")
    project = project or cfg["rules"].get("project_example") or C.project_from_cwd()
    mcp = mcp or cfg["rules"].get("mcp") or "full"
    if cfg["rules"].get("prefer_cli", True):
        block = render_with_cli(host, harness, project, mcp)
        if block:
            return block, "cli"
    return render_vendored(host, harness, project, mcp), "vendored"


def target_path(cfg, override=None):
    return os.path.expanduser(override or cfg["rules"].get("target") or "~/.claude/CLAUDE.md")


def find_block(text):
    match = BLOCK_RE.search(text)
    return (match.start(), match.end()) if match else None


def check(text, rendered):
    """'missing', 'current' or 'stale'."""
    span = find_block(text)
    if span is None:
        return "missing"
    return "current" if text[span[0]:span[1]].rstrip("\n") == rendered.rstrip("\n") else "stale"


def splice(text, rendered):
    span = find_block(text)
    if span is None:
        joiner = "" if not text else ("\n" if text.endswith("\n\n") else ("\n\n" if text.endswith("\n") else "\n\n"))
        return text + joiner + rendered + "\n"
    return text[:span[0]] + rendered + text[span[1]:]


def install(cfg, rendered, target=None, write=False):
    """Return (status, diff_text, path). Writes only when write is true."""
    path = target_path(cfg, target)
    try:
        with open(path, encoding="utf-8") as fh:
            current = fh.read()
    except FileNotFoundError:
        current = ""
    status = check(current, rendered)
    updated = splice(current, rendered)
    diff = "".join(difflib.unified_diff(
        current.splitlines(True), updated.splitlines(True),
        fromfile=path, tofile=path + " (after)", n=2,
    ))
    if write and status != "current":
        if current:
            C.ensure_dirs()
            backup = os.path.join(C.STATE_DIR, "rules", "%s.%s" % (
                os.path.basename(path), time.strftime("%Y%m%dT%H%M%S")))
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            with C.open_private(backup, "w") as fh:
                fh.write(current)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(updated)
    return status, diff, path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="rules", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["render", "check", "install"])
    parser.add_argument("--host")
    parser.add_argument("--harness")
    parser.add_argument("--project", help="example project name shown in the block (the runtime identity composes the real one)")
    parser.add_argument("--mcp", choices=["full", "light"])
    parser.add_argument("--target", help="instruction file (default rules.target, ~/.claude/CLAUDE.md)")
    parser.add_argument("--write", action="store_true", help="install: apply the change instead of showing the diff")
    args = parser.parse_args(argv)
    cfg = C.load_config()
    try:
        rendered, source = render(cfg, args.host, args.harness, args.project, args.mcp)
    except RulesError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.action == "render":
        print(rendered)
        print("(rendered by %s)" % ("the mempalace CLI" if source == "cli" else "the vendored template, see vendor/UPSTREAM.md"), file=sys.stderr)
        return 0

    path = target_path(cfg, args.target)
    try:
        with open(path, encoding="utf-8") as fh:
            current = fh.read()
    except FileNotFoundError:
        current = ""
    status = check(current, rendered)

    if args.action == "check":
        print("%s: shared-brain block %s (rendered by %s)" % (path, status, source))
        return {"current": 0, "missing": 3, "stale": 4}[status]

    status, diff, path = install(cfg, rendered, args.target, write=args.write)
    if status == "current":
        print("%s: shared-brain block already current, nothing to do" % path)
        return 0
    if args.write:
        print("%s: shared-brain block %s, written (previous file saved under %s)" % (
            path, "replaced" if status == "stale" else "appended", os.path.join(C.STATE_DIR, "rules")))
        return 0
    print(diff, end="")
    print("\n%s: shared-brain block %s. Re-run with --write to apply." % (path, status))
    return 0


if __name__ == "__main__":
    sys.exit(main())
