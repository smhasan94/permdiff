# Claude Code example

Two versions of a tool policy for Claude Code sessions, written for the bundled Python
rule-table engine (`--engine python:permdiff.demo.engine:evaluate`). Put `policy_base` and
`policy_head` in two commits of a `policy/` directory and run:

```
permdiff diff --from claude-code --traces ~/.claude/projects/<slug>/*.jsonl \
              --policy policy/ --engine python:permdiff.demo.engine:evaluate \
              --base <base-ref> --head <head-ref> --principal-from env:USER
```

Against `tests/fixtures/claude_code/session.jsonl` the head policy newly denies a `Write`
outside the working directory, asks approval for a destructive `Bash` command, and newly
allows `WebFetch`; the last one is a widening, so the exit code is 2. The README quickstart
scripts this (`scripts/quickstart_check.sh`).
