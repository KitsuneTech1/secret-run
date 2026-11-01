<p align="center"><a href="https://kitsunetechnologies.org/work"><img src="https://raw.githubusercontent.com/KitsuneTech1/.github/main/assets/kitsune-banner.svg" alt="Built by Kitsune Technologies" width="760"></a></p>

# Secret Relay

Give an agent scoped secrets from Proton Pass without the secret value ever passing through its context.

The secret flows from Proton Pass (end-to-end encrypted) through pass-cli to this wrapper to the child command's environment. The agent only types `secret-run <role> -- <command>` and sees the child's normal output. Secret values are never printed by the wrapper.

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/)

## Installation

1. Install Python 3.6 or later.
2. Install Proton Pass on your machine. The wrapper will find `pass-cli` in the standard installation location or on your PATH.

## Quick Start

1. Create the role directory and set up an example role.

   PowerShell:

   ```powershell
   New-Item -ItemType Directory -Force "$HOME\.secret-roles" | Out-Null
   Copy-Item examples/example.env "$HOME\.secret-roles\my-role.env"
   ```

   Bash (macOS or Linux):

   ```bash
   mkdir -p ~/.secret-roles
   cp examples/example.env ~/.secret-roles/my-role.env
   ```

2. Edit `~/.secret-roles/my-role.env` to map environment variables to your Proton Pass items. See the role file format section below for the syntax.

3. Store your Proton Pass access token. Choose one approach:

   Token file (recommended):

   PowerShell:

   ```powershell
   Set-Content "$HOME\.secret-roles\.pat" "your-token"
   ```

   Bash:

   ```bash
   printf '%s' 'your-token' > ~/.secret-roles/.pat
   chmod 600 ~/.secret-roles/.pat
   ```

   Or environment variable (for testing):

   PowerShell:

   ```powershell
   $env:PROTON_PASS_PERSONAL_ACCESS_TOKEN = "your-token"
   ```

   Bash:

   ```bash
   export PROTON_PASS_PERSONAL_ACCESS_TOKEN="your-token"
   ```

4. Run a command with secrets injected. This example verifies that `STRIPE_SECRET_KEY` was injected without printing its value:

   ```bash
   python secret-run.py my-role -- python -c "import os; print('STRIPE_SECRET_KEY is set:', bool(os.environ.get('STRIPE_SECRET_KEY')))"
   ```

   The child command reads the environment variable directly. Don't try to expand `$STRIPE_SECRET_KEY` or `%STRIPE_SECRET_KEY%` in the outer shell - the shell will try to substitute it before secret-run starts.

## Usage

### Run a command with a role

```bash
python secret-run.py <role> [--reason "why"] -- <command> [args...]
```

- `<role>`: name of the `.env` file in `~/.secret-roles/` (without the `.env` extension)
- `--reason`: optional reason logged to the audit trail (if auditing is configured)
- `<command>`: any executable; remaining arguments pass through to it
- All mappings in the role are injected into the child's environment

The child process inherits your current environment plus the mapped secrets.

### List configured roles

```bash
python secret-run.py --list
```

Shows each role file name (without the `.env` extension) in `~/.secret-roles/`. Does not print secret values.

### Check a role

```bash
python secret-run.py <role> --check
```

Verify that every mapping in the role resolves to a valid Proton Pass item and field, without printing secret values. Returns exit code 0 if all mappings are valid, non-zero otherwise.

## Role file format

Each line in `~/.secret-roles/<role>.env` is one mapping:

```
ENVVAR = Item Title
ENVVAR = Item Title :: fieldname
ENVVAR = SHARE_ID / ITEM_ID / field
```

Blank lines and lines starting with `#` are ignored.

The left side is the environment variable name. The right side specifies a Proton Pass item:

- `Item Title` alone uses the item's password field.
- `Item Title :: fieldname` uses a specific field. Field names are case-insensitive.
- `SHARE_ID / ITEM_ID / field` uses explicit Proton Pass IDs. Use this form if item titles are not unique or change frequently.

## Token storage

The Proton Pass personal access token is required to unlock secrets. Never store it in a role file.

Store it in one of two ways:

1. **Token file** (recommended): `~/.secret-roles/.pat`. Restrict file permissions to your user only.
2. **Environment variable** (for testing): `PROTON_PASS_PERSONAL_ACCESS_TOKEN`

The wrapper checks the environment variable first, then the file.

## Security

- Secret values are never printed by the wrapper, even on error.
- Child process exit codes are passed through to the shell.
- If auditing is enabled, `--reason` messages are logged (secret values are not).
- Secrets are never cached, written to disk, or reused across invocations.

## Testing

Run the offline smoke test:

```bash
python tests/offline-smoke.py
```

Run the full offline test suite:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

These tests run without a Proton Pass account or network access. They use synthetic secrets to verify that the wrapper injects values correctly and never leaks them through its own output.

For live integration testing with a real Proton Pass account, set these environment variables:
- `SECRET_RUN_TEST_CLI`
- `SECRET_RUN_TEST_SHARE_ID`
- `SECRET_RUN_TEST_ITEM_ID`
- `SECRET_RUN_TEST_ITEM_TITLE`
- `SECRET_RUN_TEST_USERNAME`

Then run:

```bash
python secret-run-test.py --live
```

Without `--live`, the script will not contact Proton Pass.

## Dependencies

- Python 3.6 or later
- Proton Pass `pass-cli` (install via https://proton.me/pass)

## License

MIT. Copyright (c) 2026 Kitsune Technologies LLC. See [LICENSE](LICENSE) for details.

---

<p align="center"><sub>Part of <b>Buildtober 2026</b>: 31 open source projects in 31 days. Built by <a href="https://kitsunetechnologies.org/work">Kitsune Technologies</a>. More at <a href="https://github.com/KitsuneTech1">github.com/KitsuneTech1</a>.</sub></p>
