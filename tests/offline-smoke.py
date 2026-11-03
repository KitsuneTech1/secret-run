#!/usr/bin/env python3
"""Offline regression smoke test for secret-run's no-leak injection path."""
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "secret-run.py"
SYNTHETIC_SECRET = "offline-smoke-secret-only"


def write_fake_cli(directory):
    """Create a deterministic offline pass-cli stand-in at the wrapper's first lookup."""
    if sys.platform == "win32":
        powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        launcher = directory / "pass-cli.exe"
        try:
            os.link(powershell, launcher)
        except OSError:
            shutil.copyfile(powershell, launcher)
        scripts = {
            "test.ps1": "exit 0\n",
            "login.ps1": "exit 0\n",
            "vault.ps1": '[Console]::Out.WriteLine(\'[{"share_id":"fake-share"}]\')\n',
            "item.ps1": (
                "if ($args[0] -eq 'list') { [Console]::Out.WriteLine("
                "'[ {\"id\":\"fake-item\",\"title\":\"Offline Fixture\"} ]'); exit 0 }\n"
                "if ($args[0] -eq 'view') { [Console]::Out.WriteLine("
                "'{\"password\":\"offline-smoke-secret-only\"}'); exit 0 }\n"
                "exit 9\n"
            ),
        }
        for name, content in scripts.items():
            (directory / name).write_text(content, encoding="utf-8")
    else:
        launcher = directory / "pass-cli"
        script = """#!/usr/bin/env python3
import sys, json

args = sys.argv[1:]
if not args or args[0] in ("test", "login"):
    sys.exit(0)
if args[0] == "vault":
    print(json.dumps([{"share_id": "fake-share"}]))
    sys.exit(0)
if args[0] == "item":
    sub = args[1] if len(args) > 1 else ""
    if sub == "list":
        print(json.dumps([{"id": "fake-item", "title": "Offline Fixture"}]))
        sys.exit(0)
    elif sub == "view":
        print(json.dumps({"password": "offline-smoke-secret-only"}))
        sys.exit(0)
sys.exit(9)
"""
        launcher.write_text(script, encoding="utf-8")
        launcher.chmod(0o755)


def main():
    base = ROOT / (".offline-smoke-" + uuid.uuid4().hex)
    base.mkdir()
    try:
        home = base / "profile"
        roles = home / ".secret-roles"
        roles.mkdir(parents=True)
        (roles / "offline.env").write_text(
            "SYNTHETIC_SECRET = Offline Fixture :: password\n", encoding="utf-8"
        )
        write_fake_cli(base)

        env = {
            "PATH": str(base) + os.pathsep + os.environ.get("PATH", ""),
            "USERPROFILE": str(home),
            "HOME": str(home),
            "LOCALAPPDATA": str(base / "local-app-data"),
            "PROTON_PASS_PERSONAL_ACCESS_TOKEN": "offline-fake-pat",
            "EXPECTED_SECRET": SYNTHETIC_SECRET,
        }
        if "SystemRoot" in os.environ:
            env["SystemRoot"] = os.environ["SystemRoot"]
        if "ComSpec" in os.environ:
            env["ComSpec"] = os.environ["ComSpec"]
        if "PATHEXT" in os.environ:
            env["PATHEXT"] = os.environ["PATHEXT"] + ";.PS1"

        child = (
            "import os, sys; "
            "sys.exit(0 if os.environ.get('SYNTHETIC_SECRET') == "
            "os.environ['EXPECTED_SECRET'] else 17)"
        )
        result = subprocess.run(
            [sys.executable, str(WRAPPER), "offline", "--", sys.executable, "-c", child],
            cwd=base,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding="utf-8",
        )

        if result.returncode != 0:
            raise AssertionError(
                f"wrapper/child failed with {result.returncode}: {result.stderr!r}"
            )
        if SYNTHETIC_SECRET in result.stdout or SYNTHETIC_SECRET in result.stderr:
            raise AssertionError("synthetic secret leaked through wrapper stdout/stderr")
        print("PASS: child received synthetic secret; wrapper output did not leak it")
    finally:
        shutil.rmtree(str(base), ignore_errors=True)


if __name__ == "__main__":
    main()
