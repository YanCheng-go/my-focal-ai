# Conventions

- Write tests for non-trivial logic. Skip tests for glue code and one-off scripts.
- Keep dependencies minimal — every dependency is a maintenance burden.
- Prefer simple solutions over abstractions. Extract patterns only when repeated three times.
- Fix ruff warnings before committing (`uv run ruff check src/`).
- System-level tools go through Nix (`flake.nix`), Python deps through `uv`.
