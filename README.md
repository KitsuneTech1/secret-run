# Secret Relay

Run any tool with secrets from Proton Pass injected into its environment, without the secret value ever passing through a model's context or appearing in command output.

The secret flows through this path only: Proton Pass (end-to-end encrypted) -> pass-cli subprocess -> this wrapper -> the child command's environment variables. The orchestrating model only sees `secret-run <role> -- <command>` and the child's normal output. Secret values are never printed by the wrapper.

## Installation

1. Install Python 3.6 or later.
2. Install Proton Pass on your machine. The wrapper will find `pass-cli` in the standard installation location or on your PATH.

## Quick Start

1. Copy the example role to your home directory:

   ```bash
   cp examples/example.env ~/.secret-roles/my-role.env
   ```

2. Edit `~/.secret-roles/my-role.env` to map environment variables to your Proton Pass items.

3. Set your Proton Pass access token:

   ```bash
   # Option A: environment variable (do not commit this)
   export PROTON_PASS_PERSONAL_ACCESS_TOKEN="your-token"
   
   # Option B: file (recommended)
   echo "your-token" > ~/.secret-roles/.pat
   chmod 600 ~/.secret-roles/.pat
   ```

4. Run a command with secrets injected:

   ```bash
   python secret-run.py my-role -- curl https://example.com -H "Authorization: Bearer $MY_SECRET"
   ```

## Usage

### Run a command with a role

```bash
secret-run <role> [--reason "why"] -- <command> [args...]
```

- `<role>`: name of the `.env` file in `~/.secret-roles/` (without extension)
- `--reason`: optional reason logged to the audit trail (if auditing is enabled)
- `<command>`: any executable; remaining arguments are passed to it
- All mappings in the role are injected into the child's environment

The child inherits your current environment plus the mapped secrets.

### List configured roles

```bash
secret-run --list
```

Shows each role file name (without `.env` extension) in `~/.secret-roles/`. Does not print secret values.

### Check a role

```bash
secret-run <role> --check
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
2. **Token file** (recommended): `~/.secret-roles/.pat` with mode 0600

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

For full integration tests, see the comprehensive test suite in `secret-run-test.py`. It requires a configured Proton Pass account and is separate from the offline tests.

## Dependencies

- Python 3.6+
- Proton Pass `pass-cli` on PATH (install via https://proton.me/pass)

## License

MIT

## Author

KitsuneTech1
