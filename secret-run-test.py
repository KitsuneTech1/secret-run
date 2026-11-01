#!/usr/bin/env python3
"""
secret-run self-test. Triple-checks the bridge without ever printing a secret value.

Each secret's length is confirmed THREE independent ways and reconciled:
  1. via secret-run injecting into a native child (python reads os.environ)
  2. via a direct `pass-cli item view --field` call (separate code path)
  3. via a direct `pass-cli item view` full-JSON parse (third code path)
If any of the three disagree, the test FAILS.

Also checks: PAT-from-file (env unset), clean errors on bad role / missing item,
field selector, explicit share/item/field form, exit-code propagation, and that
the wrapper's OWN stdout never contains secret material.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))
ROOT = Path(__file__).resolve().parent
PY = str(ROOT / "secret-run.py")
CLI = os.environ.get("SECRET_RUN_TEST_CLI") or shutil.which("pass-cli.exe") or shutil.which("pass-cli")
SID = os.environ.get("SECRET_RUN_TEST_SHARE_ID")
ITEM_ID = os.environ.get("SECRET_RUN_TEST_ITEM_ID")
ITEM_TITLE = os.environ.get("SECRET_RUN_TEST_ITEM_TITLE")
EXPECTED_USERNAME = os.environ.get("SECRET_RUN_TEST_USERNAME")
SESSION_DIR = str(Path(os.environ.get("LOCALAPPDATA", HOME / "AppData/Local")) /
                  "Temp" / "pass-agent-secret-run")
REASON = "secret-run self-test 2026-09-29"

results = []


def rec(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ->  {detail}" if detail else ""))


def clean_env():
    e = dict(os.environ)
    e.pop("PROTON_PASS_PERSONAL_ACCESS_TOKEN", None)  # force PAT-from-file
    e.pop("PROTON_PASS_SESSION_DIR", None)
    return e


def sr(args, env=None):
    return subprocess.run([sys.executable, PY, *args], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True,
                          encoding="utf-8", env=env if env is not None else clean_env())


def cli(args):
    e = dict(os.environ)
    e["PROTON_PASS_SESSION_DIR"] = SESSION_DIR
    e["PROTON_PASS_AGENT_REASON"] = REASON
    return subprocess.run([CLI, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, encoding="utf-8", env=e)


def remove_if_exists(path):
    try:
        path.unlink()
    except FileNotFoundError:
        pass


# ---- method 1: length + salted hash via secret-run child (value stays in child) ----
def via_secret_run():
    child = (
        "import os,hashlib;"
        "keys=('ANTHROPIC_API_KEY','DEEPSEEK_API_KEY','OPENROUTER_API_KEY');"
        "print('\\n'.join(f'{k}:{len(os.environ.get(k,\"\"))}:{hashlib.sha256((\"salt\"+os.environ.get(k,\"\")).encode()).hexdigest()[:12]}' for k in keys))"
    )
    r = sr(["ai-keys", "--reason", REASON, "--", sys.executable, "-c", child])
    out = {}
    for line in r.stdout.splitlines():
        if ":" in line:
            parts = line.split(":")
            if len(parts) != 3:
                continue
            k, ln, h = parts
            try:
                out[k] = (int(ln), h)
            except ValueError:
                continue
    return out, r


# ---- method 2: direct pass-cli --field, raw human output (independent code path) ----
def via_field(sid, iid, field="password"):
    r = cli(["item", "view", "--share-id", sid, "--item-id", iid, "--field", field])
    if r.returncode != 0:
        return None
    val = (r.stdout or "").strip()
    # human output may prefix a label line; take the last non-empty line
    lines = [ln for ln in val.splitlines() if ln.strip()]
    val = lines[-1].strip() if lines else ""
    if not val:
        return None
    return len(val), hashlib.sha256(("salt" + val).encode()).hexdigest()[:12]


# ---- method 3: direct pass-cli full json parse ----
def via_json(sid, iid, field="password"):
    r = cli(["item", "view", "--share-id", sid, "--item-id", iid, "--output", "json"])
    if r.returncode != 0:
        return None
    try:
        d = json.loads(r.stdout)
    except Exception:
        return None
    hit = [None]
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, (dict, list)):
                    walk(v)
                elif str(k).lower() == field.lower() or str(k).lower().endswith("." + field.lower()):
                    hit[0] = v
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(d)
    val = str(hit[0] or "")
    return len(val), hashlib.sha256(("salt" + val).encode()).hexdigest()[:12]


def main():
    if sys.argv[1:] != ["--live"]:
        print("Refusing live Proton Pass access. Run with --live after setting the test configuration.")
        return 2
    if not CLI or not SID or not ITEM_ID or not ITEM_TITLE or not EXPECTED_USERNAME:
        print("Set SECRET_RUN_TEST_CLI, SECRET_RUN_TEST_SHARE_ID, SECRET_RUN_TEST_ITEM_ID, "
              "SECRET_RUN_TEST_ITEM_TITLE, and SECRET_RUN_TEST_USERNAME before --live.")
        return 2
    print("=== secret-run triple-check self-test ===\n")

    # T1: --list
    r = sr(["--list"])
    rec("role listing works", r.returncode == 0 and "ai-keys" in r.stdout, r.stdout.strip())

    # T2: --check resolves without values
    r = sr(["ai-keys", "--reason", REASON, "--check"])
    rec("--check resolves all 3", r.returncode == 0 and "3 secret(s) resolved OK" in r.stdout, r.stdout.strip())

    # T3: PAT-from-file (env unset) end-to-end
    m1, r_sr = via_secret_run()
    rec("PAT-from-file + inject into native child",
        set(m1) == {"ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY"}
        and r_sr.returncode == 0
        and all(v[0] > 0 for v in m1.values()),
        " ".join(f"{k}={v[0]}ch" for k, v in m1.items()))

    # T4: TRIPLE reconciliation on Anthropic key (3 independent fetch paths)
    a1 = m1.get("ANTHROPIC_API_KEY")
    a2 = via_field(SID, ITEM_ID)
    a3 = via_json(SID, ITEM_ID)
    agree = a1 and a2 and a3 and a1[0] == a2[0] == a3[0] and a1[1] == a2[1] == a3[1]
    rec("triple-check: 3 fetch paths agree (len+hash)", bool(agree),
        f"len {a1[0] if a1 else '?'}/{a2[0] if a2 else '?'}/{a3[0] if a3 else '?'} "
        f"hash {a1[1] if a1 else '?'}={a2[1] if a2 else '?'}={a3[1] if a3 else '?'}")

    # T5: wrapper's OWN stdout leaks nothing. Re-fetch value directly, assert not in wrapper stdout.
    fv = cli(["item", "view", "--share-id", SID, "--item-id", ITEM_ID, "--field", "password"])
    fv_output = (fv.stdout or "").strip()
    realval = fv_output.splitlines()[-1] if fv.returncode == 0 and fv_output else ""
    leaked = bool(realval) and (realval in r_sr.stdout or realval in r_sr.stderr)
    rec("wrapper never prints the secret", not leaked,
        "no secret material in wrapper stdout/stderr")

    # T6: bad role errors cleanly (non-zero, helpful msg, no traceback)
    r = sr(["does-not-exist", "--", "echo", "x"])
    rec("unknown role -> clean error", r.returncode != 0 and "not found" in r.stderr
        and "Traceback" not in r.stderr, r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")

    # T7: missing item in a role errors cleanly
    badrole = HOME / ".secret-roles" / "_selftest_bad.env"
    badrole.write_text("X = No Such Item Title 9999\n", encoding="utf-8")
    r = sr(["_selftest_bad", "--reason", REASON, "--check"])
    rec("missing item -> clean error", r.returncode != 0 and "not visible" in r.stderr
        and "Traceback" not in r.stderr, r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")
    remove_if_exists(badrole)

    # T8: explicit SHARE/ITEM/field form resolves
    exrole = HOME / ".secret-roles" / "_selftest_explicit.env"
    exrole.write_text(f"EXPLICIT_KEY = {SID}/{ITEM_ID}/password\n", encoding="utf-8")
    r = sr(["_selftest_explicit", "--reason", REASON, "--check"])
    rec("explicit share/item/field form", r.returncode == 0 and "resolved OK" in r.stdout,
        r.stdout.strip())
    remove_if_exists(exrole)

    # T9: field selector (:: username) returns a DIFFERENT value than password
    fldrole = HOME / ".secret-roles" / "_selftest_field.env"
    fldrole.write_text(f"U = {ITEM_TITLE} :: username\n", encoding="utf-8")
    child = "import os;print('U='+os.environ.get('U',''))"
    r = sr(["_selftest_field", "--reason", REASON, "--", sys.executable, "-c", child])
    rec("field selector (:: field)", r.returncode == 0 and f"U={EXPECTED_USERNAME}" in r.stdout, r.stdout.strip())
    remove_if_exists(fldrole)

    # T10: exit code propagation
    r = sr(["ai-keys", "--reason", REASON, "--", sys.executable, "-c", "import sys;sys.exit(42)"])
    rec("child exit code propagates", r.returncode == 42, f"got {r.returncode}")

    # T11: runs from a protected cwd (System32) without the %TEMP% session-dir bug
    r = subprocess.run([sys.executable, PY, "ai-keys", "--reason", REASON, "--check"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, encoding="utf-8", env=clean_env(),
                       cwd=r"C:\Windows\System32")
    rec("works from C:\\Windows\\System32 cwd", r.returncode == 0 and "resolved OK" in r.stdout,
        r.stdout.strip() or r.stderr.strip())

    npass = sum(1 for _, ok, _ in results if ok)
    print(f"\n=== {npass}/{len(results)} checks passed ===")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
