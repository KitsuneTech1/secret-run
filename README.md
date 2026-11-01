# Secret Relay

Run any tool with secrets from Proton Pass injected into its environment, without the secret value ever passing through a model's context or appearing in command output.

The secret flows through this path only: Proton Pass (end-to-end encrypted) -> pass-cli subprocess -> this wrapper -> the child command's environment variables. The orchestrating model only sees `secret-run <role> -- <command>` and the child's normal output. Secret values are never printed by the wrapper.

## Installation

1. Install Python 3.6 or later.
2. Install Proton Pass on your machine. The wrapper will find `pass-cli` in the standard installation location or on your PATH.

## Quick Start

1. Create the role directory and copy the example role to your home directory.

   PowerShell:

   ```powershell
   New-Item -ItemType Directory -Force "$HOME\.secret-roles" | Out-Null
   Copy-Item examples/example.env "$HOME\.secret-roles\my-role.env"
   ```

   macOS or Linux:

   ```bash
   mkdir -p ~/.secret-roles
   cp examples/example.env ~/.secret-roles/my-role.env
   ```

2. Edit `~/.secret-roles/my-role.env` to map environment variables to your Proton Pass items.

3. Set your Proton Pass access token:

   PowerShell, for the current session only:

   ```powershell
   $env:PROTON_PASS_PERSONAL_ACCESS_TOKEN = "your-token"
   ```

   macOS or Linux, for the current shell only:

   ```bash
   export PROTON_PASS_PERSONAL_ACCESS_TOKEN="your-token"
   ```

   Or store the token in a file. PowerShell:

   ```powershell
   Set-Content "$HOME\.secret-roles\.pat" "your-token"
   ```

   macOS or Linux:

   ```bash
   printf '%s' 'your-token' > ~/.secret-roles/.pat
   chmod 600 ~/.secret-roles/.pat
   ```

4. Edit the role so its mappings refer to your Proton Pass items, then run a
   command with secrets injected. This example checks whether the mapped
   `STRIPE_SECRET_KEY` variable is present without printing its value:

   ```text
   python secret-run.py my-role -- python -c "import os; print('STRIPE_SECRET_KEY is set:', bool(os.environ.get('STRIPE_SECRET_KEY')))"
   ```

   The child command reads the injected variable itself. Do not put
   `$STRIPE_SECRET_KEY` or `%STRIPE_SECRET_KEY%` in the outer shell command,
   because that shell expands it before `secret-run.py` starts.

## Usage

### Run a command with a role

```bash
python secret-run.py <role> [--reason "why"] -- <command> [args...]
```

- `<role>`: name of the `.env` file in `~/.secret-roles/` (without extension)
- `--reason`: optional reason logged to the audit trail (if auditing is enabled)
- `<command>`: any executable; remaining arguments are passed to it
- All mappings in the role are injected into the child's environment

The child inherits your current environment plus the mapped secrets.

### List configured roles

```bash
python secret-run.py --list
```

Shows each role file name (without `.env` extension) in `~/.secret-roles/`. Does not print secret values.

### Check a role

```bash
python secret-run.py <role> --check
```

Verifies that every mapping in the role resolves to a valid Proton Pass item and field. Does not print secret values. Exits with code 0 if all mappings are valid, and a non-zero code otherwise.

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

The Proton Pass personal access token is required for the wrapper to unlock secrets. It is never stored in a role file.

Store it in one of two ways:

1. **Environment variable** (for testing only): `PROTON_PASS_PERSONAL_ACCESS_TOKEN`
2. **Token file** (recommended): `~/.secret-roles/.pat`; restrict the file to your user account

The wrapper checks the environment variable first, then the file.

## Security and audit

- Secret values are never printed by this wrapper, even on error.
- Child process exit codes are preserved and passed to the shell.
- If auditing is enabled by the platform, `--reason` messages are logged (values are not).
- The value is never cached, written to disk, or reused across invocations.

## Testing

Run the offline smoke test to verify the injection path works correctly:

```bash
python tests/offline-smoke.py
```

Run the additional offline regression tests with the Python standard library:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

These offline tests run without a Proton Pass account or network access. They use synthetic secrets to verify that the wrapper correctly injects values into the child process and never leaks them through the wrapper's own output.

For integration testing, see `secret-run-test.py`. It requires a configured Proton Pass account and is separate from the offline tests.

## Dependencies

- Python 3.6+
- Proton Pass `pass-cli` on PATH (install via https://proton.me/pass)

## License

MIT

## Author

KitsuneTech1
