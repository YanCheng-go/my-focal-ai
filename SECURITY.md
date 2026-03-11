# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| Latest (`main`) | Yes |
| Older branches | No |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report security issues privately via GitHub's built-in security advisory feature:

1. Go to the **Security** tab
2. Click **"Report a vulnerability"**
3. Fill in the details

You can expect an acknowledgement within 48 hours and a resolution timeline within 7 days for critical issues.

## Security Design

### Deployment Modes

| Mode | Network | Auth | Attack Surface |
|---|---|---|---|
| Local (`uv run ainews serve`) | LAN (binds `0.0.0.0:8000`) | Optional (`AINEWS_ADMIN_PASSWORD`) | FastAPI + SQLite |
| Online (Vercel) | Public internet | None (read-only static site) | Static HTML + `data.json` |

### Authentication

- **Admin auth** is optional, enabled by setting `AINEWS_ADMIN_PASSWORD` env var
- When enabled, admin routes (`/admin/api/*`) require a session cookie
- Login: `POST /admin/login` validates password via `secrets.compare_digest()` (constant-time comparison)
- Session cookie: `httponly=True`, `samesite="strict"`, `max_age=86400` (24 hours)
- Protected routes use FastAPI `Depends()` dependency injection
- When `AINEWS_ADMIN_PASSWORD` is unset, admin routes are open (single-user local tool)

### Data Access

- **SQLite**: All queries use parameterized statements (`?` placeholders). No raw string interpolation in SQL.
- **Admin API**: All state-changing endpoints (`POST`, `PUT`, `DELETE` under `/admin/api/`) are protected by `_require_admin` dependency when auth is enabled
- **Public API**: Read-only endpoints (`/api/items`, `/api/digest`, `/api/badge-counts`) are unauthenticated by design
- **Feed data**: RSS/Atom content is semi-trusted (user-curated sources, but externally controlled content)

### Environment Variables

| Variable | Secret? | Purpose |
|---|---|---|
| `AINEWS_ADMIN_PASSWORD` | Yes | Admin login password (local mode) |
| `ANTHROPIC_API_KEY` | Yes | Claude API for cloud scoring |
| `AINEWS_OLLAMA_MODEL` | No | Ollama model name |
| `AINEWS_DB_PATH` | No | SQLite database path |
| `AINEWS_SCORING` | No | Enable/disable scoring |

- `.env` is in `.gitignore` — never committed
- GitHub Actions secrets are used for `ANTHROPIC_API_KEY` in CI workflows
- No secrets are hardcoded in source code

### OWASP Top 10 Mitigations

| Risk | Mitigation |
|---|---|
| Injection (SQL) | All database queries use parameterized statements with `?` placeholders. Dynamic `IN` clauses use chunked parameterization (`db.py`). Search uses parameterized `LIKE` with `%`-wrapped terms. |
| Injection (Command) | No `os.system()`, `subprocess.run(shell=True)`, `exec()`, or `eval()` calls anywhere in the codebase. |
| Broken Auth | `secrets.compare_digest()` for constant-time password comparison. `httponly` + `samesite=strict` cookies prevent XSS/CSRF-based session theft. |
| Sensitive Data Exposure | All secrets loaded from env vars, never logged. `.env` is gitignored. Browser cookies (Twitter/Xiaohongshu) stay local, never transmitted to cloud pipeline. |
| XSS (Server-side) | Jinja2 templates use default auto-escaping — all `{{ variable }}` output is HTML-escaped. No `|safe` filter or `{% autoescape false %}` overrides. |
| XSS (Client-side) | Static pages use `escapeHtml()` / `esc()` helpers for text content in `innerHTML`. See [Known Issues](#known-issues) for gaps. |
| Security Misconfiguration | Vercel deployment is static-only (no serverless). No debug mode in production. No overly permissive CORS. |
| Vulnerable Components | Dependabot monitors dependencies weekly. No application-level CVEs in current deps. |
| YAML Deserialization | Uses `yaml.safe_load()` (stdlib) and `ruamel.yaml.YAML()` (safe by default). No unsafe `yaml.load()`. |

### Third-Party Services

| Service | Data Shared | Notes |
|---|---|---|
| Ollama (local) | Feed titles + summaries | Local LLM scoring, no network egress |
| Anthropic Claude API | Feed titles + summaries | Cloud scoring (optional, requires API key) |
| RSSHub (local Docker) | RSS feed requests | Self-hosted, no external data sharing |
| Vercel | Static HTML + `data.json` | Public deployment of exported feed data |
| GitHub Actions | Feed URLs, API key (secret) | Scheduled fetch + export pipeline |

## Known Issues

Issues identified in the security audit of 2026-03-11. Severity is assessed in the context of a single-user local tool.

### MEDIUM

**[M1] Stored XSS via unescaped URL in `static/index.html` — FIXED 2026-03-11**

`item.url` was interpolated directly into an `href` attribute without escaping. Fixed by applying `escapeHtml()` to the URL, matching the pattern used in all other static pages.

**[M2] Unescaped `tier`, `tags`, and `source_type` in `static/index.html` — FIXED 2026-03-11**

`item.tier`, tag values, and `typeTag` were interpolated directly into `innerHTML` without escaping. Fixed by applying `escapeHtml()` to all dynamic values in template literals.

**[M3] Tag values in `onclick` handler in `static/index.html` — FIXED 2026-03-11**

Tag names were interpolated into an `onclick` attribute string. `escapeHtml()` does not escape single quotes, so a dedicated `escapeAttr()` helper was added that also encodes `'` to `&#39;`.

### LOW

**[L1] Static session token derived from password hash**

The admin session cookie value is `SHA256(password)` — deterministic and never rotates. For a single-user local tool this is acceptable, but not suitable for multi-user or production deployments.

**[L2] Missing `secure` flag on admin cookie**

The `admin_token` cookie lacks `secure=True`, meaning it could be transmitted over HTTP. Acceptable for local-only mode (`http://localhost:8000`), but should be added if HTTPS is ever used.

**[L3] Unauthenticated `/api/fetch` endpoint**

`POST /api/fetch` triggers a fetch+score cycle without auth. Any device on the local network can trigger it. Impact is limited to resource usage (Ollama inference).

**[L4] No input bounds on `page` and `since_hours` query parameters**

`page` accepts zero/negative values and `since_hours` has no upper bound. Impact is limited to unexpected query results, not a security breach.

## Audit History

| Date | Scope | Findings | Auditor |
|---|---|---|---|
| 2026-03-11 | Full codebase | 0 critical, 0 high, 3 medium (all fixed), 4 low | Claude Opus 4.6 |

---

*Last updated: 2026-03-11*
