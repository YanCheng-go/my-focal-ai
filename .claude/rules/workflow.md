# Workflow

- Commit directly to feature branches. PR to main when ready.
- Self-review changes before merging (use /commit to review diffs).
- Keep commits small and atomic — one logical change per commit.
- Run `uv run pytest` before committing. Do not commit code that breaks existing tests.
- Write meaningful commit messages in imperative mood ("Add ...", "Fix ...").
- Tag releases with semver (e.g., `v1.2.0`).
