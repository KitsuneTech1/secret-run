import contextlib
import importlib.util
import io
import os
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

    def test_role_rejects_nul_in_name(self):
        with self.assertRaises(SystemExit) as raised:
            secret_run.load_role("bad\x00role")
        self.assertEqual(raised.exception.code, 2)

    def test_role_rejects_empty_environment_variable(self):
        (self.roles / "broken.env").write_text(" = Item\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as raised:
            secret_run.load_role("broken")
        self.assertEqual(raised.exception.code, 2)

    def test_role_rejects_invalid_environment_variable_name(self):
        (self.roles / "broken.env").write_text("NOT-VALID = Item\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as raised:
            secret_run.load_role("broken")
        self.assertEqual(raised.exception.code, 2)

    def test_role_rejects_case_insensitive_duplicate_environment_names(self):
        (self.roles / "broken.env").write_text(
            "TOKEN = First\ntoken = Second\n", encoding="utf-8"
        )
        with self.assertRaises(SystemExit) as raised:
            secret_run.load_role("broken")
        self.assertEqual(raised.exception.code, 2)

    def test_local_cli_candidate_is_checked(self):
        cli = self.base / "pass-cli.exe"
        cli.write_text("fixture", encoding="utf-8")
        old_cwd = os.getcwd()
        try:
            os.chdir(self.base)
            with patch.object(secret_run, "CANDIDATES", [Path("pass-cli.exe")]):
                self.assertEqual(secret_run.find_cli(), "pass-cli.exe")
        finally:
            os.chdir(old_cwd)

    def test_session_path_must_be_a_directory(self):
        secret_run.SESSION_DIR.write_text("not a directory", encoding="utf-8")
        with self.assertRaises(SystemExit) as raised:
            secret_run.cli_env()
        self.assertEqual(raised.exception.code, 3)

    def test_explicit_reference_requires_three_parts(self):
        with self.assertRaises(SystemExit) as raised:
            secret_run.resolve_ref("unused", {}, None, "share/item")
        self.assertEqual(raised.exception.code, 2)

    def test_ambiguous_title_does_not_select_an_arbitrary_item(self):
        completed = secret_run.subprocess.CompletedProcess

        def fake_run_cli(_cli, args, _env, _reason=None, capture=True):
            if args[:2] == ["vault", "list"]:
                return completed([], 0, '[{"share_id":"share-one"},{"share_id":"share-two"}]', "")
            if args[:2] == ["item", "list"] and args[2] == "--share-id":
                share = args[3]
                return completed([], 0, '[{"id":"item-' + share + '","title":"Same title"}]', "")
            raise AssertionError(f"unexpected CLI call: {args}")

        with patch.object(secret_run, "run_cli", side_effect=fake_run_cli):
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                with self.assertRaises(SystemExit) as raised:
                    secret_run.resolve_ref("fixture", {}, None, "Same title")
        self.assertEqual(raised.exception.code, 4)
        self.assertIn("ambiguous", error.getvalue())

    def test_malformed_item_content_is_ignored_without_crashing(self):
        completed = secret_run.subprocess.CompletedProcess

        def fake_run_cli(_cli, args, _env, _reason=None, capture=True):
            if args[:2] == ["vault", "list"]:
                return completed([], 0, '[{"share_id":"share-one"}]', "")
            if args[:2] == ["item", "list"]:
                return completed([], 0, '[{"id":"item-one","content":[]}]', "")
            raise AssertionError(f"unexpected CLI call: {args}")

        with patch.object(secret_run, "run_cli", side_effect=fake_run_cli):
            self.assertEqual(secret_run.item_index("fixture", {}, None), {})

    def test_cli_error_output_is_not_echoed(self):
        completed = secret_run.subprocess.CompletedProcess(
            [], 7, "synthetic-secret-from-cli", "synthetic-secret-from-cli"
        )
        with patch.object(secret_run, "run_cli", return_value=completed):
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                with self.assertRaises(SystemExit) as raised:
                    secret_run.resolve_ref("fixture", {}, None, "share/item/password")
        self.assertEqual(raised.exception.code, 4)
        self.assertNotIn("synthetic-secret-from-cli", error.getvalue())

    def test_authentication_error_does_not_echo_cli_output(self):
        completed = secret_run.subprocess.CompletedProcess(
            [], 1, "synthetic-secret-from-cli", "synthetic-secret-from-cli"
        )
        with patch.object(secret_run, "run_cli", return_value=completed):
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                with self.assertRaises(SystemExit) as raised:
                    secret_run.ensure_session("fixture", {}, "pat")
        self.assertEqual(raised.exception.code, 3)
        self.assertNotIn("synthetic-secret-from-cli", error.getvalue())

    def test_malformed_role_is_rejected_before_authentication(self):
        (self.roles / "broken.env").write_text("NOT-VALID = Item\n", encoding="utf-8")
        with patch.object(secret_run, "find_cli") as find_cli:
            with self.assertRaises(SystemExit):
                secret_run.main(["broken", "--check"])
        find_cli.assert_not_called()

    def test_command_arguments_before_separator_are_rejected(self):
        with self.assertRaises(SystemExit) as raised:
            secret_run.main(["role", "unexpected", "--", "echo", "ok"])
        self.assertEqual(raised.exception.code, 2)

    def test_check_cannot_silently_ignore_a_command(self):
        with self.assertRaises(SystemExit) as raised:
            secret_run.main(["role", "--check", "--", "echo", "ok"])
        self.assertEqual(raised.exception.code, 2)

    def test_nul_in_audit_reason_is_rejected_before_subprocess(self):
        with self.assertRaises(SystemExit) as raised:
            secret_run.run_cli("fixture", ["test"], {}, "bad\x00reason")
        self.assertEqual(raised.exception.code, 2)

    def test_empty_reference_after_field_separator_is_rejected(self):
        with self.assertRaises(SystemExit) as raised:
            secret_run.resolve_ref("fixture", {}, None, "::password")
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
