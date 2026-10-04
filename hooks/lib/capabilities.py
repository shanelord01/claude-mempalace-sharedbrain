"""Machine capability probe and requirement matching.

A machine on a shared hub advertises what it can do so a task lands on a
machine able to do it. This module detects the facts (what is installed, how
big the machine is) with no hub access, in a stable vocabulary; the model
publishes them through the MCP tools as knowledge-graph facts on the host
label plus one profile drawer. Requirements on a task
(``metadata.requires``, e.g. ``["xcode>=27.1", "linode-cli", "memory-gb>=32"]``)
are matched here against the local probe.

Vocabulary (capability names):
    os, cpu, memory-gb, gpu, xcode, xcode-beta, ios-simulator, linode-cli,
    gh, unattended-commit, docker, podman, distrobox, tailscale, node, python,
    git, uv, plus any names under config ``capabilities.custom``.

Requirements travel in ``metadata.requires`` or a ``Requires:`` line in the
event body. A requirement is ``name`` (present) or ``name<op>version`` with op in
``>= > = <= <`` compared on the leading dotted number of the capability's
version. Run directly to see this machine's probe:

    python3 hooks/lib/capabilities.py
"""
import glob
import hashlib
import json
import os
import platform
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import sb_common as C  # noqa: E402

CMD_TIMEOUT = 4.0
CACHE_FILE = os.path.join(C.STATE_DIR, "capabilities.json")
PUBLISHED_FILE = os.path.join(C.STATE_DIR, "capabilities.published.json")
CACHE_TTL = 6 * 3600
# Absence of these is worth stating as a fact (a "lacks" edge), because
# requesters route on them.
CORE = ("xcode", "gpu", "linode-cli", "unattended-commit", "docker")
VERSION_RE = re.compile(r"(\d+(?:\.\d+)*)")
REQ_RE = re.compile(r"^\s*([a-z0-9][a-z0-9._-]*)\s*(>=|<=|=|>|<)?\s*(\S+)?\s*$")


def run(argv, timeout=CMD_TIMEOUT, shell=False):
    """(exit code, stdout) with the exit code 127 when the command is missing or fails to run."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, shell=shell)
        return proc.returncode, proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def version_of(text):
    match = VERSION_RE.search(text or "")
    return match.group(1) if match else None


def version_tuple(text):
    found = version_of(text)
    return tuple(int(p) for p in found.split(".")) if found else ()


def cap(present, version=None, summary="", **detail):
    entry = {"present": bool(present)}
    if version:
        entry["version"] = version
    entry["summary"] = summary or (version or "")
    if detail:
        entry["detail"] = detail
    return entry


# ---- individual probes ---------------------------------------------------

def probe_os():
    system = platform.system().lower() or "unknown"
    release = platform.release()
    pretty = ""
    if system == "linux":
        try:
            for line in open("/etc/os-release"):
                if line.startswith("PRETTY_NAME="):
                    pretty = line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
    elif system == "darwin":
        pretty = "macOS %s" % (platform.mac_ver()[0] or release)
    elif system == "windows":
        pretty = "Windows %s" % platform.version()
    return cap(True, version_of(pretty or release), "%s %s" % (pretty or system, platform.machine()),
               system=system, release=release, arch=platform.machine())


def probe_cpu():
    count = os.cpu_count() or 0
    model = ""
    if platform.system() == "Linux":
        try:
            for line in open("/proc/cpuinfo"):
                if line.lower().startswith("model name"):
                    model = line.split(":", 1)[1].strip()
                    break
        except OSError:
            pass
    elif platform.system() == "Darwin":
        _, model = run(["sysctl", "-n", "machdep.cpu.brand_string"])
    return cap(count > 0, str(count), "%d threads%s" % (count, (", " + model) if model else ""), threads=count, model=model)


def probe_memory():
    gb = 0.0
    if platform.system() == "Linux":
        try:
            for line in open("/proc/meminfo"):
                if line.startswith("MemTotal:"):
                    gb = int(line.split()[1]) / 1024 / 1024
                    break
        except OSError:
            pass
    elif platform.system() == "Darwin":
        _, out = run(["sysctl", "-n", "hw.memsize"])
        gb = int(out) / 1024 ** 3 if out.isdigit() else 0.0
    gb = round(gb)
    return cap(gb > 0, str(gb), "%d GB" % gb, gb=gb)


def probe_gpu():
    if shutil.which("nvidia-smi"):
        code, out = run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])
        if code == 0 and out:
            name, mem, driver = [p.strip() for p in (out.splitlines()[0].split(",") + ["", ""])[:3]]
            return cap(True, version_of(driver), "%s, %s (nvidia driver %s)" % (name, mem, driver), vendor="nvidia", name=name, memory=mem, driver=driver)
    if platform.system() == "Darwin":
        code, out = run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if code == 0 and "Apple" in out:
            return cap(True, None, "%s integrated GPU (Metal)" % out, vendor="apple", name=out)
    return cap(False, summary="none detected")


def probe_xcode():
    if platform.system() != "Darwin":
        return cap(False, summary="not macOS"), cap(False, summary="not macOS")
    releases, betas = [], []
    for app in sorted(glob.glob("/Applications/Xcode*.app")):
        try:
            with open(os.path.join(app, "Contents", "version.plist"), "rb") as fh:
                info = plistlib.load(fh)
            ver = str(info.get("CFBundleShortVersionString", ""))
            build = str(info.get("ProductBuildVersion", ""))
        except Exception:
            continue
        entry = {"app": os.path.basename(app), "version": ver, "build": build}
        # Apple's beta builds end in a letter-digit sequence with a trailing letter; the app
        # is also usually named Xcode-beta.app. Either marks a beta.
        is_beta = "beta" in os.path.basename(app).lower() or bool(re.search(r"\d+[a-z]$", build.lower()))
        (betas if is_beta else releases).append(entry)
    _, selected = run(["xcodebuild", "-version"])
    selected_version = version_of(selected.splitlines()[0]) if selected else None

    def summarise(items):
        return "; ".join("%s (%s)" % (i["version"], i["build"]) for i in items)
    release_cap = cap(bool(releases), (releases[-1]["version"] if releases else None),
                      summarise(releases) + ((", selected %s" % selected_version) if selected_version else ""),
                      apps=releases, selected=selected_version)
    beta_cap = cap(bool(betas), (betas[-1]["version"] if betas else None), summarise(betas), apps=betas)
    return release_cap, beta_cap


def probe_simulators():
    if platform.system() != "Darwin" or not shutil.which("xcrun"):
        return cap(False, summary="not macOS")
    code, out = run(["xcrun", "simctl", "list", "devices", "available", "-j"], timeout=8)
    if code != 0 or not out:
        return cap(False, summary="simctl unavailable")
    try:
        data = json.loads(out)
    except ValueError:
        return cap(False, summary="simctl output unreadable")
    names = sorted({d.get("name", "") for devs in (data.get("devices") or {}).values() for d in devs if d.get("isAvailable", True)})
    phones = [n for n in names if n.startswith("iPhone")]
    return cap(bool(names), None, ", ".join(phones[:6]) + (" ..." if len(phones) > 6 else ""), devices=names)


def probe_tool(name, argv, version_from_first_line=True):
    path = shutil.which(name)
    if not path:
        return cap(False, summary="not installed")
    code, out = run(argv)
    text = (out.splitlines()[0] if (out and version_from_first_line) else out) if code == 0 else ""
    return cap(True, version_of(text), text or path, path=path)


def probe_gh():
    """gh installed and logged in, read from gh's own hosts file so the probe makes no network call."""
    path = shutil.which("gh")
    if not path:
        return cap(False, summary="not installed")
    hosts = os.path.join(os.environ.get("GH_CONFIG_DIR") or os.path.expanduser("~/.config/gh"), "hosts.yml")
    user = None
    try:
        in_github = False
        for line in open(hosts):
            if not line.startswith((" ", "\t")):
                in_github = line.strip().rstrip(":") == "github.com"
            elif in_github and line.strip().startswith("user:"):
                user = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    if user or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return cap(True, None, "logged in to github.com" + ((" as %s" % user) if user else " (token in environment)"), account=user, path=path)
    return cap(False, summary="installed, not logged in", path=path)


def probe_linode_cli():
    path = shutil.which("linode-cli")
    config = os.path.expanduser("~/.config/linode-cli")
    if not path and not os.path.exists(config):
        return cap(False, summary="not installed")
    return cap(True, None, "installed%s" % (", configured" if os.path.exists(config) else ", no profile file"), path=path, configured=os.path.exists(config))


def probe_unattended_commit():
    key = os.path.expanduser("~/.ssh/claude_agent_signing_ed25519")
    signers = os.path.expanduser("~/.ssh/allowed_signers")
    present = os.path.isfile(key) and os.path.isfile(key + ".pub")
    return cap(present, None, "agent signing key present%s" % (", allowed_signers present" if os.path.isfile(signers) else "") if present else "no agent signing key",
               key=key if present else None)


def probe_tailscale():
    """Present when this machine is joined to a tailnet. Up or down right now is volatile and kept out of the summary."""
    if not shutil.which("tailscale"):
        return cap(False, summary="not installed")
    code, out = run(["tailscale", "status", "--self", "--json"], timeout=6)
    try:
        data = json.loads(out) if out else {}
    except ValueError:
        data = {}
    me = data.get("Self") or {}
    dns = (me.get("DNSName") or "").rstrip(".")
    state = data.get("BackendState", "")
    if not dns:
        return cap(False, summary="installed, not joined (%s)" % (state or "status unavailable"), state=state)
    return cap(True, None, dns, state=state, dns_name=dns, tags=me.get("Tags") or [])


def probe_custom(custom):
    """User-defined checks from config: name -> command (no shell). Present when the command exits 0.

    Output is discarded, never published: a check such as a secret-store lookup prints the secret.
    """
    out = {}
    for name, command in (custom or {}).items():
        argv = shlex.split(command) if isinstance(command, str) else list(command)
        try:
            code = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8).returncode
        except (OSError, subprocess.TimeoutExpired, ValueError):
            code = 127
        out[C.component(name, "custom")] = cap(code == 0, None, "yes (custom check)" if code == 0 else "check failed")
    return out


# ---- assembling ----------------------------------------------------------

def probe(cfg, quick=False):
    caps = {
        "os": probe_os(),
        "cpu": probe_cpu(),
        "memory-gb": probe_memory(),
        "gpu": probe_gpu(),
        "git": probe_tool("git", ["git", "--version"]),
        "python": probe_tool("python3", ["python3", "--version"]),
        "node": probe_tool("node", ["node", "--version"]),
        "uv": probe_tool("uv", ["uv", "--version"]),
        "docker": probe_tool("docker", ["docker", "--version"]),
        "podman": probe_tool("podman", ["podman", "--version"]),
        "distrobox": probe_tool("distrobox", ["distrobox", "version"]),
        "linode-cli": probe_linode_cli(),
        "unattended-commit": probe_unattended_commit(),
        "tailscale": probe_tailscale(),
        "gh": probe_gh(),
    }
    xcode, beta = probe_xcode()
    caps["xcode"], caps["xcode-beta"] = xcode, beta
    if not quick:
        caps["ios-simulator"] = probe_simulators()
    caps.update(probe_custom((cfg.get("capabilities") or {}).get("custom")))
    summary = {name: (c.get("summary") if c["present"] else None) for name, c in caps.items()}
    digest = hashlib.sha256(json.dumps(summary, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return {
        "host": C.host_label(cfg),
        "probed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "quick": quick,
        "hash": digest,
        "capabilities": caps,
    }


def facts(result):
    """Knowledge-graph facts for the host label: has_capability and lacks edges, objects under 128 chars."""
    out = []
    host = result["host"]
    for name, c in sorted(result["capabilities"].items()):
        if c["present"]:
            obj = "%s: %s" % (name, c.get("summary") or "present")
            out.append({"subject": host, "predicate": "has_capability", "object": obj[:128]})
        elif name in CORE:
            out.append({"subject": host, "predicate": "lacks", "object": name})
    return out


def profile_text(result, ident=""):
    """The machine-profile drawer body: a problem-phrased purpose line, search terms, then the facts."""
    host = result["host"]
    lines = [
        "Which machine can run a task that needs particular tools or hardware: capability profile of host %s." % host,
        "Search terms: %s capabilities, machine profile, which machine has xcode, which machine has a gpu, "
        "linode-cli access, unattended commit, task routing, metadata.requires." % host,
        "",
        "Probed %s by %s (mempalace-sharedbrain capabilities probe, hash %s)." % (result["probed_at"], ident or host, result["hash"]),
        "",
    ]
    for name, c in sorted(result["capabilities"].items()):
        lines.append("- %s: %s" % (name, (c.get("summary") or "present") if c["present"] else "no"))
    lines += ["", "Route with metadata.requires on a task.request, for example [\"xcode>=27\", \"memory-gb>=32\"]. "
              "Identities on this host are %s:<harness>:<project>." % host]
    return "\n".join(lines)


def short_summary(result, names=("os", "cpu", "memory-gb", "gpu", "xcode", "xcode-beta", "linode-cli", "unattended-commit", "docker", "tailscale")):
    parts = []
    for name in names:
        c = result["capabilities"].get(name)
        if not c:
            continue
        parts.append("%s=%s" % (name, (c.get("summary") or "yes") if c["present"] else "no"))
    return "; ".join(parts)


def load_cached(max_age=CACHE_TTL):
    try:
        data = json.load(open(CACHE_FILE))
        age = time.time() - os.path.getmtime(CACHE_FILE)
        if age <= max_age:
            return data
    except (OSError, ValueError):
        pass
    return None


def save_cached(result):
    C.ensure_dirs()
    with C.open_private(CACHE_FILE, "w") as fh:
        json.dump(result, fh, indent=2)


def load_published():
    try:
        return json.load(open(PUBLISHED_FILE))
    except (OSError, ValueError):
        return {}


def save_published(hash_value, drawer_id):
    C.ensure_dirs()
    with C.open_private(PUBLISHED_FILE, "w") as fh:
        json.dump({"hash": hash_value, "drawer_id": drawer_id, "published_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, fh, indent=2)


def current(cfg, quick=False):
    """Cached probe when fresh, otherwise a new one (cached)."""
    cached = load_cached()
    if cached and (cached.get("quick") is False or quick):
        return cached
    result = probe(cfg, quick=quick)
    save_cached(result)
    return result


# ---- requirements --------------------------------------------------------

def parse_requirement(text):
    match = REQ_RE.match(str(text))
    if not match:
        return None
    name, op, value = match.group(1), match.group(2), match.group(3)
    if bool(op) != bool(value):
        return None
    return {"name": name, "op": op, "value": value}


def _compare(have, op, want):
    a, b = version_tuple(have or ""), version_tuple(want or "")
    if not a or not b:
        return False
    n = max(len(a), len(b))
    a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
    return {">=": a >= b, ">": a > b, "=": a[:len(version_tuple(want))] == b[:len(version_tuple(want))], "<=": a <= b, "<": a < b}[op]


def check_requirements(result, requires):
    """Return (met, unmet) lists of requirement strings against a probe result."""
    met, unmet = [], []
    caps = result.get("capabilities") or {}
    if isinstance(requires, str):
        requires = [r for r in re.split(r"[,\s]+", requires) if r]
    for raw in requires or []:
        req = parse_requirement(raw)
        if not req:
            unmet.append("%s (unreadable requirement)" % raw)
            continue
        c = caps.get(req["name"])
        if not c or not c.get("present"):
            unmet.append(raw)
            continue
        if req["op"] and not _compare(c.get("version") or c.get("summary"), req["op"], req["value"]):
            unmet.append("%s (have %s)" % (raw, c.get("version") or c.get("summary") or "unknown"))
            continue
        met.append(raw)
    return met, unmet


REQUIRES_LINE = re.compile(r"(?im)^\s*requires:\s*(.+?)\s*$")


def _split(text):
    return [r for r in re.split(r"[,\s]+", text) if r]


def requires_of(event):
    """Requirements of a logstream event, as a list, or [].

    Read from metadata.requires (a list or a comma/space separated string), or
    failing that from a "Requires: a, b" line in the body, which is where
    mempalace_task_create (no metadata field) carries them.
    """
    meta = event.get("metadata") or {}
    req = meta.get("requires") if isinstance(meta, dict) else None
    if isinstance(req, str):
        return _split(req)
    if isinstance(req, list):
        return [str(r) for r in req]
    match = REQUIRES_LINE.search(str(event.get("body") or ""))
    return _split(match.group(1)) if match else []


if __name__ == "__main__":
    config = C.load_config()
    res = probe(config, quick="--quick" in sys.argv)
    print(json.dumps(res, indent=2))
    print()
    print("summary:", short_summary(res))
    print("facts:")
    for f in facts(res):
        print("  %s -%s-> %s" % (f["subject"], f["predicate"], f["object"]))
