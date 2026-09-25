# Releasing permdiff (owner checklist)

permdiff is never published by the agent (standing rule 5). Everything below is for the
repository owner.

## 0.1.0

1. Confirm `main` is green: `ci`, `bench`, and `dogfood` workflows on the release commit.
2. Verify the sticky PR comment once by hand: open a throwaway pull request that changes
   `src/permdiff/demo/policy_head/rules.py`, confirm one `<!-- permdiff -->` comment
   appears, push a second commit, confirm the same comment updates in place, close the PR
   (see `docs/decisions.md`, 2026-09-25, open item).
3. Build and check the distribution:

   ```
   rm -rf dist && uv build && uv run twine check dist/*
   ```

4. Publish to PyPI (needs a PyPI API token with upload scope for the `permdiff` project):

   ```
   uv run twine upload dist/*
   ```

5. Tag the release and the Action's floating major tag, then push both:

   ```
   git tag -a v0.1.0 -m "permdiff 0.1.0"
   git tag -f v0 v0.1.0
   git push origin v0.1.0
   git push -f origin v0
   ```

   Users reference the Action as `smhasan94/permdiff@v0`; `v0` moves with each 0.x release.

6. Create the GitHub release from `v0.1.0` with the 0.1.0 section of `CHANGELOG.md` as
   the notes, and mark `CHANGELOG.md` `0.1.0 (unreleased)` as released with the date.
7. Set the Action's default `version` input to `0.1.0` in `action.yml` once the PyPI
   release is visible, so the Action installs the published wheel instead of its own
   source; leave it empty on `main` between releases if you prefer source installs.
8. Refresh the CI benchmark baseline: download the `bench-results` artifact from the
   first green `bench` run after release and copy its phase numbers into the `ci-linux`
   entry of `bench/baseline.json` (the shipped entry is provisional).
9. Bump `src/permdiff/__init__.py` to the next `.dev0` version on `main`.

## Every release

- Never publish from a dirty tree; the sdist includes `tests/` and `README.md`.
- Re-run `uv run pip-audit --skip-editable` and `permdiff setup opa --force` against the
  pinned OPA version; bump `OPA_VERSION` and the checksum table in
  `src/permdiff/evaluators/opa/binary.py` only with the release's `.sha256` assets.
