<p align="center"><a href="https://kitsunetechnologies.org/work"><img src="https://raw.githubusercontent.com/KitsuneTech1/.github/main/assets/kitsune-banner.svg" alt="Built by Kitsune Technologies" width="760"></a></p>

# Secret Relay (secret-run)

> Provide autonomous AI agents and automated scripts scoped access to Proton Pass secrets without secret values ever entering the model's context or terminal logs.

<p align="center">
  <a href="https://github.com/KitsuneTech1/secret-run/releases"><img src="https://img.shields.io/github/v/release/KitsuneTech1/secret-run?style=flat-square&color=blue" alt="Release"></a>
  <a href="https://github.com/KitsuneTech1/secret-run/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/KitsuneTech1/secret-run/ci.yml?branch=master&label=CI&style=flat-square" alt="CI Status"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg?style=flat-square" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python Version"></a>
  <a href="secret-run.py"><img src="https://img.shields.io/badge/Dependencies-Standard%20Library%20Only-success?style=flat-square" alt="Zero Dependencies"></a>
  <a href="https://proton.me/pass"><img src="https://img.shields.io/badge/Integration-Proton%20Pass%20CLI-6D4AFF?style=flat-square&logo=proton&logoColor=white" alt="Proton Pass"></a>
</p>

<p align="center">
  <a href="https://github.com/KitsuneTech1/secret-run/releases/latest"><strong>📦 Download Latest Release ZIP</strong></a> •
  <a href="#-quick-start-noob-friendly"><strong>⚡ Quick Start Guide</strong></a> •
  <a href="#architecture--secrets-boundary"><strong>🔒 Security Architecture</strong></a>
</p>

---

The secret flows from Proton Pass (end-to-end encrypted) through `pass-cli` into the isolated child process environment. The agent executes `secret-run <role> -- <command>` and observes only the child process's standard output. Secret values are never printed, logged, or echoed by the wrapper.

---

## Architecture & Secrets Boundary

```mermaid
flowchart LR
    Agent[🤖 AI Agent / Runner Process] -->|Executes: secret-run <role> -- <cmd>| Relay[Secret Relay Python Engine]
    
    subgraph Isolated Secrets Boundary [Host Security Boundary]
        Relay -->|Read Role Mapping| RoleFile[(~/.secret-roles/<role>.env)]
        Relay -->|Query Item & Field via pass-cli| Proton[(Proton Pass Encrypted Vault)]
        Proton -->|Deliver Secret in Memory| Relay
        Relay -->|Inject into Child Process Env ONLY| ChildProc[Target Process / Tool / CLI]
    end
    
    ChildProc -->|Standard Output & Errors (No Secrets Printed)| Agent
```

---

## Features

- **Context Leak Immunity**: LLMs and agents cannot accidentally dump secrets by echoing environment variables from the parent shell.
- **Role-Based Scoping**: Map friendly variable names (e.g., `AWS_SECRET_ACCESS_KEY`, `STRIPE_KEY`) to specific vaults and entries in Proton Pass.
- **Zero Third-Party Dependencies**: Pure Python standard library implementation (`subprocess`, `os`, `sys`, `json`).
- **Comprehensive Audit Trail**: Automatically records secret requests to audit logs without recording values.
- **Multiplatform**: Runs seamlessly on Windows (`secret-run.cmd`), macOS, and Linux.

---

## 🚀 Quick Start (Noob-Friendly)

### 1. Download & Launch
1. Download [**Secret Relay ZIP**](https://github.com/KitsuneTech1/secret-run/releases/latest) and extract it.
2. Double-click **`start.bat`** (Windows) or execute `./start.sh` (macOS/Linux) to verify your Python environment and view the CLI options.

### 2. Configure a Role (3 Steps)
1. Create your local roles directory:
   ```bash
   mkdir -p ~/.secret-roles
   cp examples/example.env ~/.secret-roles/demo.env
   ```
2. Store your Proton Pass Personal Access Token in `~/.secret-roles/.pat`:
   ```bash
   echo "your-proton-token" > ~/.secret-roles/.pat
   chmod 600 ~/.secret-roles/.pat
   ```
3. Run any tool through the relay:
   ```bash
   python secret-run.py demo -- env
   ```

---

## 📖 Role File Specification

Role files are simple `.env` declarations mapped to Proton Pass targets:

```ini
# Explicit vault/item/field mapping
STRIPE_API_KEY=prod-vault/stripe/api_key

# Simple item name (defaults to 'password' field in default vault)
DATABASE_PASSWORD=database_production

# Custom field lookup
GITHUB_TOKEN=Personal/GitHub/pat_token
```

---

## 🧪 Testing & Verification

Run the included unit and smoke tests:

```bash
# 1. Run offline smoke test
python tests/offline-smoke.py

# 2. Run unit test suite
python -m unittest discover -s tests
```

Tests verify:
- Child processes receive mapped secrets properly.
- Wrapper error messages never expose secret contents.
- Strict path confinement on role files (directory traversal prevention).
- Fail-safe handling for invalid, revoked, or expired tokens.

---

## 🔒 Security Specifications

- **Zero Logging of Values**: Exit errors and stdout streams are guaranteed clean of secret data.
- **In-Memory Pipe Transport**: Values pass directly into child environment blocks via OS-level process creation APIs without intermediate disk writes.
- **Strict Role Permissions**: File permissions on `~/.secret-roles/` and `.pat` are validated on Unix platforms.

---

## License

MIT. Copyright (c) 2026 Kitsune Technologies LLC. Full text in [LICENSE](LICENSE).

<p align="center"><sub>Part of <b>Buildtober 2026</b>: 31 open source projects in 31 days. Built by <a href="https://kitsunetechnologies.org/work">Kitsune Technologies</a>. More at <a href="https://github.com/KitsuneTech1">github.com/KitsuneTech1</a>.</sub></p>
