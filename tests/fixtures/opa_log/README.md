Fixtures for the OPA decision-log importer (E10).

SOURCE: captured 2026-09-26 from the pinned OPA 1.21.0 (`opa run --server --log-format json`
with `decision_logs.console: true` and `nd_builtin_cache: true`) evaluating a small
`agent.authz` policy over four `POST /v1/data/...` requests. `console.jsonl` is the server's
log with `labels.id` and `requested_by` replaced and `metrics` dropped; `sink.json` holds
the same events as the JSON array a remote sink receives (console-only keys removed). One
`bundles` revision was added to the first event to cover `recorded.policy_hash`. Events:
allow (rule path), require_approval (rule path), a scalar `lucky` result with `rand.intn`
cached, and a foreign `input` queried at the package path.
