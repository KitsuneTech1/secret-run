#!/usr/bin/env bash
echo "========================================================"
echo "  Secret Relay (secret-run)"
echo "  Kitsune Technologies LLC"
echo "========================================================"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] Python 3 was not found on your system."
    echo "Please install Python 3.10+ from https://python.org/"
    exit 1
fi

python3 secret-run.py --help
