Fixtures for the Langfuse importer (E13).

SOURCE: hand-built on 2026-09-26 from the Langfuse docs: the blob-storage export field
groups (`export-to-blob-storage`: `core`, `basic`, `io`, `metadata`), the v2 Observations
API response example (`observations-api`, camelCase keys, `input`/`output` as JSON
strings), and the ten observation types (`observation-types`). Not a real export;
regenerate expectations when one is available. `observations.jsonl` is the blob shape
(snake_case), `observations.jsonl.gz` the same compressed, `observations_api.json` an API
page (`{"data": [...]}`).
