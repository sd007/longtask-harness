#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: Python 3 is required. Install Python 3 and run ./install.sh again." >&2
    exit 2
fi

exec python3 "$SCRIPT_DIR/scripts/install.py" --yes --setup-hooks "$@"
