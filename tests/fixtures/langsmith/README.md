Fixtures for the LangSmith importer (E13).

SOURCE: hand-built on 2026-09-26 from the LangSmith docs: the run data format
(`run-data-format`: `id`, `name`, `run_type`, `inputs`, `outputs`, `start_time` without a
zone, `extra`, `error`, `tags`, `trace_id`, `parent_run_id`, `session_id`, `status`,
`dotted_order`) and the bulk export docs (`data-export`: Parquet with JSON columns as
text). Not a real export; regenerate expectations when one is available. `runs.jsonl` is an
SDK-style dump; `runs.parquet` is generated from it by `make_parquet.py`.
