#!/usr/bin/env python3
"""Offline regression smoke test for secret-run's no-leak injection path."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "secret-run.py"
SYNTHETIC_SECRET = "offline-smoke-secret-only"


def write_fake_cli(directory):
    """Create a deterministic offline pass-cli stand-in at the wrapper's first lookup."""
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    launcher = directory / "pass-cli.exe"
    try:
        os.link(powershell, launcher)
    except OSError:
        shutil.copyfile(powershell, launcher)
    scripts = {
        "test.ps1": "exit 0\n",
        "login.ps1": "exit 0\n",
        "vault.ps1": "[Console]::Out.WriteLine('[{\"share_id\":\"fake-share\"}]')\n",
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


def main():
    with tempfile.TemporaryDirectory(prefix="secret-run-offline-") as tmp:
        base = Path(tmp)
        home = base / "profile"
        roles = home / ".secret-roles"
        roles.mkdir(parents=True)
        (roles / "offline.env").write_text(
            "SYNTHETIC_SECRET = Offline Fixture :: password\n", encoding="utf-8"
        )
        write_fake_cli(base)

        env = {
            "SystemRoot": os.environ["SystemRoot"],
            "ComSpec": os.environ.get("ComSpec", ""),
            "PATH": str(base) + os.pathsep + os.environ["PATH"],
            "PATHEXT": os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD") + ";.PS1",
            "USERPROFILE": str(home),
            "LOCALAPPDATA": str(base / "local-app-data"),
            "PROTON_PASS_PERSONAL_ACCESS_TOKEN": "offline-fake-pat",
            "EXPECTED_SECRET": SYNTHETIC_SECRET,
        }
        child = (
            "import os, sys; "
            "sys.exit(0 if os.environ.get('SYNTHETIC_SECRET') == "
            "os.environ['EXPECTED_SECRET'] else 17)"
        )
        result = subprocess.run(
            [sys.executable, str(WRAPPER), "offline", "--", sys.executable, "-c", child],
            cwd=base,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        if result.returncode != 0:
            raise AssertionError(
                f"wrapper/child failed with {result.returncode}: {result.stderr!r}"
            )
        if SYNTHETIC_SECRET in result.stdout or SYNTHETIC_SECRET in result.stderr:
            raise AssertionError("synthetic secret leaked through wrapper stdout/stderr")
        # The child's zero exit proves it received the exact synthetic value without printing it.
        print("PASS: child received synthetic secret; wrapper output did not leak it")


if __name__ == "__main__":
    main()
