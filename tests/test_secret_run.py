import contextlib
import importlib.util
import io
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("secret_run", ROOT / "secret-run.py")
secret_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(secret_run)


class SecretRunTests(unittest.TestCase):
    def setUp(self):
        self.base = ROOT / (".test-secret-run-" + uuid.uuid4().hex)
        self.roles = self.base / ".secret-roles"
        self.roles.mkdir(parents=True)
        self.old_values = {
            "ROLES_DIR": secret_run.ROLES_DIR,
            "PAT_FILE": secret_run.PAT_FILE,
            "SESSION_DIR": secret_run.SESSION_DIR,
        }
        secret_run.ROLES_DIR = self.roles
        secret_run.PAT_FILE = self.roles / ".pat"
        secret_run.SESSION_DIR = self.base / "session"

    def tearDown(self):
        for name, value in self.old_values.items():
            setattr(secret_run, name, value)
        shutil.rmtree(str(self.base), ignore_errors=True)

    def test_environment_pat_takes_precedence_over_file(self):
        secret_run.PAT_FILE.write_text("from-file\n", encoding="utf-8")
        with patch.dict(
            secret_run.os.environ,
            {"PROTON_PASS_PERSONAL_ACCESS_TOKEN": "from-environment"},
            clear=False,
        ):
            self.assertEqual(secret_run.get_pat(), "from-environment")

    def test_role_rejects_path_traversal(self):
        with self.assertRaises(SystemExit) as raised:
            secret_run.load_role("../outside")
        self.assertEqual(raised.exception.code, 2)

    def test_role_rejects_empty_environment_variable(self):
        (self.roles / "broken.env").write_text(" = Item\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as raised:
            secret_run.load_role("broken")
        self.assertEqual(raised.exception.code, 2)

    def test_explicit_reference_requires_three_parts(self):
        with self.assertRaises(SystemExit) as raised:
            secret_run.resolve_ref("unused", {}, None, "share/item")
        self.assertEqual(raised.exception.code, 2)

    def test_missing_reason_value_is_a_clean_error(self):
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            with self.assertRaises(SystemExit) as raised:
                secret_run.main(["role", "--reason"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--reason requires a value", error.getvalue())

    def test_main_passes_secret_to_child_and_preserves_exit_code(self):
        (self.roles / "offline.env").write_text(
            "SYNTHETIC_SECRET = Offline Fixture\n", encoding="utf-8"
        )
        completed = secret_run.subprocess.CompletedProcess([], 23)
        with patch.object(secret_run, "find_cli", return_value="fake-pass-cli"), \
                patch.object(secret_run, "cli_env", return_value={}), \
                patch.object(secret_run, "get_pat", return_value="fake-pat"), \
                patch.object(secret_run, "ensure_session"), \
                patch.object(secret_run, "resolve_ref", return_value="synthetic-value"), \
                patch.object(secret_run.subprocess, "run", return_value=completed) as run:
            result = secret_run.main(
                ["offline", "--", "python", "-c", "print('child')"]
            )

        self.assertEqual(result, 23)
        child_env = run.call_args.kwargs["env"]
        self.assertEqual(child_env["SYNTHETIC_SECRET"], "synthetic-value")
        self.assertEqual(child_env["PROTON_PASS_SESSION_DIR"], str(secret_run.SESSION_DIR))


if __name__ == "__main__":
    unittest.main()
