# Docs Update — Always Update Documentation

## When this rule applies

Every PR that changes code, config, or adds features — before requesting merge approval.

## What to do

Before presenting the PR for human review (Step 7 of /commit), check if any docs are stale:

| Doc | Update when... |
|-----|---------------|
| `README.md` | New pages, new source types, setup changes, new commands |
| `CLAUDE.md` | New modules, changed architecture, new env vars, new conventions |
| `docs/architecture.md` | New ingest modules, new pages, new CI workflows, changed data flow |
| `docs/sources.md` | New source types, changed source counts, new config patterns |
| `docs/scoring.md` | Scoring logic changes, new principles, new tiers |
| `CHANGELOG.md` | Updated via `/release` only |
| `MEMORY.md` | New architectural decisions, new pages, release version bumps |

## How to check

After committing code changes, run through this checklist mentally:
1. Did I add a new page? → Update README (Pages table), architecture.md (module map), MEMORY.md
2. Did I add a new source type? → Update sources.md, architecture.md, README
3. Did I add a new ingest module? → Update architecture.md (module map), CLAUDE.md
4. Did I change CI workflows? → Update architecture.md
5. Did I add new commands? → Update README (Commands section)

## Rules

- Commit doc updates as a separate commit on the same PR branch
- Always update the `*Last updated: YYYY-MM-DD*` line at the bottom of each modified doc
- Do NOT wait for the user to ask — proactively update docs before presenting the PR
