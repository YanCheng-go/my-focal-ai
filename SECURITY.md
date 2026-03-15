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
| Online public (Vercel) | Public internet | None (read-only static site) | Static HTML + `data.json` |
| Online login (Vercel) | Public internet | Supabase Auth (email/password) | Static HTML + PostgREST + serverless |

### Authentication

- **Local admin auth** is optional, enabled by setting `AINEWS_ADMIN_PASSWORD` env var
- When enabled, admin routes (`/admin/api/*`) require a session cookie
- Login: `POST /admin/login` validates password via `secrets.compare_digest()` (constant-time comparison)
- Session cookie: `httponly=True`, `samesite="strict"`, `max_age=86400` (24 hours)
- Protected routes use FastAPI `Depends()` dependency injection
- When `AINEWS_ADMIN_PASSWORD` is unset, admin routes are open (single-user local tool)
- **Online login auth** uses Supabase Auth (email/password). JWTs validated server-side via Supabase Auth API (`GET /auth/v1/user`), not decoded locally — avoids algorithm confusion attacks
- Serverless function (`api/fetch_source.py`) extracts `user_id` from verified auth response, not from JWT payload directly

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
| `AINEWS_SUPABASE_SERVICE_KEY` | Yes | Supabase service role key (server-side only) |
| `AINEWS_SUPABASE_URL` | No | Supabase project URL |
| `AINEWS_SUPABASE_KEY` | No | Supabase anon/publishable key |
| `AINEWS_CORS_ORIGIN` | No | Allowed CORS origin for serverless endpoints |
| `AINEWS_OLLAMA_MODEL` | No | Ollama model name |
| `AINEWS_DB_PATH` | No | SQLite database path |
| `AINEWS_SCORING` | No | Enable/disable scoring |

- `.env` is in `.gitignore` — never committed
- GitHub Actions secrets are used for `ANTHROPIC_API_KEY` in CI workflows
- No secrets are hardcoded in source code
- Service key (`AINEWS_SUPABASE_SERVICE_KEY`) is server-side only — never exported to `config.json` or static files
- CORS restricted: headers only sent when `AINEWS_CORS_ORIGIN` is set AND `Origin` matches exactly. No wildcard `*`

### OWASP Top 10 Mitigations

| Risk | Mitigation |
|---|---|
| Injection (SQL) | All database queries use parameterized statements with `?` placeholders. Dynamic `IN` clauses use chunked parameterization (`db.py`). Search uses parameterized `LIKE` with `%`-wrapped terms. |
| Injection (Command) | No `os.system()`, `subprocess.run(shell=True)`, `exec()`, or `eval()` calls anywhere in the codebase. |
| Broken Auth | `secrets.compare_digest()` for constant-time password comparison. `httponly` + `samesite=strict` cookies prevent XSS/CSRF-based session theft. |
| Sensitive Data Exposure | All secrets loaded from env vars, never logged. `.env` is gitignored. Browser cookies (Twitter/Xiaohongshu) stay local, never transmitted to cloud pipeline. |
| XSS (Server-side) | Jinja2 templates use default auto-escaping — all `{{ variable }}` output is HTML-escaped. No `|safe` filter or `{% autoescape false %}` overrides. |
| XSS (Client-side) | Static pages use `escapeHtml()` / `esc()` helpers for text content in `innerHTML`. See [Known Issues](#known-issues) for gaps. |
| SSRF | Serverless endpoint (`api/fetch_source.py`) validates URLs via `_is_safe_url()`: blocks private IPs, resolves DNS before checking, blocks `localhost` and `metadata.google.internal`. Local mode URLs come from admin-controlled `sources.yml`. |
| Security Misconfiguration | Vercel deployment is static-only (no serverless). No debug mode in production. No overly permissive CORS. |
| Vulnerable Components | Dependabot monitors dependencies weekly. GitHub CodeQL runs on PRs + weekly schedule. No application-level CVEs in current deps. |
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

Issues identified in security audits. Severity is assessed in the context of a single-user local tool + multi-tenant online mode.

### MEDIUM (open)

**[M4] Unauthenticated `/api/fetch` endpoint**

`POST /api/fetch` triggers a fetch+score cycle without auth. Any device on the local network can trigger it. Impact is limited to resource usage (Ollama inference). Promoted from L3 given the default `0.0.0.0` bind.

**[M5] PostgREST filter injection via search input**

Search input in `supabase_backend.py` (lines 211–214) and `static/index.html` (line 209) escapes `%`, `\`, `,`, `.` but not parentheses, which could theoretically manipulate PostgREST filter grouping. Likely causes errors rather than bypass, but is a defense-in-depth gap. Fix: use per-column `ilike()` filters or allowlist `[a-zA-Z0-9\s]`.

**[M6] Verbose error messages in serverless function**

`api/fetch_source.py` line 325 returns `type(e).__name__: {e}` to the client in 500 responses. Could leak internal paths or library details. Fix: log full error server-side, return generic message to client.

**[M7] XSS via `JSON.stringify` in admin template onclick**

`templates/admin.html` line 167 places `JSON.stringify(s)` in a single-quoted `onclick` attribute. A source name containing `'` could break out. Mitigated: only accessible to authenticated admins. The static `admin.html` uses safe `data-id` event delegation.

**[M8] `.gitignore` only covers `.env`, not `.env.*` variants**

`.env.local`, `.env.production`, etc. are not gitignored and could be accidentally committed. Fix: add `.env*` with `!.envrc` exception.

### MEDIUM (fixed)

**[M1] Stored XSS via unescaped URL in `static/index.html` — FIXED 2026-03-11**

`item.url` was interpolated directly into an `href` attribute without escaping. Fixed by applying `escapeHtml()` to the URL.

**[M2] Unescaped `tier`, `tags`, and `source_type` in `static/index.html` — FIXED 2026-03-11**

`item.tier`, tag values, and `typeTag` were interpolated directly into `innerHTML` without escaping. Fixed by applying `escapeHtml()`.

**[M3] Tag values in `onclick` handler in `static/index.html` — FIXED 2026-03-11**

Tag names were interpolated into an `onclick` attribute. Fixed with `escapeAttr()` helper.

### LOW

**[L1] Static session token derived from password hash**

The admin session cookie value is `SHA256(password)` — deterministic and never rotates. Acceptable for single-user local tool.

**[L2] Missing `secure` flag on admin cookie**

The `admin_token` cookie lacks `secure=True`. Acceptable for local-only mode (`http://localhost:8000`).

**[L4] No input bounds on `page` and `since_hours` query parameters**

`page` accepts zero/negative values and `since_hours` has no upper bound. Impact is limited to unexpected query results.

**[L5] No brute-force protection on admin login**

`POST /admin/login` has no rate limiting or lockout. Local-only feature; online mode uses Supabase Auth.

**[L6] Default bind to `0.0.0.0`**

`config.py` line 24 binds to all interfaces by default, exposing the server to the local network. Consider defaulting to `127.0.0.1`.

**[L7] GitHub Actions use tag refs, not SHA pins**

All 15 action references across 6 workflows use mutable tags (`@v6`, `@v3`). Dependabot for github-actions mitigates this somewhat. Full SHA pinning recommended for supply-chain hardening.

**[L8] `actions/checkout@v4` in `migrations.yml` vs `@v6` everywhere else**

Version inconsistency across workflows. Should align to v6.

### INFO (positive findings)

- All SQLite queries use parameterized statements — no SQL injection
- Supabase backend consistently scopes all queries by `user_id`
- RLS enabled on all tables with full CRUD policies using `auth.uid() = user_id`
- JWT validation via server-side Supabase Auth API (not local decode)
- `secrets.compare_digest()` for constant-time password comparison
- SSRF protection in serverless endpoint (`_is_safe_url()`)
- No `os.system()`, `subprocess.run(shell=True)`, `exec()`, or `eval()` in codebase
- No `|safe` filter or `{% autoescape false %}` in Jinja2 templates
- Static pages use `escapeHtml()` / `esc()` consistently
- YAML loading is safe: `yaml.safe_load()` + `ruamel.yaml.YAML()` (safe by default)
- Service key never appears in client-side code or static files
- `.env` never committed to git history
- No CVEs in any runtime Python dependency (as of 2026-03-15)

## Audit History

| Date | Scope | Findings | Auditor |
|---|---|---|---|
| 2026-03-15 | Full codebase (secrets, deps, OWASP, auth, config) | 0 critical, 0 high, 5 medium (open), 3 medium (fixed), 8 low | Claude Opus 4.6 |
| 2026-03-11 | Full codebase | 0 critical, 0 high, 3 medium (all fixed), 4 low | Claude Opus 4.6 |

## Automated Security

| Tool | Scope | Frequency | Status |
|---|---|---|---|
| Dependabot alerts | Known CVEs in Python deps | Continuous | Enabled 2026-03-15 |
| Dependabot security updates | Auto-PR for vulnerable deps | On CVE detection | Enabled 2026-03-15 |
| Dependabot version updates | Weekly dep bumps | Weekly | Configured (pip + github-actions) |
| Secret scanning | Committed secrets detection | On push | Enabled 2026-03-15 |
| Push protection | Block pushes with secrets | On push | Enabled 2026-03-15 |
| CodeQL | Static analysis (injection, XSS, etc.) | On PR + weekly | Pending setup |

---

*Last updated: 2026-03-15*
