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
# The Claude Code quickstart: example policy pair in two commits, fixture transcript.
work="$(mktemp -d)"
git -C "$work" init -q -b main
export GIT_AUTHOR_NAME=permdiff GIT_AUTHOR_EMAIL=permdiff@example.com
export GIT_COMMITTER_NAME=permdiff GIT_COMMITTER_EMAIL=permdiff@example.com
cp -r "$root/examples/claude-code/policy_base" "$work/policy"
git -C "$work" add -A && git -C "$work" -c commit.gpgsign=false commit -qm base && git -C "$work" tag v-base
rm -r "$work/policy" && cp -r "$root/examples/claude-code/policy_head" "$work/policy"
git -C "$work" add -A && git -C "$work" -c commit.gpgsign=false commit -qm head
set +e
USER=dev-user "$venv/bin/permdiff" diff --repo "$work" --from claude-code \
  --traces "$root/tests/fixtures/claude_code/session.jsonl" \
  --policy policy --engine python:permdiff.demo.engine:evaluate \
  --base v-base --head HEAD --principal-from env:USER --no-color
code=$?
set -e
[ "$code" -eq 2 ] || { echo "expected exit 2 from the Claude Code quickstart, got $code" >&2; exit 1; }
echo "quickstart OK"
