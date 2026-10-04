"""Bridge message signing (docs/bridge.md, Signing): OpenSSH signatures made and checked with
ssh-keygen, one Ed25519 key per machine, and an allowed-signers file of keys the person approved.

Every subprocess call takes an argv list, never a shell, and every piece of event text reaches
ssh-keygen through a file or stdin, never its command line.
"""
import base64
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

import sb_common as C

NAMESPACE = "mempalace-bridge"
MAX_AGE_SECONDS = 14 * 86400
MAX_SKEW_SECONDS = 5 * 60
PRINCIPAL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*(:[a-z0-9*][a-z0-9._*-]*){0,2}$")
KEY_RE = re.compile(r"^(ssh-ed25519) ([A-Za-z0-9+/=]{40,200})$")
TIME_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


def config_dir():
    return os.path.dirname(C.CONFIG_FILE)


def key_path():
    return os.path.join(config_dir(), "bridge_ed25519")


def signers_path():
    return os.path.join(config_dir(), "trusted_signers")


def seen_path():
    return os.path.join(C.BRIDGE_DIR, "seen_signatures.json")


def ssh_keygen():
    return shutil.which("ssh-keygen") or ""


def _run(argv, stdin=None, timeout=10):
    return subprocess.run(argv, input=stdin, capture_output=True, timeout=timeout)


def fingerprint_of(public_line):
    """SHA256 fingerprint of one public key line, as ssh-keygen prints it."""
    blob = base64.b64decode(public_line.split()[1])
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")


def agent_socket():
    """The 1Password SSH agent's socket, or ''. MEMPALACE_SHAREDBRAIN_AGENT_SOCK overrides it."""
    override = os.environ.get("MEMPALACE_SHAREDBRAIN_AGENT_SOCK")
    if override is not None:
        return override if override and os.path.exists(override) else ""
    for path in ("~/.1password/agent.sock",
                 "~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock"):
        full = os.path.expanduser(path)
        if os.path.exists(full):
            return full
    return ""


def agent_key_name(cfg):
    name = str((cfg.get("bridge") or {}).get("agent_key_name") or "MemPalace bridge {host}")
    return name.replace("{host}", C.host_label(cfg))


def agent_key(cfg):
    """(public key line, '') for the 1Password item named for this machine, or ('', why not).
    Listing public keys never asks the person anything; only signing does."""
    sock = agent_socket()
    if not sock:
        return "", "no 1Password SSH agent socket (turn on Settings > Developer > Use the SSH agent)"
    exe = shutil.which("ssh-add")
    if not exe:
        return "", "ssh-add not found"
    try:
        res = subprocess.run([exe, "-L"], capture_output=True, timeout=10, env=dict(os.environ, SSH_AUTH_SOCK=sock))
    except Exception as exc:
        return "", "could not ask the 1Password agent: %s" % exc
    want = agent_key_name(cfg)
    for line in res.stdout.decode(errors="replace").splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0] == "ssh-ed25519" and parts[2].strip() == want:
            return "%s %s" % (parts[0], parts[1]), ""
    return "", 'no Ed25519 SSH key named "%s" in the 1Password agent' % want


def _trust_own(cfg, line, note):
    """This machine trusts its own current key for its own identities, and no other key for them."""
    principal = "%s:*" % C.host_label(cfg)
    current = [e for e in trust_list() if e["principal"] == principal]
    if not current or current[0]["key"] != line:
        trust_add(principal, line, note)


def ensure_key(cfg):
    """This machine's bridge key. With bridge.key_source auto (the default) or 1password, the key is
    the 1Password SSH key named "MemPalace bridge <host>": its private half never touches the disk,
    and 1Password asks the person before each use, so no command a session runs can sign without
    them. auto falls back to a key file, with a warning; file uses the key file only. Returns
    {available, key, fingerprint, source, warning, error}."""
    exe = ssh_keygen()
    if not exe:
        return {"available": False, "key": "", "fingerprint": "", "source": "", "warning": "", "error": "ssh-keygen not found"}
    source = str((cfg.get("bridge") or {}).get("key_source") or "auto").lower()
    if source not in ("auto", "1password", "file"):
        source = "1password"  # an unrecognised value fails closed: never quietly use a key file
    why = ""
    if source in ("auto", "1password"):
        line, why = agent_key(cfg)
        if line:
            os.makedirs(config_dir(), exist_ok=True)
            pub = agent_pub_path()
            if not os.path.exists(pub) or open(pub).read().split()[:2] != line.split():
                with open(pub, "w") as fh:
                    fh.write(line + " " + agent_key_name(cfg) + "\n")
            _trust_own(cfg, line, "this machine (1Password)")
            # A key file from before is no longer trusted for this machine; remove it so nothing can
            # sign with it any more.
            for old in (key_path(), key_path() + ".pub"):
                try:
                    os.remove(old)
                except OSError:
                    pass
            return {"available": True, "key": line, "fingerprint": fingerprint_of(line), "source": "1password", "warning": "", "error": ""}
        # Once this machine has signed with its 1Password key, it never falls back to a key file: a
        # locked 1Password or a stopped agent means no signing (messages go out unsigned), never a
        # quiet switch to a key any command could use.
        if source == "1password" or os.path.exists(agent_pub_path()):
            return {"available": False, "key": "", "fingerprint": "", "source": "1password", "warning": "",
                    "error": why + " (this machine uses its 1Password key; unlock 1Password or turn its SSH agent on)"}
    path = key_path()
    if not os.path.exists(path):
        os.makedirs(config_dir(), exist_ok=True)
        res = _run([exe, "-q", "-t", "ed25519", "-N", "", "-C", "%s mempalace bridge" % C.host_label(cfg), "-f", path])
        if res.returncode != 0:
            return {"available": False, "key": "", "fingerprint": "", "source": "file", "warning": "", "error": res.stderr.decode(errors="replace").strip()[:200]}
        os.chmod(path, 0o600)
    try:
        line = " ".join(open(path + ".pub").read().split()[:2])
    except OSError as exc:
        return {"available": False, "key": "", "fingerprint": "", "source": "file", "warning": "", "error": str(exc)}
    _trust_own(cfg, line, "this machine (key file)")
    warning = ("the bridge key is a file any command run as this user can read, so a session could sign "
               "without asking you" + (" (1Password: %s)" % why if why else ""))
    return {"available": True, "key": line, "fingerprint": fingerprint_of(line), "source": "file", "warning": warning, "error": ""}


def agent_pub_path():
    return os.path.join(config_dir(), "bridge_1password.pub")


TYPES = ("task.request", "task.reply", "patch.ready")
CORRELATION_RE = re.compile(r"^[A-Za-z0-9_.:-]{0,100}$")


def check_fields(fields):
    """Refuses fields that could blur the line-based payload: every field but the body is one line
    from a fixed alphabet. Returns an error, or ''."""
    sender, to = str(fields.get("from") or ""), str(fields.get("to") or "")
    if not PRINCIPAL_RE.match(sender) or "*" in sender:
        return "sender name not usable as a principal"
    if to != "*" and not PRINCIPAL_RE.match(to):
        return "recipient name not usable"
    if fields.get("type") not in TYPES:
        return "type cannot be signed"
    if not CORRELATION_RE.match(str(fields.get("correlation") or "")):
        return "correlation id not usable"
    return ""


def payload(fields):
    body = fields.get("body") or ""
    return "\n".join([
        "mempalace-bridge-v1",
        "from:%s" % (fields.get("from") or ""),
        "to:%s" % (fields.get("to") or ""),
        "type:%s" % (fields.get("type") or ""),
        "correlation:%s" % (fields.get("correlation") or ""),
        "signed_at:%s" % (fields.get("signed_at") or ""),
        "body-sha256:%s" % hashlib.sha256(body.encode("utf-8")).hexdigest(),
    ])


def sign(cfg, fields, now=None):
    """metadata.bridge_sig for an event this machine sends."""
    problem = check_fields(fields)
    if problem:
        raise RuntimeError("not signed: %s" % problem)
    info = ensure_key(cfg)
    if not info["available"]:
        raise RuntimeError("signing unavailable: %s" % info["error"])
    signed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now or time.time()))
    data = payload(dict(fields, signed_at=signed_at)).encode("utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        msg = os.path.join(tmp, "msg")
        with open(msg, "wb") as fh:
            fh.write(data)
        if info["source"] == "1password":
            # Signs through the agent: 1Password asks the person to approve the use of the key.
            argv = [ssh_keygen(), "-Y", "sign", "-f", agent_pub_path(), "-n", NAMESPACE, "-O", "hashalg=sha512", msg]
            res = subprocess.run(argv, capture_output=True, timeout=120, stdin=subprocess.DEVNULL,
                                 env=dict(os.environ, SSH_AUTH_SOCK=agent_socket()))
        else:
            res = _run([ssh_keygen(), "-Y", "sign", "-f", key_path(), "-n", NAMESPACE, "-O", "hashalg=sha512", msg])
        if res.returncode != 0:
            raise RuntimeError("ssh-keygen -Y sign failed: %s" % res.stderr.decode(errors="replace").strip()[:200])
        sig = open(msg + ".sig").read()
    return {"v": 1, "signed_at": signed_at, "key": info["fingerprint"], "sig": sig}


def _parse_time(text):
    return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()


def verify(event, now=None, record=True):
    """Checks an event's metadata.bridge_sig on this machine. Returns {ok, reason, key}: `key` is
    the fingerprint of the trusted key that verified it, as ssh-keygen reports it, and empty unless
    ok. Nothing the sender wrote about its own key is ever returned."""
    now = now or time.time()
    meta = event.get("metadata") or {}
    sig = meta.get("bridge_sig") if isinstance(meta, dict) else None
    if not isinstance(sig, dict):
        return {"ok": False, "reason": "unsigned", "key": ""}
    key = ""  # filled only from this machine's own verification
    sender = str(event.get("from_agent") or "")
    if event.get("writer") and event.get("writer") != sender:
        return {"ok": False, "reason": "hub writer differs from sender", "key": key}
    if sig.get("v") != 1 or not isinstance(sig.get("sig"), str) or "BEGIN SSH SIGNATURE" not in sig["sig"]:
        return {"ok": False, "reason": "malformed signature", "key": key}
    signed_at = str(sig.get("signed_at") or "")
    if not TIME_RE.match(signed_at):
        return {"ok": False, "reason": "malformed signed_at", "key": key}
    age = now - _parse_time(signed_at)
    if age > MAX_AGE_SECONDS:
        return {"ok": False, "reason": "signature older than 14 days", "key": key}
    if age < -MAX_SKEW_SECONDS:
        return {"ok": False, "reason": "signature dated in the future", "key": key}
    problem = check_fields({"from": sender, "to": event.get("to_agent"), "type": event.get("type"),
                            "correlation": event.get("correlation_id")})
    if problem:
        return {"ok": False, "reason": problem, "key": key}
    if not ssh_keygen():
        return {"ok": False, "reason": "ssh-keygen not found", "key": key}
    if not os.path.exists(signers_path()):
        return {"ok": False, "reason": "no trusted keys on this machine", "key": key}
    data = payload({"from": sender, "to": event.get("to_agent"), "type": event.get("type"),
                    "correlation": event.get("correlation_id"), "signed_at": signed_at,
                    "body": event.get("body") or ""}).encode("utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        sig_file = os.path.join(tmp, "msg.sig")
        with open(sig_file, "w") as fh:
            fh.write(sig["sig"])
        res = _run([ssh_keygen(), "-Y", "verify", "-f", signers_path(), "-I", sender, "-n", NAMESPACE, "-s", sig_file], stdin=data)
    if res.returncode != 0:
        return {"ok": False, "reason": "not signed by a key trusted for %s" % sender, "key": ""}
    m = re.search(r"with \S+ key (SHA256:[A-Za-z0-9+/]+)", (res.stdout + res.stderr).decode(errors="replace"))
    key = m.group(1) if m else ""
    # A valid signature is good for one event: the same one on another event is a replayed task.
    # Keyed on what was signed (the seven lines), not on the signature's text, which can be re-encoded.
    digest = hashlib.sha256(data).hexdigest()
    event_id = str(event.get("id") or "")
    seen = C._read_json(seen_path())
    seen = {k: v for k, v in seen.items() if isinstance(v, dict) and now - v.get("at", 0) < MAX_AGE_SECONDS + 86400}
    first = seen.get(digest)
    if first and first.get("event") != event_id:
        return {"ok": False, "reason": "replayed signature (first seen on %s)" % first.get("event"), "key": key}
    if record and not first:
        seen[digest] = {"event": event_id, "at": now}
        C._write_json(seen_path(), seen)
    return {"ok": True, "reason": "", "key": key}


# ---- the trust store: an OpenSSH allowed-signers file -------------------------------

def principal_for(identity):
    """Approving host:harness:project trusts the key for every identity on that host."""
    parts = identity.split(":")
    return "%s:*" % parts[0] if len(parts) == 3 else identity


def trust_list():
    out = []
    try:
        lines = open(signers_path()).read().splitlines()
    except OSError:
        return out
    for line in lines:
        m = re.match(r'^(\S+) namespaces="mempalace-bridge" (ssh-ed25519 \S+)(?: (.*))?$', line.strip())
        if m:
            out.append({"principal": m.group(1), "key": m.group(2), "fingerprint": fingerprint_of(m.group(2)), "note": m.group(3) or ""})
    return out


def _write_signers(entries):
    os.makedirs(config_dir(), exist_ok=True)
    with C.open_private(signers_path(), "w") as fh:
        for e in entries:
            fh.write('%s namespaces="%s" %s%s\n' % (e["principal"], NAMESPACE, e["key"], (" " + e["note"]) if e.get("note") else ""))


def trust_add(principal, public_line, note="", fingerprint=""):
    """Trusts one key for a principal (replacing any key it had). Returns the key's fingerprint."""
    if not PRINCIPAL_RE.match(principal):
        raise ValueError("not a usable principal: %r" % principal)
    m = KEY_RE.match(" ".join(public_line.split()[:2]))
    if not m:
        raise ValueError("not an ssh-ed25519 public key")
    line = "%s %s" % (m.group(1), m.group(2))
    fpr = fingerprint_of(line)
    if fingerprint and fingerprint != fpr:
        raise ValueError("fingerprint mismatch: the published key is %s, not %s" % (fpr, fingerprint))
    note = re.sub(r"[^A-Za-z0-9 ._:-]", "", note)[:60]
    entries = [e for e in trust_list() if e["principal"] != principal]
    entries.append({"principal": principal, "key": line, "note": note})
    _write_signers(entries)
    return fpr


def trust_revoke(principal):
    entries = trust_list()
    kept = [e for e in entries if e["principal"] != principal]
    _write_signers(kept)
    return len(entries) - len(kept)


def key_from_checkin(content):
    """The published key and fingerprint in a check-in drawer, or ('', '')."""
    for line in str(content).splitlines():
        m = re.match(r"^bridge-key: (ssh-ed25519 [A-Za-z0-9+/=]+) (SHA256:[A-Za-z0-9+/]+)\s*$", line.strip())
        if m:
            return m.group(1), m.group(2)
    return "", ""


def dumps(obj):
    return json.dumps(obj, sort_keys=True)


# ---- pairing: a 6-digit code instead of comparing fingerprints (docs/bridge.md, Pairing) ----------

PAIR_MINUTES = 10


def _pair_mac(code, identity, key, nonce, expires):
    salt = "\n".join([nonce, identity, key, expires]).encode("utf-8")
    return hashlib.scrypt(code.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32).hex()


def pair_offer(cfg, identity, now=None):
    """A pairing request for this machine's key: the code to show the person, and the metadata the
    hub event carries. The code itself never goes to the hub."""
    import secrets
    info = ensure_key(cfg)
    if not info["available"]:
        raise RuntimeError("signing unavailable: %s" % info["error"])
    code = "%06d" % secrets.randbelow(10 ** 6)
    nonce = secrets.token_hex(16)
    expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime((now or time.time()) + PAIR_MINUTES * 60))
    return code, {"v": 1, "identity": identity, "key": info["key"], "fingerprint": info["fingerprint"],
                  "nonce": nonce, "expires": expires, "mac": _pair_mac(code, identity, info["key"], nonce, expires)}


def pair_accept(code, events, own_host, now=None):
    """Trusts the key whose live pairing request matches the code the person typed. Refuses when
    none or more than one key matches. Returns (principal, fingerprint, identity)."""
    now = now or time.time()
    code = re.sub(r"\s", "", str(code))
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("the code is six digits")
    matches = {}
    for e in events or []:
        offer = (e.get("metadata") or {}).get("bridge_pair") if isinstance(e.get("metadata"), dict) else None
        if not isinstance(offer, dict) or offer.get("v") != 1:
            continue
        identity, key, nonce, expires = (str(offer.get(k) or "") for k in ("identity", "key", "nonce", "expires"))
        if identity != e.get("from_agent") or not PRINCIPAL_RE.match(identity) or "*" in identity:
            continue
        if identity.split(":")[0] == own_host or not KEY_RE.match(key) or not TIME_RE.match(expires):
            continue
        if _parse_time(expires) < now or not re.fullmatch(r"[0-9a-f]{32}", nonce):
            continue
        if _pair_mac(code, identity, key, nonce, expires) == str(offer.get("mac") or ""):
            matches.setdefault(key, identity)
    if not matches:
        raise ValueError("no live pairing request matches that code (they last %d minutes)" % PAIR_MINUTES)
    if len(matches) > 1:
        raise ValueError("%d different keys match that code: not approved. Start the pairing again." % len(matches))
    key, identity = next(iter(matches.items()))
    principal = principal_for(identity)
    return principal, trust_add(principal, key, "paired with %s" % identity), identity
