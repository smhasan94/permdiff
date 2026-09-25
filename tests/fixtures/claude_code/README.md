Fixtures for the Claude Code importers (E8).

SOURCE: `session.jsonl` and `subagent.jsonl` are scrubbed lines from real session
transcripts written by Claude Code 2.1.282 on 2026-09-25 (`~/.claude/projects/<slug>/`):
paths moved under `/home/dev/project`, commands and outputs replaced with harmless
equivalents, ids shortened. The format is undocumented; regenerate when a newer Claude Code
changes it. `hooks.jsonl` is `PreToolUse`/`PostToolUse` stdin as documented at
code.claude.com/docs/en/hooks (read 2026-09-25) with the `ts` key added by the hook shown in
`docs/importers.md`; `hooks_no_ts.jsonl` lacks it. `invalid.jsonl` covers a block without
an id, a line without a timestamp, bad JSON, and one good line.
