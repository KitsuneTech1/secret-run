#!/usr/bin/env python3
"""
secret-run: give an agent scoped secrets from Proton Pass WITHOUT the value ever
passing through a model's context.

The secret value flows: Proton Pass (E2E encrypted) -> pass-cli subprocess -> this
wrapper process -> the child command's environment. The orchestrating model only ever
types `secret-run <role> -- <command>` and sees the child's normal output. Values are
never printed by this wrapper.

Usage:
    secret-run <role> [--reason "why"] -- <command> [args...]
    secret-run --list                      # show configured roles
    secret-run <role> --check              # verify every secret in the role resolves (no values shown)

A role is a file at ~/.secret-roles/<role>.env . One mapping per line:
    ENVVAR = Item Title                    # defaults to the item's password field
    ENVVAR = Item Title :: fieldname       # a specific field (case-insensitive)
    ENVVAR = SHARE_ID / ITEM_ID / field    # explicit ids (most precise)
Lines starting with # and blank lines are ignored.

The PAT is read from ~/.secret-roles/.pat if present, else from the
PROTON_PASS_PERSONAL_ACCESS_TOKEN environment variable. Never put it in a role file.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))
ROLES_DIR = HOME / ".secret-roles"
PAT_FILE = ROLES_DIR / ".pat"
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", HOME / "AppData/Local"))
SESSION_DIR = LOCALAPPDATA / "Temp" / "pass-agent-secret-run"

# Resolve pass-cli.exe
CANDIDATES = [
    HOME / "AppData/Local/Programs/ProtonPass/pass-cli.exe",
    Path("pass-cli.exe"),
    Path("pass-cli"),
]


def find_cli():
    for c in CANDIDATES:
        if c.name != str(c) and c.exists():
            return str(c)
    # fall back to PATH
    from shutil import which
    for name in ("pass-cli.exe", "pass-cli"):
        p = which(name)
        if p:
            return p
    die("pass-cli not found. Install Proton Pass CLI or add it to PATH.")


def die(msg, code=2):
    sys.stderr.write(f"secret-run: {msg}\n")
    sys.exit(code)


def get_pat():
    if PAT_FILE.exists():
        tok = PAT_FILE.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    tok = os.environ.get("PROTON_PASS_PERSONAL_ACCESS_TOKEN", "").strip()
    if tok:
        return tok
    die(f"no PAT found. Put it in {PAT_FILE} or set PROTON_PASS_PERSONAL_ACCESS_TOKEN.")


def cli_env():
    env = dict(os.environ)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    env["PROTON_PASS_SESSION_DIR"] = str(SESSION_DIR)
    return env


def run_cli(cli, args, env, reason=None, capture=True):
    e = dict(env)
    if reason:
        e["PROTON_PASS_AGENT_REASON"] = reason
    return subprocess.run(
        [cli, *args],
        env=e,
        capture_output=capture,
        text=True,
        encoding="utf-8",
    )


def ensure_session(cli, env, pat):
    r = run_cli(cli, ["test"], env)
    if r.returncode == 0:
        return
    run_cli(cli, ["login", "--pat", pat], env)
    r = run_cli(cli, ["test"], env)
    if r.returncode != 0:
        die("could not authenticate to Proton Pass with the PAT. "
            + (r.stderr or r.stdout or "").strip(), 3)


def load_role(role):
    f = ROLES_DIR / f"{role}.env"
    if not f.exists():
        die(f"role '{role}' not found ({f}). Try: secret-run --list")
    mappings = []
    for raw in f.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            die(f"bad line in {f.name}: {raw!r}")
        var, ref = line.split("=", 1)
        mappings.append((var.strip(), ref.strip()))
    if not mappings:
        die(f"role '{role}' has no mappings.")
    return mappings


_item_index = None


def item_index(cli, env, reason):
    """Map lowercased item title -> (share_id, item_id) across all accessible vaults."""
    global _item_index
    if _item_index is not None:
        return _item_index
    idx = {}
    vl = run_cli(cli, ["vault", "list", "--output", "json"], env, reason)
    try:
        vaults = json.loads(vl.stdout)
    except Exception:
        vaults = []
    # vault list json shape varies; pull ids robustly
    vault_ids = []
    def collect_ids(o):
        if isinstance(o, dict):
            if "share_id" in o:
                vault_ids.append(o["share_id"])
            elif "id" in o and "name" in o:
                vault_ids.append(o["id"])
            for v in o.values():
                collect_ids(v)
        elif isinstance(o, list):
            for v in o:
                collect_ids(v)
    collect_ids(vaults)
    for sid in dict.fromkeys(vault_ids):
        il = run_cli(cli, ["item", "list", "--share-id", sid, "--output", "json"], env, reason)
        try:
            items = json.loads(il.stdout)
        except Exception:
            continue
        def collect_items(o):
            if isinstance(o, dict):
                iid = o.get("id") or o.get("item_id")
                title = o.get("title") or (o.get("content", {}) or {}).get("title")
                if iid and title:
                    idx[str(title).strip().lower()] = (sid, iid)
                for v in o.values():
                    collect_items(v)
            elif isinstance(o, list):
                for v in o:
                    collect_items(v)
        collect_items(items)
    _item_index = idx
    return idx


def find_field(obj, name):
    """Return the value of the deepest key matching name (case-insensitive)."""
    name = name.lower()
    hit = [None]
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, (dict, list)):
                    walk(v)
                elif str(k).lower() == name or str(k).lower().endswith("." + name):
                    hit[0] = v
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    return hit[0]


def resolve_ref(cli, env, reason, ref):
    """ref -> (share_id, item_id, field). Returns the secret string value."""
    field = "password"
    if "::" in ref:
        left, field = ref.split("::", 1)
        ref, field = left.strip(), field.strip()
    if "/" in ref and ref.count("/") >= 2:
        sid, iid, *rest = [p for p in ref.split("/") if p != ""]
        if rest:
            field = rest[-1]
    else:
        # treat ref as an item title
        idx = item_index(cli, env, reason)
        key = ref.strip().lower()
        if key not in idx:
            die(f"item titled {ref!r} not visible to this token.")
        sid, iid = idx[key]
    r = run_cli(cli, ["item", "view", "--share-id", sid, "--item-id", iid, "--output", "json"], env, reason)
    if r.returncode != 0:
        die(f"could not read item {ref!r}: " + (r.stderr or r.stdout or "").strip(), 4)
    try:
        data = json.loads(r.stdout)
    except Exception:
        die(f"could not parse item {ref!r}.", 4)
    val = find_field(data, field)
    if val is None or val == "":
        die(f"field {field!r} empty/missing on item {ref!r}.", 4)
    return str(val)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--list":
        if not ROLES_DIR.exists():
            print("(no roles dir yet)")
            return 0
        roles = sorted(p.stem for p in ROLES_DIR.glob("*.env"))
        print("roles:", ", ".join(roles) if roles else "(none)")
        return 0

    role = argv[0]
    rest = argv[1:]
    reason = None
    check_only = False
    # parse leading flags
    while rest and rest[0].startswith("--"):
        if rest[0] == "--reason":
            reason = rest[1]
            rest = rest[2:]
        elif rest[0] == "--check":
            check_only = True
            rest = rest[1:]
        elif rest[0] == "--":
            break
        else:
            die(f"unknown flag {rest[0]}")
    cmd = None
    if "--" in rest:
        i = rest.index("--")
        cmd = rest[i + 1:]
    if not check_only and not cmd:
        die("no command. Usage: secret-run <role> [--reason ..] -- <command>")

    reason = reason or os.environ.get("PROTON_PASS_AGENT_REASON") or f"secret-run role={role}"
    cli = find_cli()
    env = cli_env()
    pat = get_pat()
    ensure_session(cli, env, pat)

    mappings = load_role(role)
    child_env = dict(os.environ)
    for var, ref in mappings:
        value = resolve_ref(cli, env, reason, ref)
        child_env[var] = value

    if check_only:
        print(f"role '{role}': {len(mappings)} secret(s) resolved OK -> " +
              ", ".join(v for v, _ in mappings))
        return 0

    # run the child with secrets in its environment. Values are NOT printed here.
    child_env["PROTON_PASS_SESSION_DIR"] = str(SESSION_DIR)
    try:
        proc = subprocess.run(cmd, env=child_env)
        return proc.returncode
    except FileNotFoundError:
        die(f"command not found: {cmd[0]}", 127)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
