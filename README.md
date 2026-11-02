# ResearchTwin

AI-powered researcher-student collaboration platform that matches students with faculty researchers based on profile compatibility using machine learning.

## Architecture

ResearchTwin uses a FastAPI backend, SQLAlchemy database layer, and static vanilla JavaScript frontend. The backend owns authentication, profile ownership, researcher access policy, collaboration, roadmap persistence, rate limits, and recommendations.

```text
backend/app/                 Canonical FastAPI application and services
backend/models/               Model artifacts used by recommendation service
backend/data/                 Researcher import source and matching data
backend/tests/                Pytest unit and integration coverage
frontend/researchtwin.html    Main application
frontend/api-client.js        Browser API client and session handling
frontend/frontend-config.js   Browser API base URL selection
frontend/index.html           Frontend launcher
main.py                       Root compatibility entry point for the backend
index.html, researchtwin.html Root frontend launchers
```

The serving recommendation code currently expects `backend/models/researchtwin_logistic_v2_7features.joblib`. The artifact is present in this working tree but is currently untracked by Git; include and verify it in any future release bundle before expecting `/ready` to pass in a clean checkout. See [Production configuration checklist](PRODUCTION_CONFIGURATION_CHECKLIST.md).

## Installation

### Prerequisites
- Python 3.11.
- Node.js and npm for the frontend tests and browser E2E suite.
- Internet access the first time semantic matching downloads its sentence-transformer model.

### Local demo setup (Windows PowerShell)

Run the backend commands from `backend/`. Use a new temporary SQLite database for a clean demo; leaving `DATABASE_URL` unset selects the existing file `backend/researchtwin.db`.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt

$demoDir = Join-Path $env:TEMP ("ResearchTwin-demo-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $demoDir | Out-Null
$dbPath = Join-Path $demoDir "researchtwin.sqlite"
$env:DATABASE_URL = "sqlite:///" + $dbPath.Replace('\', '/')
$env:RATE_LIMIT_HASH_SECRET = [guid]::NewGuid().ToString("N")
$env:RATE_LIMIT_REQUIRE_SHARED_DATABASE = "false"
$env:RATE_LIMIT_TRUST_CF_CONNECTING_IP = "false"
$env:FRONTEND_ORIGINS = "http://127.0.0.1:5500"
uvicorn app.main:app --reload --port 8000
```

The application creates missing tables through SQLAlchemy `create_all()` when the backend imports. This creates a new empty schema; it is not a migration system and must not be treated as a safe upgrade for an existing production database.

### Administrator provisioning

Public registration creates student or faculty accounts only. To provision an administrator, first start the backend once against the intended database so its schema exists. In a second PowerShell window, from `backend/`, set the **same** `DATABASE_URL`, then run:

```powershell
$env:DATABASE_URL = 'sqlite:///C:/path/to/the/same/researchtwin.sqlite'
$env:RESEARCHTWIN_ENABLE_ADMIN_PROVISIONING = 'YES'
python .\provision_admin.py
```

The CLI displays a sanitized database label, requires the exact typed confirmation `CREATE ADMIN`, and prompts for a new password without echoing it. Use a unique password of at least 16 characters. The enable flag is for this one CLI process; never set it on the web service. See [Administrator provisioning](backend/ADMIN_PROVISIONING.md).

### Importing the bundled researcher directory

The import source is `backend/data/researchers.csv`; the API does not accept an arbitrary uploaded file. After signing in as an administrator, call `POST /researchers/import` with that account's bearer token. Repeating the import is idempotent. For example, after setting `$adminEmail` and `$adminPassword` in the current PowerShell session:

```powershell
$login = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/auth/login' -Method Post -ContentType 'application/json' -Body (@{email=$adminEmail; password=$adminPassword} | ConvertTo-Json)
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/researchers/import' -Method Post -Headers @{Authorization="Bearer $($login.access_token)"}
```

Do not paste real passwords into shared command histories or commit them to files.

### Backend startup commands

Canonical command, from `backend/`:

```powershell
uvicorn app.main:app --reload --port 8000
```

Root compatibility command, from the project root:

```powershell
uvicorn main:app --reload --port 8000
```

Both launch paths use the backend application. For local smoke checks, `GET http://127.0.0.1:8000/health` checks database availability and `GET http://127.0.0.1:8000/ready` checks database, active model artifact, and limiter readiness.

### Frontend startup

From the project root, serve the static frontend and open `http://127.0.0.1:5500/researchtwin.html`:

```powershell
npx serve frontend --listen 5500 --no-clipboard
```

There is no frontend build step. `frontend/frontend-config.js` selects the local API only on localhost addresses and the Render API only on the documented production Netlify host; any other hostname leaves the API unset and the client fails closed with a configuration error. A static host does not automatically inject environment variables into JavaScript. To override the API deliberately, assign `window.RESEARCHTWIN_API_BASE` before `frontend-config.js` loads; `api-client.js` accepts only a bare HTTP(S) origin, permits plain `http` only for loopback, and rejects credentials, paths, query strings, and fragments.

The detailed isolated Playwright setup is in [tests/e2e/README.md](tests/e2e/README.md).

## Database

SQLAlchemy models live in `backend/app/models.py`. The application uses SQLite by default at the absolute path `backend/researchtwin.db`, or uses `DATABASE_URL` when configured. PostgreSQL URLs are normalized to the `postgresql+psycopg` driver. SQLite foreign-key enforcement is enabled.

Tables cover users and hashed bearer sessions; researcher directory records; student and faculty profiles; admin-verified faculty/researcher links; collaboration requests; roadmap progress; shared rate-limit counters; and append-only audit events.

### Fresh database setup

For local SQLite, set an explicit new path under the operating system temporary directory as shown in the local demo setup, then start the backend. On startup, `Base.metadata.create_all()` creates missing tables for SQLite only. PostgreSQL schemas are created exclusively by Alembic migrations.

### Schema migrations

Alembic is configured from `backend/` (`alembic.ini`, `migrations/`). Revision `0001_baseline` matches the schema that `create_all()` produced before migrations were introduced; `tests/test_migrations.py` checks it against the models, a fresh upgrade, an existing stamped database, a downgrade, and an incompatible upgrade.

Run from `backend/` with `DATABASE_URL` pointing at the target database:

```powershell
alembic current
alembic upgrade head          # fresh database
alembic stamp 0001_baseline   # one-time mark for an existing unchanged database
alembic check                 # confirm models and the migration head agree
```

Never point migration commands at production without an approved change: back up first, rehearse on a restored copy, review the generated revision, run one revision as a one-off step, verify constraints and data, and retain a tested restore path. Downgrades drop data and are not a recovery plan. See [Security assessment](SECURITY_ASSESSMENT.md), [Production configuration checklist](PRODUCTION_CONFIGURATION_CHECKLIST.md), and [Repository cleanup inventory](REPOSITORY_CLEANUP_INVENTORY.md).

### Backups and recovery

`backend/scripts/database_backup.py` creates checksummed backups with a manifest, verifies them, reports capacity and session-retention indicators, and restores only to a new path. SQLite backups use the online-backup API; PostgreSQL backups use `pg_dump`. Verification works without a manifest (read-only), but restore requires the manifest by default. A legacy backup with no manifest can be restored only after verification and an explicit `--allow-manifestless` opt-in. The free hosting tier is not assumed to provide durable backups.

```powershell
cd backend
python scripts/database_backup.py status --source researchtwin-demo.db
python scripts/database_backup.py backup --source researchtwin-demo.db --destination ..\backups\snapshot.db
python scripts/database_backup.py verify --backup ..\backups\snapshot.db
python scripts/database_backup.py restore --backup ..\backups\snapshot.db --target ..\restore-drill.db
```

Backup cadence, retention, restore drills, account deletion, personal-data export, and capacity monitoring are documented in [Disaster recovery](DISASTER_RECOVERY.md).

## API Endpoints

All protected routes require a bearer token. Student and faculty profile routes operate on the authenticated account; clients cannot choose another owner ID.

### Authentication
- `POST /auth/register` — register a student or faculty account.
- `POST /auth/login` — authenticate and receive a bearer token.
- `POST /auth/logout` — revoke the current session.
- `GET /auth/me` — get the current account.

### Profiles and recommendations

- `GET` / `PUT /students/me/profile` — read or save the current student's profile.
- `POST /students/me/recommendations` — recommend researchers from the authenticated student's saved profile (`top_k` 1–10).
- `GET` / `PUT /faculty/me/profile` — read or save the current faculty profile.
- `GET /faculty/me/researcher-link` and `PUT /faculty/me/researcher-link` — view or confirm an administrator-assigned link.
- `POST /recommendations/researchers` — deprecated compatibility endpoint; still requires student authentication and uses the saved profile. Prefer `/students/me/recommendations`.

### Researcher directory and administration

- `GET /researchers/` and `GET /researchers/{id}` — public directory reads. List requests support `offset` and `limit` (maximum 500), plus search filters.
- `POST /researchers/`, `PUT /researchers/{id}`, and `DELETE /researchers/{id}` — administrator-only shared directory mutations.
- `POST /researchers/import` — administrator-only idempotent import of the bundled CSV at `backend/data/researchers.csv`.
- `PUT /admin/faculty/{id}/researcher-link` and `DELETE /admin/faculty/{id}/researcher-link` — administrator-only faculty/researcher assignment and removal, both audited.
- `GET /admin/users` — administrator-only account listing with role and active filters.
- `PUT /admin/users/{id}/active`, `PUT /admin/users/{id}/role`, `POST /admin/users/{id}/sessions/revoke`, and `POST /admin/users/{id}/password-reset` — administrator-only lifecycle operations. Self status/role changes are rejected and sensitive actions revoke sessions.
- `GET /admin/users/{id}/data-export` — administrator-only personal-data export without credential or token material.
- `GET /admin/audit-events` — administrator-only audit history with action, target, and pagination filters.

### Collaboration and roadmap

- `POST /students/me/collaboration-requests` and `GET /students/me/collaboration-requests` — create and list the current student's requests.
- `GET /faculty/me/collaboration-requests` and `PUT /faculty/me/collaboration-requests/{id}/decision` — faculty inbox and decisions for the linked researcher.
- `GET /students/me/researchers/{id}/roadmap` and `PUT /students/me/researchers/{id}/roadmap/progress` — get the current student's roadmap and persist milestone progress.

### Health and readiness

- `GET /health` — database health.
- `GET /ready` and `GET /readiness` — readiness including database, model artifact, and limiter configuration.
- FastAPI schema/docs are served by the application at `/openapi.json` and `/docs`.

## Institution model (decision blocked)

The current implementation has no institution or tenant scoping: one deployment serves one shared researcher directory, and registration is open to the configured frontend. Whether an institution should run a separate deployment or share a multi-tenant deployment has **not** been established by product documentation or code. That decision is recorded as blocked; do not add a `tenant_id` or similar field until isolation requirements and the ownership model are explicitly approved.

## Features

Researcher recommendations combine textual, semantic, research-area, expertise, skill, project, and publication signals. The active model expects seven features in a fixed order and returns ranked scores with explanations.

Student profiles drive personalized recommendations and skill-gap roadmaps; saved progress is scoped to the student's account and researcher.

Faculty collaboration inbox access depends on the administrator-verified faculty/researcher link.

Administrator accounts get an account-management console after sign-in: role and status filters, activation/deactivation, role changes, session revocation, password reset, faculty/researcher link assignment, per-account data export, and a filterable audit log. Every operation is enforced again by the API; the console is only a client of the administrator-only endpoints.

Authentication uses server-side role and ownership checks; the frontend's role-aware controls are only a user-interface aid.

Authentication and recommendation endpoints use configured database-backed rate limits. Shared production enforcement requires PostgreSQL.

Session and race guards prevent stale frontend responses from replacing newer state.

## Testing

Run backend tests from `backend/` with the canonical Python 3.11 environment:

```powershell
C:\Users\Venkatesh\researchtwin-venv311\Scripts\python.exe -m pytest -q
```

```powershell
npm test
```

Run actual-browser journeys only against a new temporary SQLite database. Follow every guard and setup step in [tests/e2e/README.md](tests/e2e/README.md), then execute:

```powershell
node tests/e2e/researchtwin.phase3.e2e.cjs
```

`npm test` runs the complete frontend suite, including headers and configuration checks. Historical test counts in older audit reports are snapshots; the current local verified run is 316 backend and 101 frontend tests plus 13 browser journey groups in the pinned Python 3.11 environment. Phase 13 environment and performance measurements are recorded in the [release checklist](PRODUCTION_RELEASE_CHECKLIST.md).

See [backend testing notes](backend/TESTING.md) for isolated fixtures and production-like checks.

## Configuration

### Environment Variables

| Variable | Purpose and current behavior |
|---|---|
| `DATABASE_URL` | SQLAlchemy database URL. If unset, local development uses SQLite at `backend/researchtwin.db`; when `RENDER=true` the application refuses to start without it. Production shared rate limits require PostgreSQL. |
| `FRONTEND_ORIGINS` | Comma-separated browser origins added to the CORS allowlist. The backend also includes the two localhost port-5500 origins. |
| `RATE_LIMIT_HASH_SECRET` | Required by rate limiting; use a randomly generated value of at least 32 bytes. Never log or commit it. |
| `RATE_LIMIT_REQUIRE_SHARED_DATABASE` | Set `true` in multi-instance production; requires PostgreSQL. Local SQLite demo uses `false`. |
| `RATE_LIMIT_TRUST_CF_CONNECTING_IP` | Trusts a valid `CF-Connecting-IP` value only when this is `true` **and** the direct peer is listed in `RATE_LIMIT_TRUSTED_PROXY_CIDRS`. Enable only if the ingress proxy is verified to overwrite or secure this header; otherwise the peer address is used. |
| `RATE_LIMIT_TRUSTED_PROXY_CIDRS` | Comma-separated networks of verified ingress proxies. An empty or invalid list means no proxy is trusted. Do not guess values. |
| `RATE_LIMIT_REGISTER_MAX`, `RATE_LIMIT_REGISTER_WINDOW_SECONDS` | Registration limit; current Render file sets 5 per 3600 seconds. |
| `RATE_LIMIT_LOGIN_MAX`, `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | Login limit; current Render file sets 10 per 900 seconds. |
| `RATE_LIMIT_RECOMMENDATION_MAX`, `RATE_LIMIT_RECOMMENDATION_WINDOW_SECONDS` | Recommendation limit; current Render file sets 8 per 300 seconds. |
| `MAX_REQUEST_BODY_BYTES` | Request body limit; current default and Render value are 65,536 bytes. |
| `AUTH_SESSION_TTL_SECONDS` | Optional session lifetime in seconds; default is 43,200 seconds (12 hours). |
| `RESEARCHTWIN_ENABLE_ADMIN_PROVISIONING` | Set to `YES` only for the trusted one-off administrator provisioning CLI; never expose it in the web service environment. |

Never put secret values in this README or other tracked files.

### Frontend API URL

`frontend/frontend-config.js` selects `http://127.0.0.1:8000` on local hostnames and `https://researchtwin-api.onrender.com` only on the documented production Netlify host (`starlit-empanada-a323e3.netlify.app`). Any other hostname is left unconfigured, and `frontend/api-client.js` then fails closed with a configuration error instead of calling an unintended backend. The optional override is a JavaScript global (`window.RESEARCHTWIN_API_BASE`), not a Netlify environment variable; it must be a bare HTTP(S) origin (plain `http` only for loopback). Set the global before the config script loads if a different API host is intentionally used, and add that host to the Netlify CSP `connect-src` deliberately.

## Deployment

### Local demo

Use the isolated SQLite setup above, start the backend and static frontend locally, provision a test administrator through the CLI, and import the bundled researcher CSV. Keep the demo database in a temporary directory when you want a clean run. No production service or data is needed for local development.

### Production preparation (not a deployment instruction)

The repository configures a Render Python service (`rootDir: backend`, Python 3.11.11, `pip install -r requirements.txt -c constraints.txt`, ONNX model fetch at build time, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, readiness path `/ready`) and a Netlify static publish directory `frontend`. Configure a durable shared PostgreSQL database and the environment variables listed above in the hosting dashboard. Set the exact frontend origin in `FRONTEND_ORIGINS`; configure the frontend API host intentionally. Confirm the active seven-feature model artifact is included in the release bundle.

The YAML does not declare a PostgreSQL service, persistent disk, plan, or migration command. The Render/Netlify dashboards and live app were not inspected as part of these documentation updates. Complete [Production configuration checklist](PRODUCTION_CONFIGURATION_CHECKLIST.md) before any deployment. No deploy, push, or live-service change is part of this repository setup guide.

## Security Considerations

Passwords use PBKDF2-HMAC-SHA256 with a per-user salt; session tokens are random and only SHA-256 hashes are stored in the database. Sessions expire after 12 hours by default and logout revokes the stored session.

The browser stores only the bearer token in `sessionStorage`, never the password. JavaScript can read that token, so a successful XSS attack can steal the current session. Cookie migration needs HttpOnly/Secure/SameSite cookies, CSRF protections, credentialed CORS, and coordinated frontend/backend tests; it has not been introduced.

Researcher shared writes/import and faculty link assignment require administrator authorization. Public registration does not allow administrator roles. CORS does not allow credentials. Production origins must be exact. The repository configures CSP, HSTS, frame, MIME-sniffing, referrer, and permissions headers in `frontend/_headers` (Netlify reads this file from the publish directory, not from `netlify.toml`); `tests/frontend/headers.test.cjs` statically verifies the directives and that every external asset on `index.html` and `researchtwin.html` is permitted. Live response headers were not inspected.

Successful login, failed login, and logout write audit events. Events exclude passwords, hashes, tokens, authorization headers, and request bodies; unknown login emails are not stored, and repeated failures are deduplicated per identity per login window. See [Security assessment](SECURITY_ASSESSMENT.md) for the exact failure and growth behavior.

Authentication and recommendation limits share counters across workers only when they use the same PostgreSQL database. Production Render configuration requires this mode. PostgreSQL schema changes go through Alembic (`backend/migrations/`); `create_all()` runs for SQLite only and is not an existing-schema upgrade plan.

See the evidence and remaining security risks in [Security assessment](SECURITY_ASSESSMENT.md).

## Troubleshooting

- `401 Unauthorized`: sign in again; the session may be expired or revoked.
- `403 Forbidden`: the authenticated account lacks the role or ownership needed for the route.
- `413 Request body is too large`: reduce the request body; the default cap is 65,536 bytes.
- `422 Unprocessable Entity`: validate the request schema and `top_k` range (1–10).
- `429 Too Many Requests`: wait for the `Retry-After` window before retrying.
- `503 Request protection is not configured`: provide `RATE_LIMIT_HASH_SECRET` with at least 32 bytes. If shared-database mode is enabled, use PostgreSQL.
- `503` readiness failure: check database connectivity, the active model artifact path, and rate-limit configuration.
- Empty recommendations: save the authenticated student's profile first and ensure researcher rows exist. The API ignores client-supplied profiles for the protected recommendation routes.
- Session restored after refresh: the token persists in `sessionStorage`; logging out revokes it. A token can still disappear if browser storage is cleared.
- API fails from a local browser: start the API on port 8000 and serve the frontend on port 5500; check the browser console, CORS origin, and network tab.

## License

Proprietary - All rights reserved

## Support

For issues and questions:
- GitHub Issues: [ResearchTwin repository](https://github.com/venkatesh19-prog/ResearchTwin/issues)

## Changelog

### Phase G (2026-10-31)
- Added collaboration system with admin-verified faculty-researcher linking
- Implemented roadmap progress persistence with atomic updates
- Enhanced security with rate limiting and input validation
- Fixed session race conditions with epoch guards and single-flight logic
- Added the initial automated test suite (219 backend and 78 frontend tests at the Phase G snapshot)
- Improved directory filtering with department and skill filters
- Added expandable researcher details in directory view

### Phase F (2026-10-25)
- Initial ML recommendation engine with SHAP explainability
- Student and faculty profile management
- Researcher directory with search
- Authentication and authorization system
- Basic roadmap feature

### Phase 4 — final development hardening (2026-11-01)
- Reconciled setup, API, environment, and deployment instructions with the current source configuration.
- Added production configuration, security, and cleanup inventories.
- Reverified 228 backend tests, 79 frontend tests, and 12 browser journey groups locally; see the release checklist for warnings and setup details.
- Production remains unverified.
