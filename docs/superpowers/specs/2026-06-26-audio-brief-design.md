# Daily Audio Brief — Design Spec

**Issue:** #89 (Daily digest via LLM summary)
**Date:** 2026-06-26
**Status:** Approved, pre-implementation

## Goal

Produce a daily, narrated audio brief of the most relevant items — a NotebookLM-style
2-host podcast — that earns "the slot" (commute, gym, dog walk) a text digest cannot.

Per the issue discussion (m13v): the value of audio is the *listening slot*, not the
format. The catch is audio must be *narrated*, not bullets piped through TTS. NotebookLM
already writes and voices its own 2-host conversational script, so we feed it clean
source items and let it narrate — no separate Claude script pass.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Output format | Audio brief (NotebookLM 2-host podcast) | The "slot" argument; conversational feel |
| Engine | `notebooklm-py` (unofficial, browser automation) | Authentic NotebookLM audio; user opted in |
| Auth | Personal Google account via `notebooklm login` | Only auth the library supports |
| Run environment | **Local / self-hosted server only** | Browser automation + Google login can't run in GitHub Actions CI |
| Script pass | None — feed items, let NotebookLM narrate | NotebookLM writes its own script; a Claude pass is redundant |
| Item selection | Reuse `backend.get_items(limit, min_score, since)` | Single source of truth; same query as `/api/digest` |

## Constraints / Risks

- **CI-incompatible.** Playwright + interactive Google auth. Runs on the user's Mac or a
  self-hosted Linux server, never GitHub Actions.
- **Cookies expire silently.** A logged-out / expired session makes the job fail with no
  audio. Phase 3 cron MUST alert on failure (Slack) or gaps go unnoticed.
- **`storage_state.json` = full Google impersonation.** Never commit, `chmod 600`, keep
  out of the repo dir. Login locally, copy the file to the server (don't `notebooklm
  login` from a datacenter IP — higher bot-flag risk).
- **ToS gray zone.** Automating a personal account is unofficial; low account-flag risk
  for personal daily use.
- **Notebook accumulation.** A new notebook per run accrues toward NotebookLM's notebook
  cap. Marked as a `ponytail:` ceiling; add reuse/cleanup only if the cap is hit.

## Architecture

```
ainews audio-brief
  └─ audio_brief.generate_brief(hours, min_score, out_dir)
        1. items = backend.get_items(limit=20, min_score, since=now-hours)   # reuse
        2. text  = build_source_text(items)
        3. NotebookLMClient.from_storage():
             nb = notebooks.create("Daily Brief <date>")
             sources.add_text(nb.id, text)          # verify exact method at impl
             s  = artifacts.generate_audio(nb.id, instructions=AUDIO_INSTRUCTIONS)
             artifacts.wait_for_completion(nb.id, s.task_id)
             artifacts.download_audio(nb.id, out/brief-YYYY-MM-DD.mp3)
        4. return out_path
  └─ (optional) deliver_slack(out_path)              # Phase 2
```

### Components

**`src/ainews/audio_brief.py`** (new)
- `build_source_text(items) -> str` — plain-text source doc: one block per item with
  title · source · score · reason · url. **Only real logic; unit-tested.**
- `generate_brief(hours, min_score, out_dir) -> Path` — orchestrates selection →
  NotebookLM → download. Glue; not unit-tested (network + browser).
- `deliver_slack(path, token, channel)` — `files.upload` via `httpx` (already a dep; no
  Slack SDK). Phase 2.

**CLI** — `ainews audio-brief [--hours 24] [--min-score 0.6] [--out out/] [--slack]`

**Dependency** — new optional extra `[audio]` = `notebooklm-py`. Out of core; nothing
else takes the dep.

**Config** (new `AINEWS_` vars in `config.py`)
- `AUDIO_OUT_DIR` — default `out/`
- `AUDIO_INSTRUCTIONS` — default: "Concise daily AI news brief, conversational, ~5 minutes."
- `SLACK_BOT_TOKEN`, `SLACK_CHANNEL` — Phase 2 delivery
- NotebookLM auth lives in `~/.notebooklm/`, not our config.

## Phases

| Phase | Deliverable | Stop-here value |
|---|---|---|
| 1 | `audio-brief` → local mp3 in `out/` | Listen, verify quality before any wiring |
| 2 | `--slack` → mp3 uploaded to channel | Mobile push = the listening slot |
| 3 | cron on server + Slack failure alert | Daily, fails loud, no silent gaps |

## Testing

- `tests/test_audio_brief.py` — assert `build_source_text` renders items correctly
  (title/url/score present, ordering, empty-list handling).
- NotebookLM and Slack calls = glue; mocked or skipped (can't run in CI).

## Security checklist

- `.gitignore`: `out/`, `*.notebooklm*`, `storage_state.json`.
- Slack token via env only — never committed.
- Server: `storage_state.json` `chmod 600`, outside repo dir.

## Out of scope

- Video / slides (NotebookLM video overview) — separate follow-up.
- Email delivery — Slack chosen instead.
- Claude narration script pass — NotebookLM narrates itself.
- Multi-user / per-user briefs (online-login mode).

---

*Last updated: 2026-06-26*
