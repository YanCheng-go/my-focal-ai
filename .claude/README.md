# .claude/ — Project Config

Most Claude Code configuration lives in the **global** `~/.claude/` folder:

- **Rules**: `~/.claude/rules/` (conventions, git workflow, linting, etc.)
- **Memory**: `~/.claude/memory/` (git identities, feedback, preferences)
- **Hooks**: `~/.claude/settings.json` (protect-files, observability, notifications)

This project's `.claude/` only contains:

- `references/module-map.md` — codebase module reference
- `settings.local.json` — local permission allowlist (gitignored)
