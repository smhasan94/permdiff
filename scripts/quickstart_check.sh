#!/usr/bin/env bash
# Installs the package into a fresh virtualenv and runs the README quickstart.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
venv="$(mktemp -d)/venv"
python3 -m venv "$venv"
"$venv/bin/pip" install --quiet --upgrade pip
"$venv/bin/pip" install --quiet "$root"
"$venv/bin/permdiff" --version
