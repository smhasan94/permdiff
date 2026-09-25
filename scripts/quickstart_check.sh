#!/usr/bin/env bash
# Installs the package into a fresh virtualenv and runs the README quickstart (NFR-Q5).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
venv="$(mktemp -d)/venv"
python3 -m venv "$venv"
"$venv/bin/pip" install --quiet --upgrade pip
"$venv/bin/pip" install --quiet "$root"
cd "$(mktemp -d)"  # away from the source tree: only the installed package may be used

"$venv/bin/permdiff" --version

# `permdiff demo` must find a widening and exit 2 in under 5 seconds.
start=$(date +%s)
set +e
"$venv/bin/permdiff" demo --no-color
code=$?
set -e
end=$(date +%s)
[ "$code" -eq 2 ] || { echo "expected exit 2 from permdiff demo, got $code" >&2; exit 1; }
[ $((end - start)) -le 5 ] || { echo "permdiff demo took $((end - start))s (> 5s)" >&2; exit 1; }

"$venv/bin/permdiff" demo --fail-on none --quiet --no-color
"$venv/bin/permdiff" schema toolcall | python3 -m json.tool > /dev/null

# The OPA variant: download the pinned binary (cached across runs), then rerun the demo.
"$venv/bin/permdiff" setup opa
set +e
"$venv/bin/permdiff" demo --engine opa --quiet --no-color
code=$?
set -e
[ "$code" -eq 2 ] || { echo "expected exit 2 from permdiff demo --engine opa, got $code" >&2; exit 1; }
echo "quickstart OK"
