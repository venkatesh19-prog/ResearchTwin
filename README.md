# ResearchTwin

AI-powered researcher–student collaboration platform. Students save a research profile and receive ranked, explained researcher matches plus skill-gap roadmaps; faculty are linked to directory records by an administrator; both sides collaborate through requests, workspaces, teams, opportunities, theses, proposals, publications, and research-intelligence analytics.

**This `README.md` is the single authoritative documentation file for the project.** Setup, architecture, data model, migrations, configuration, API reference, security, testing, deployment, disaster recovery, and troubleshooting all live here. There is no separate `docs/` tree and no API contract file to keep in sync — `git ls-files "*.md"` returns this file alone. Where an older phase report, audit note, or chat summary disagrees with this file or with the code, this file and the code are right and the other text is not a source of truth.

## Table of contents

- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Administrator provisioning](#administrator-provisioning)
- [Researcher directory import](#researcher-directory-import)
- [Frontend startup](#frontend-startup)
- [Configuration](#configuration)
- [Database](#database)
- [Data model](#data-model)
- [Migrations](#migrations)
- [Backups and restore](#backups-and-restore)
- [Database hosting and migration constraints](#database-hosting-and-migration-constraints)
- [HTTP conventions](#http-conventions)
- [API reference](#api-reference)
- [Rate and size limits](#rate-and-size-limits)
- [Features](#features)
- [Security](#security)
- [Residual risks](#residual-risks)
- [Testing](#testing)
- [Deployment](#deployment)
- [Operational procedures](#operational-procedures)
- [Troubleshooting](#troubleshooting)
- [Known limitations and open decisions](#known-limitations-and-open-decisions)
- [License](#license)
- [Support](#support)

## Architecture

FastAPI backend, SQLAlchemy 2 ORM, Alembic migrations, and a static vanilla-JavaScript frontend with no build step. The backend owns authentication, role and ownership checks, researcher access policy, collaboration, roadmap persistence, rate limiting, and model inference. The frontend is a client; it never authorizes anything.

```text
backend/app/main.py             Application factory, middleware, health/readiness, DB error handler
backend/app/db_url.py           Database URL resolution and precedence
backend/app/database.py         Engine, SessionLocal, get_db
backend/app/models.py           43 SQLAlchemy tables
backend/app/schemas.py          Pydantic request/response models (extra="forbid")
backend/app/api/                20 router modules
backend/app/api/deps.py         Role and session dependencies
backend/app/services/           auth, recommendation, research_intelligence, rate_limit, backup, importers
backend/migrations/             Alembic environment and 12 revisions
backend/models/                 Model artifacts used by the recommendation service
backend/data/                   Researcher import source and matching data
backend/scripts/                database_backup.py and fetch_embedding_model.py, nothing else
backend/seed_researchers.py     Guarded demo seeder — refuses a non-empty table and needs RESEARCHTWIN_ALLOW_DEMO_SEED=YES
backend/tests/                  Pytest unit and integration coverage
frontend/researchtwin.html      Main application
frontend/research-2.0.js        Research 2.0 console (workspaces, teams, opportunities, outputs)
frontend/api-client.js          Browser API client, session handling, base-URL validation
frontend/frontend-config.js     Browser API base URL selection
frontend/_headers               Netlify security headers and CSP (read from the publish directory)
frontend/index.html             Frontend launcher
tests/e2e/                      Playwright browser journeys
tests/frontend/                 Node test suite including header and configuration checks
main.py                         Root compatibility entry point for the backend (a real shim)
researchtwin.html               Root redirect stub (window.location.replace to frontend/researchtwin.html) — not the app itself
index.html                      Root page of an unrelated "UMS – University Management System" mock-up; its only script opens frontend/researchtwin.html in a new tab and it holds no API client
supervised project/             Separate prototype: its own FastAPI mock engine (main.py), CSV flat-file data and HTML pages — not part of the deployed application
```

`supervised project/` is a standalone prototype, not a second deployment target. `supervised project/main.py:18-23` builds its own `FastAPI` app that answers from CSV files with `allow_origins=["*"]`, and it shares no code, schema, or authentication with `backend/app`. Netlify publishes only `frontend` (`netlify.toml:2`) and Render builds only `backend` (`render.yaml:5`), so nothing in that directory is reachable in production — and it must never be run, documented, or demoed as the production application.

The serving recommendation code expects `backend/models/researchtwin_logistic_v2_7features.joblib`. Three of the four `.joblib` files under `backend/models/` are tracked by Git — `researchtwin_logistic.joblib`, `researchtwin_logistic_render.joblib`, and the active `researchtwin_logistic_v2_7features.joblib`; `researchtwin_logistic_compat_test.joblib` is **not** tracked and its purpose is undocumented. `researchtwin_logistic_render.joblib` is an older, different feature bundle and is **not** a substitute for the active seven-feature artifact. Being tracked is not sufficient for a clean checkout to serve: the ONNX embedding directory `backend/models/all-MiniLM-L6-v2-onnx/` is gitignored, so `/ready` **fails on a fresh clone until `scripts/fetch_embedding_model.py` has run**. Readiness does not pin the active `.joblib` digest — it validates lazy module imports, the ONNX model and tokenizer files, and the SHA-256 of the SHAP background data against the `training_data_sha256` recorded inside the bundle (`backend/app/services/recommendation.py:194-234`). See [Readiness](#readiness).

## Quick start

### Prerequisites

- **Python 3.11.** The pinned dependency set (notably `onnxruntime` and the `numpy`/`scipy` builds used by the model stack) does not have usable wheels for Python 3.14, so 3.11 is the supported runtime for the backend and its tests.
- Node.js and npm for the frontend test suite and the Playwright browser journeys.
- Internet access twice, not once: `scripts/fetch_embedding_model.py` downloads the pinned ONNX model and tokenizer, and `npx serve` fetches the `serve` package on first use (it is **not** a devDependency). Nothing is downloaded while serving a request — if the embedding files are missing the application refuses readiness instead of fetching them.
- Git Bash (or any POSIX shell) if you run the repository helper scripts on Windows.

### Backend

Create the environment **outside** the repository — `.gitignore` already excludes in-repo environments, but keeping it outside also prevents the trap below — then install with the pinned constraints and fetch the embedding model. From `backend/`:

```powershell
py -3.11 -m venv "$env:LOCALAPPDATA\ResearchTwin\venv-py311"
& "$env:LOCALAPPDATA\ResearchTwin\venv-py311\Scripts\Activate.ps1"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt -r requirements-dev.txt
python -m pip check
python scripts/fetch_embedding_model.py
python -c "import sys, onnxruntime; print(sys.version.split()[0])"   # must print 3.11.x
```

**Do not use a repository-local `backend/.venv`.** One exists on this workstation and is a different interpreter (`backend/.venv/pyvenv.cfg` → 3.14.3) without `onnxruntime`, so `pytest` fails during collection and recommendation routes fail at runtime. An editor that auto-activates it silently changes your results.

`fetch_embedding_model.py` writes to `backend/models/all-MiniLM-L6-v2-onnx/` at a pinned revision with SHA-256 verification (`scripts/fetch_embedding_model.py:13-17`). That directory is gitignored (`.gitignore:35`) — it is the one thing a fresh clone cannot have, so skipping this step makes `/ready` fail even though the tracked joblib artifact is present.

Run against a fresh temporary SQLite database for a clean demo. Leaving `DATABASE_URL` unset selects the existing repository file `backend/researchtwin.db` instead. A second file, `researchtwin.db` at the **repository root**, also exists on this machine; it is untracked and gitignored, is **not** opened by the application (`db_url.py:18` resolves the `backend/` path), and must not be used as a backup, restore, or migration target.

```powershell
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

Use `--workers 1` whenever you run the app outside `--reload`. Cluster rebuilds and other background maintenance take **process-local locks**, so more than one worker process can run the same rebuild concurrently. Horizontal scaling is achieved with one worker per instance behind a load balancer, not with multiple workers per instance.

The application creates missing tables through `Base.metadata.create_all()` when the backend imports — for SQLite only. This creates a new empty schema; it is not a migration system and must not be treated as an upgrade path for an existing database.

Canonical command from `backend/`:

```powershell
uvicorn app.main:app --reload --port 8000
```

Root compatibility command from the project root:

```powershell
uvicorn main:app --reload --port 8000
```

Both launch paths serve the same application. Smoke checks: `GET http://127.0.0.1:8000/health` probes the database, `GET http://127.0.0.1:8000/ready` checks database, Alembic revision (PostgreSQL), model artifact, and limiter configuration.

## Administrator provisioning

Public registration creates student or faculty accounts only — there is no admin-registration route and no default password. To provision an administrator, first start the backend once against the intended database so its schema exists. Then, in a second shell from `backend/`, set the **same** `DATABASE_URL` and run:

```powershell
$env:DATABASE_URL = 'sqlite:///C:/path/to/the/same/researchtwin.sqlite'
$env:RESEARCHTWIN_ENABLE_ADMIN_PROVISIONING = 'YES'
python .\provision_admin.py
```

The CLI displays a sanitized database label, requires the exact typed confirmation `CREATE ADMIN`, and prompts for the password without echoing it. Password length is bounded **both ways — 16 to 128 characters** (`provision_admin.py:12-13,40-46`), so a very long passphrase is rejected rather than accepted. The enable flag must equal `YES` exactly, case-sensitive (`:19`), and an email that already exists is refused instead of re-roled (`:49-52`). The enable flag belongs to this one CLI process only — never set it in the web service environment.

Treat provisioning as a reviewed operation: pass [Confirm the database target first](#confirm-the-database-target-first-mandatory) before running it, record who authorized the account, and never run it against a hosted database without an approved change.

> The tool never prints the database URL, password, or bearer tokens. A successful run does print the new **administrator email address**, so treat CLI output as account-identifying information when you paste it into an issue or chat.

Do not paste real passwords into shared command histories or commit them to files.

## Researcher directory import

The import source is `backend/data/researchers.csv`; the API does not accept an arbitrary uploaded file. After signing in as an administrator, call `POST /researchers/import` with that account's bearer token. Repeating the import is idempotent.

```powershell
$login = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/auth/login' -Method Post -ContentType 'application/json' -Body (@{email=$adminEmail; password=$adminPassword} | ConvertTo-Json)
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/researchers/import' -Method Post -Headers @{Authorization="Bearer $($login.access_token)"}
```

## Frontend startup

From the project root, serve the static frontend and open `http://127.0.0.1:5500/researchtwin.html`:

```powershell
npx serve frontend --listen 5500 --no-clipboard
```

There is no frontend build step. `frontend/frontend-config.js` selects the local API only on localhost addresses and the production API only on the documented production Netlify host; any other hostname leaves the API unset, and `frontend/api-client.js` fails closed with a configuration error rather than calling an unintended backend. A static host does **not** inject environment variables into JavaScript. To override deliberately, assign `window.RESEARCHTWIN_API_BASE` before `frontend-config.js` loads; the client accepts only a bare HTTP(S) origin, permits plain `http` only for loopback, and rejects credentials, paths, query strings, and fragments.

## Configuration

### Environment variables

Every name below is read by the application code. Defaults come from `backend/app/services/rate_limit.py`, `services/recommendation.py`, `db_url.py`, `middleware.py:40` (`MAX_REQUEST_BODY_BYTES`), `services/auth.py:62` (`AUTH_SESSION_TTL_SECONDS`), and `services/funding_sources.py:15` (`FUNDING_GRANTS_GOV_ENABLED`).

| Variable | Default / behavior |
|---|---|
| `DATABASE_URL` | SQLAlchemy database URL. Unset → SQLite at `backend/researchtwin.db`. `postgres://` and `postgresql://` are rewritten to `postgresql+psycopg://`; anything else unchanged. **Set-but-blank is a third state, and the two entry points resolve it differently.** The application calls `resolve_database_url()` with no argument, so the opt-in file is still read (`db_url.py:86-90`) — but loading uses `os.environ.setdefault` (`:48`), so the blank process value wins over the file's URL and resolution falls through to the same SQLite default without warning. Alembic passes `configured_url or os.getenv("DATABASE_URL")` (`:121`), which makes `raw_url` non-`None` and skips the file *and* its missing-file check outright. When `RENDER=true` the application refuses to start without a non-blank value (`:95-101`). Production shared rate limits require PostgreSQL. |
| `RENDER` | Platform flag. `true` makes a missing `DATABASE_URL` a hard startup failure instead of a silent SQLite fallback. |
| `RESEARCHTWIN_ENV_FILE` | Opt-in dotenv file for local work. Unset by default, so no file is ever read implicitly. For the **application** it takes effect whenever it names a file, because `backend/app/database.py:12` calls `resolve_database_url()` with no argument and the read is gated on `raw_url is None` (`db_url.py:86`) — a real process variable still wins (`:48`), so a set-but-**blank** `DATABASE_URL` shadows the file's URL and the app resolves to the SQLite default. **Alembic** differs: `resolve_migration_url` passes `configured_url or os.getenv("DATABASE_URL")` (`:121`) with `alembic.ini:5` leaving `sqlalchemy.url` empty, so a blank `DATABASE_URL` makes `raw_url` non-`None`, the file is never read, and its missing-file typo check never fires. A missing named file raises `FileNotFoundError` (`:58-67`); the path may be absolute or relative to the repository root (`:22`). Never point this at the workstation's existing `.env.local` for rehearsal work — see [Confirm the database target first](#confirm-the-database-target-first-mandatory). |
| `FRONTEND_ORIGINS` | Comma-separated browser origins added to the CORS allowlist. The backend also always includes the two localhost port-5500 origins. `allow_credentials=False`. |
| `RATE_LIMIT_HASH_SECRET` | Required by rate limiting. Length must be ≥ 32 bytes; otherwise limiter-dependent routes return `503 Request protection is not configured`. Generate randomly; never log or commit it. |
| `RATE_LIMIT_REQUIRE_SHARED_DATABASE` | `true` in multi-instance production; readiness then requires a PostgreSQL bind. Local SQLite demo uses `false`. |
| `RATE_LIMIT_TRUST_CF_CONNECTING_IP` | Honors `CF-Connecting-IP` only when exactly `true` **and** the direct TCP peer is inside `RATE_LIMIT_TRUSTED_PROXY_CIDRS`. Otherwise the peer address is used. Enable only after proving the ingress overwrites or strips this header. |
| `RATE_LIMIT_TRUSTED_PROXY_CIDRS` | Comma-separated CIDRs of verified ingress proxies. Empty or invalid → no proxy is trusted. Do not guess values. |
| `RATE_LIMIT_REGISTER_MAX` / `RATE_LIMIT_REGISTER_WINDOW_SECONDS` | `5` / `3600` seconds. Keyed per IP plus normalized email. |
| `RATE_LIMIT_LOGIN_MAX` / `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | `10` / `900` seconds. Keyed per IP plus normalized email. |
| `RATE_LIMIT_RECOMMENDATION_MAX` / `RATE_LIMIT_RECOMMENDATION_WINDOW_SECONDS` | `8` / `300` seconds. |
| `RATE_LIMIT_NETWORK_MAX` / `RATE_LIMIT_NETWORK_WINDOW_SECONDS` | `6` / `60` seconds — research-intelligence network and graph endpoints. |
| `RATE_LIMIT_OPPORTUNITY_APPLY_MAX` / `RATE_LIMIT_OPPORTUNITY_APPLY_WINDOW_SECONDS` | `20` / `3600` seconds — opportunity applications. |
| `RECOMMENDATION_MAX_CONCURRENCY` | `2`. A process-local `BoundedSemaphore` around model inference. Positive integers only; invalid or non-positive values fall back to `2`. |
| `MAX_REQUEST_BODY_BYTES` | `65536`. Enforced by request middleware; larger bodies get `413`. |
| `AUTH_SESSION_TTL_SECONDS` | `43200` (12 hours). A positive value overrides; invalid values fall back to 12 hours. Choose an explicit bounded production policy. |
| `FUNDING_GRANTS_GOV_ENABLED` | Opts the grants.gov funding feed in. Disabled by default; the fetcher stores no credentials. See [Grant-feed import](#grant-feed-import). |
| `RESEARCHTWIN_ALLOW_DEMO_SEED` | Must equal `YES` for `backend/seed_researchers.py` to write any rows (`seed_researchers.py:380-384`). The seeder then reads `DATABASE_URL` directly rather than resolving it (`:377`), so it ignores `RESEARCHTWIN_ENV_FILE` and refuses any non-SQLite or in-memory URL (`:385-386`) — **it cannot write to a hosted PostgreSQL database at all** — requires the typed confirmation `SEED EMPTY SQLITE DATABASE` (`:388-393`), and aborts if the researcher table already contains a row (`:343-346`), so it cannot overwrite a directory. |
| `RESEARCHTWIN_ENABLE_ADMIN_PROVISIONING` | `YES` only for the trusted one-off provisioning CLI. Never set it in the web service environment. |

Rate-limit numbers are read through `_positive_setting()`, which ignores non-numeric and non-positive values, so a typo in the hosting dashboard silently keeps the default. Only the `RATE_LIMIT_*` pairs in the table above are environment-configurable; limiter scopes that reuse a constant (team recommendations, collaboration requests, opportunity matches, topic prediction) move with the recommendation pair, and `researcher-verification` is hardcoded at 5 per 3600 s and moves with nothing (`api/verification.py:25-26`). `MAX_SEMANTIC_CLUSTER_RESEARCHERS` is **not** an environment variable — it is a source constant of `2000` in `backend/app/services/research_intelligence.py`, and a semantic rebuild above that size is rejected rather than attempted.

Never put secret values in this README or any other tracked file.

### Frontend API base URL

`frontend/frontend-config.js` selects `http://127.0.0.1:8000` on local hostnames and `https://researchtwin-api.onrender.com` only on the production Netlify host `starlit-empanada-a323e3.netlify.app`. Any other hostname is left unconfigured and `api-client.js` fails closed. The override is a JavaScript global (`window.RESEARCHTWIN_API_BASE`), not a Netlify environment variable, and must be a bare HTTP(S) origin (plain `http` only for loopback). If you point the frontend at a different API host, add that host to the Netlify CSP `connect-src` deliberately.

**Three places pin the API origin, and all three must change together** when the API host changes: `frontend/frontend-config.js`, the CSP `connect-src` in `frontend/_headers`, and `FRONTEND_ORIGINS` on the backend. Changing one and not the others produces a site that loads, authenticates against the wrong host, or is blocked by the browser before the request leaves.

### Readiness

`GET /ready` (alias `GET /readiness`) is the single gate used by the platform health check. It verifies, in order:

1. `SELECT 1` against the bound database.
2. On PostgreSQL, that `alembic_version` equals the current head. A mismatch is a readiness failure — the app refuses to serve a schema it does not understand.
3. `verify_serving_artifacts()`, in four ordered parts (`services/recommendation.py:194-234`): the lazy runtime modules (`onnxruntime`, `tokenizers`, `shap`) are **locatable** — the check is `importlib.util.find_spec(...) is not None` (`:176-191`), so a module that is installed but fails to import still passes this part; `verify_model_files()` confirms the ONNX `model.onnx` and `tokenizer.json` exist under `backend/models/all-MiniLM-L6-v2-onnx/` (`services/semantic_matching.py:63-85`); the model bundle loads; and the SHAP background CSV exists with a SHA-256 equal to the `training_data_sha256` recorded **inside** the bundle. The active `.joblib` file itself is never digest-pinned — its integrity rests on Git and the trusted-source policy.
4. `is_rate_limit_ready(db)`: a ≥ 32-byte `RATE_LIMIT_HASH_SECRET`, and PostgreSQL when shared mode is required.

`GET /health` only probes the database with `SELECT 1` and returns `503 {"status":"unhealthy"}` when it is unreachable. Because engine creation and initialization run at import, an unreachable database can prevent the process from starting at all — in that state `/health` is not served, it is absent.

## Database

### URL resolution and precedence

`backend/app/db_url.py` resolves one source at a time:

1. An explicit, **non-blank** `DATABASE_URL` process variable, normalized (`postgres://`/`postgresql://` → `postgresql+psycopg://`; anything else unchanged). A variable set to an empty string is **not** "unset", and the two readers treat blank differently. The application calls `resolve_database_url()` with no argument (`database.py:12`), so the dotenv opt-in below *is* read — but loading uses `os.environ.setdefault` (`db_url.py:48`), so the blank process value still beats the file's URL and resolution falls through to step 3 silently. Alembic calls `resolve_migration_url` (`:121`), which passes `configured_url or os.getenv("DATABASE_URL")`; a blank value arrives as a non-`None` `raw_url`, so the opt-in and its missing-file check are skipped outright and step 3 applies. Clear it with `Remove-Item Env:\DATABASE_URL` (PowerShell) or `unset DATABASE_URL`, never by assigning an empty value.
2. Otherwise, when no process value occupies the name and `RESEARCHTWIN_ENV_FILE` names an existing dotenv file, the values in that file (a real process variable, blank included, still wins).
3. Otherwise SQLite at `backend/researchtwin.db`, resolved relative to the package. When `RENDER=true`, this fallback is a startup error rather than a silent SQLite.

To confirm which database a running process will open, without exposing credentials:

```bash
python -c "from app.database import engine; print(engine.url.render_as_string(hide_password=True))"
```

Never print or paste the un-redacted URL.

### Confirm the database target first (mandatory)

Run this pre-flight **before every** migration, restore, seed, provisioning command, or anything else that can write — including commands you believe are rehearsal-only. No command in this repository refuses to write to a production database on your behalf.

**Step 1 — record the intended target as identity, not as a name.** An approved change must name the provider **project identifier**, the **branch identifier**, and the **endpoint identifier** of the database it authorizes you to touch, plus a truncated SHA-256 fingerprint of the exact connection string. Those values belong in the change record, not in this file. A hostname that "looks like" a different server is **not** evidence of a safe target: pooled and direct endpoints for different branches share a domain and naming pattern, a copied string can resolve to production, and a branch can be promoted or reset under the same-looking host.

**Step 2 — prove the process resolves to the approved fingerprint**, without ever printing the URL:

```bash
# from backend/, after any environment setup you are about to use
python - <<'PY'
import hashlib
from getpass import getpass
from app.db_url import resolve_database_url

got = hashlib.sha256(resolve_database_url().encode()).hexdigest()[:12]
expected = getpass("Approved target fingerprint: ").strip().lower()
print("TARGET MATCHES" if got == expected
      else "MISMATCH - STOP: the resolved target is not the approved one")
PY
```

The fingerprint is entered, never echoed; the resolved URL is hashed in memory and discarded. A blank `DATABASE_URL` makes this print a *matching* fingerprint for the local SQLite file, which is why step 3 is not optional.

**Step 3 — prove the endpoint belongs to the approved project and branch** using the provider's own control plane (CLI or console listing a branch's endpoints), not by reading a connection string. Confirm the endpoint you are about to open is listed under the approved **branch** under the approved **project**. If the provider mapping is unavailable, stop; a resolved fingerprint proves only that the process will connect where the string says, not that the string names the branch you were authorized to change.

**Step 4 — for restore and rehearsal work, prove separation.** The restored copy and the migration target must be different branches, and both must be distinct from the source you backed up. Verify this through step 3's project/branch mapping. Never assert separation from hostname similarity alone, and never run the rehearsal `alembic upgrade head` in the same shell that holds the production connection string — use a fresh process whose only database variable is the rehearsal target.

**Do not use this workstation's `.env.local` for rehearsal work.** The existing gitignored file resolves to the hosted **production** branch — re-verified on 2026-11-11 by matching its endpoint host and `NEON_BRANCH` / `NEON_BRANCH_ID` keys against the provider's branch listing, and it does **not** match the rehearsal branch. Its keys are `DATABASE_URL`, `DATABASE_URL_UNPOOLED`, `NEON_BRANCH`, `NEON_BRANCH_ID` and `NEON_FUNCTION_HOST_SUFFIX`, and `load_env_files` injects **all** of them into the process (`db_url.py:37-48`, first write wins so an existing process value is never overwritten). Pointing `RESEARCHTWIN_ENV_FILE` at it while following any command below runs migrations against production. This mapping is a snapshot: branch hosts change when a branch is promoted, reset, or re-created, so re-run step 3 rather than trusting this sentence. Export a file for the specific rehearsal target instead, or pass `DATABASE_URL` explicitly in a fresh shell.

### Initialization

`Base.metadata.create_all(bind=engine)` runs at import for **SQLite only**. It issues `CREATE TABLE`/`CREATE INDEX` for missing objects and never alters, drops, or reseeds an existing table; the test suite asserts that existing rows survive a repeat of initialization. PostgreSQL schemas are created exclusively by Alembic.

There is no seed-on-boot and no `drop_all` anywhere in `backend/app`. A brand-new database therefore has **zero researchers** until an administrator imports `backend/data/researchers.csv`.

### Sessions and error handling

- `get_db` yields a `SessionLocal` and always closes it in `finally`; closing rolls back any uncommitted transaction, including when a handler raises mid-request.
- Sessions use `autocommit=False`, `autoflush=False`, `pool_pre_ping=True`.
- Write paths commit explicitly; the CSV import rolls back on failure.
- A `SQLAlchemyError` during a request is converted to `503 {"detail":"Database unavailable"}`. Logging records the exception **type** and the route only — never the DSN, SQL, or bound parameters.
- Limiter-dependent guards fail closed: a misconfigured limiter yields `503`, not an unthrottled route.

### Optional cloud Postgres for local work

A managed-Postgres CLI may write connection variables to a dotenv file (conventionally `.env.local`). That file is never read implicitly: local startup keeps using `backend/researchtwin.db`, the deployed backend keeps using its injected `DATABASE_URL`, and Alembic keeps using `DATABASE_URL` or SQLite. To target a cloud branch for one process, name a file **exported for that specific branch** — never reuse a file written for another target, and never use the pre-existing `.env.local` on this workstation, which resolves to the production branch:

```powershell
# from backend/ — after the pre-flight in "Confirm the database target first"
$env:RESEARCHTWIN_ENV_FILE = "<file-exported-for-the-branch-you-are-authorized-to-use>"
python -c "import hashlib;from app.db_url import resolve_database_url as r;print(hashlib.sha256(r().encode()).hexdigest()[:12])"   # compare with the approved fingerprint, then continue
alembic upgrade head
python -m uvicorn app.main:app --port 8000
Remove-Item Env:\RESEARCHTWIN_ENV_FILE    # back to SQLite
Remove-Item Env:\DATABASE_URL             # if you also set it: remove it, never assign ""
```

Assigning `$env:DATABASE_URL = ""` is **not** the same as removing it: a blank value disables the `RESEARCHTWIN_ENV_FILE` opt-in above, including its missing-file check, and silently selects `backend/researchtwin.db` (`db_url.py:86,121`).

Treat each request to a serverless/autosuspending Postgres as needing **two connections** — one pooled and one direct. With the default pool this roughly halves effective concurrency and can surface as slow 503s under load. Mitigate with a smaller `pool_size`, a managed connection pooler, or a non-suspending database; do not assume one-connection-per-request behavior.

### Fresh database setup

Set an explicit new path under the OS temporary directory (see [Quick start](#quick-start)), then start the backend. For PostgreSQL, run `alembic upgrade head` against the new database instead — `create_all()` will not build it.

## Data model

SQLAlchemy models live in `backend/app/models.py`: **43 tables**. SQLite foreign-key enforcement is enabled.

| Area | Tables |
|---|---|
| Identity and access | `users`, `auth_sessions`, `audit_events`, `search_history`, `rate_limit_counters`, `groups`, `group_memberships` |
| Directory and verification | `researchers`, `researcher_verifications`, `faculty_researcher_links` |
| Profiles | `student_profiles`, `faculty_profiles` |
| Collaboration | `collaboration_requests`, `collaboration_workspaces`, `workspace_members`, `workspace_tasks`, `workspace_comments`, `workspace_milestones`, `research_teams`, `research_team_members`, `research_team_invitations` |
| Roadmaps | `roadmap_progress` |
| Opportunities | `opportunities`, `opportunity_applications` |
| Research outputs | `literature_entries`, `research_proposals`, `proposal_sections`, `proposal_collaborators`, `proposal_versions`, `proposal_citations`, `thesis_records`, `thesis_milestones`, `thesis_progress_events`, `publication_submissions`, `publication_revisions`, `publication_status_events` |
| Intelligence | `research_cluster_runs`, `research_cluster_assignments` |
| Institutions | `institutions`, `institution_memberships`, `research_labs`, `research_lab_members`, `interuniversity_collaborations` |

Notable integrity rules established by the schema:

- `users.email` is unique. `auth_sessions.token_hash` is unique; the foreign key to `users.id` is on `auth_sessions.user_id`, not on the token hash (`models.py:107-113`).
- `student_profiles.user_id` and `faculty_profiles.user_id` are each unique — one profile row per account.
- `faculty_researcher_links` makes `faculty_user_id` and `researcher_id` individually unique with `ondelete="CASCADE"`: one faculty account owns at most one directory record, and one record has at most one owner.
- `roadmap_progress` carries `UniqueConstraint(user_id, researcher_id, skill, milestone_index)` (`uq_roadmap_progress_milestone`), which makes a milestone write an idempotent upsert instead of a duplicate row.
- `opportunities` are keyed by `(external_source, external_id)` so an importer cannot create duplicates.
- `thesis_progress_events.milestone_id` is a plain column, **not** a foreign key to `thesis_milestones`; event history therefore survives milestone deletion but is not referentially constrained.
- Ownership is enforced in queries, not inferred from client parameters: collaboration rows are always filtered by the authenticated `student_user_id`, and a faculty decision is rejected with `403` unless the request's `researcher_id` matches that faculty account's own `faculty_researcher_links` row. `roadmap_progress.skill` is stored from the **server-recomputed** roadmap, so a client cannot persist progress for a skill or milestone index that is not currently in its roadmap.

**Known trade-off:** `roadmap_progress` rows are keyed by `(skill, milestone_index)`. If a researcher's `skills` text is edited later, previously completed milestones for a removed or reordered skill become orphans that no longer render. They are inert, not incorrect, and no retention job exists for them.

## Migrations

Alembic is configured from `backend/` (`alembic.ini`, `migrations/`). The history is a **linear chain** with a single head:

```text
0001_baseline → 0002_audit_events → 0003_groups → 0004_verified_profiles
→ 0005_workspaces_and_teams → 0006_opportunities → 0007_research_intelligence
→ 0008_research_outputs → 0009_research_labs → 0010_repair_batch_2
→ 0011_drop_redundant_indexes → 0012_search_history (head)
```

`0001_baseline` matches the schema `create_all()` produced before migrations were introduced. On PostgreSQL, readiness fails closed unless `alembic_version` equals the head.

Run from `backend/` only after passing [Confirm the database target first](#confirm-the-database-target-first-mandatory). With `DATABASE_URL` **unset or blank**, every one of these commands silently targets `backend/researchtwin.db` (`migrations/env.py:31` → `db_url.py:112-121`) — including read-only ones like `alembic current` and `alembic check`, which is why a passing check is not evidence about the hosted database. Commands:

```powershell
alembic current
alembic upgrade head          # fresh database or advancing an existing one
alembic stamp 0001_baseline   # one-time mark for an existing unchanged pre-migration database
alembic check                 # confirm models and the migration head agree
```

`tests/test_migrations.py` exercises the models-vs-head comparison, a fresh upgrade, the adoption path on a stamped legacy database (data survives, audit migration applies once), a downgrade, and an incompatible upgrade.

Never point migration commands at production without an approved change: take a fresh backup, rehearse on a restored copy, review the generated revision, run one revision as a one-off step, verify constraints and data, and retain a tested restore path. Downgrades drop data and are **not** a recovery plan.

## Backups and restore

`backend/scripts/database_backup.py` creates checksummed backups with a manifest sidecar, verifies them, reports capacity and session-retention indicators, and restores only to a **new** path. It refuses to overwrite an existing file. SQLite backups use the online-backup API; PostgreSQL backups use `pg_dump`.

```bash
cd backend
python scripts/database_backup.py status   --source researchtwin-demo.db
python scripts/database_backup.py backup   --source researchtwin-demo.db --destination ../backups/snapshot.db
python scripts/database_backup.py verify   --backup ../backups/snapshot.db
python scripts/database_backup.py restore  --backup ../backups/snapshot.db --target ../restore-drill.db
```

```bash
# PostgreSQL archive — the URL is taken from the argument and never printed
DATABASE_URL='postgresql://...' python scripts/database_backup.py backup \
  --database-url "$DATABASE_URL" \
  --destination ../backups/researchtwin.dump
```

**Manifest semantics.** Every backup writes `<backup>.manifest.json` with the SHA-256 checksum and file size. SQLite manifests additionally record per-table row counts, the Alembic revision when present, and active/expired session counts. PostgreSQL manifests carry the checksum, size, database name, `format: "pg_dump-custom"`, `created_at`, a `restore_format` hint string, and `toc_verified` — which records only that the `pg_restore` **binary was located** (`scripts/database_backup.py:257`), not that a TOC listing succeeded; a failed `--list` aborts before any manifest is written (`:246-248`). Do not read `toc_verified: true` as archive-content validation. `verify` is read-only, works without a manifest, and fails on a checksum mismatch, a non-`ok` SQLite `integrity_check`, or row-count drift. `restore` requires a manifest **by default** because there is otherwise nothing to compare against.

**Legacy manifest-less backups** remain recoverable through a deliberate opt-in, after inspecting the `verify` output (which reports `"manifest": null`) and confirming the file came from a trusted location:

```bash
python scripts/database_backup.py restore --backup ../backups/legacy.db --target ../restore-drill.db --allow-manifestless
```

`--allow-manifestless` still refuses an existing target, still validates the SQLite file signature before creating the target, and still removes its own partial target if the copy or verification fails. It simply cannot compare checksums or row counts, so record the verification output in the restore log and compare row counts manually. No migration converts old backups.

**PostgreSQL restore is manual-only and unverified.** The tool's `restore` subcommand accepts SQLite and rejects PostgreSQL archives. Recovery is a reviewed manual operation:

```bash
pg_restore --no-owner --no-privileges --dbname=<new target> <file>
```

This path has **not** been drilled against a disposable PostgreSQL database in this repository. Treat it as UNVERIFIED until an approved drill completes. Never run it against production without explicit approval, a fresh backup, and a tested rollback path.

### Restore procedure

1. Stop application writes or put the service in maintenance mode.
2. Take a fresh backup of the current database before touching it.
3. Select the newest backup whose `verify` succeeds.
4. Restore to a **new** database, never over the live one.
5. Compare the restored snapshot against the manifest.
6. If the backup predates the current schema, run `alembic upgrade head` on the restored copy and re-verify.
7. Re-run the identity pre-flight against the **new** target and confirm, through the provider's project/branch mapping, that it is not the live database — a different-looking hostname is not proof. Then repoint `DATABASE_URL` only after the restored copy passes verification, or follow the provider's console restore flow.
8. Record the incident, backup used, timestamps, and verification output.

### Backup schedule and capacity

Assume **no managed backup** from a free hosting tier until the provider dashboard proves otherwise. RPO 24 hours; RTO 4 hours for a tested restore path.

| Cadence | Retention | Location |
|---|---|---|
| Daily (operator-run or scheduled task) | 14 days | Host outside the web service, access-controlled |
| Weekly | 8 weeks | Off-host, encrypted archive |
| Before any migration or schema change | Until verified, then 30 days | Off-host |
| Quarterly restore drill output | Delete after verification | Disposable local path |

Encrypt archives with an OS-provided tool and a passphrase held outside the repository — `7z a -p -mhe=on backup.7z backup.db*` on Windows, or `age -p -o backup.age backup.db*`. Never place the passphrase in a script, shell history, or a tracked file. Secrets (`DATABASE_URL`, `RATE_LIMIT_HASH_SECRET`) are configured separately and must never be inside a backup archive or committed.

Read-only capacity checks:

```sql
SELECT pg_size_pretty(pg_database_size(current_database()));
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;
SELECT count(*) FROM pg_stat_activity;
```

For SQLite, `database_backup.py status` reports file size, freelist pages, per-table row counts, active and expired sessions, and the audit-event date range. Review monthly. Treat 80% of available storage, a rising freelist, or more than 30 days of expired sessions as a cleanup signal.

### Retention rules

Proposed defaults that need institutional approval before enforcement. Deletion is always a manual, reviewed operation — there is no destructive retention job in the application. Purge only from a verified backup, and never purge audit events under a legal hold or open investigation.

| Data | Default retention |
|---|---|
| Audit events | 3 years |
| Collaboration requests and responses | 3 years after last update |
| Roadmap progress | Life of the account |
| Expired or revoked sessions | Purge candidate after 30 days |
| Rate-limit counters | Purge candidate after 7 days |
| Deactivated accounts | Review after 2 years; delete only with approval |
| Backups | Per the schedule above, then securely deleted |

### Account deletion

1. An administrator deactivates the account through `PUT /admin/users/{id}/active`, which revokes every session immediately and writes an `account.deactivate` audit event.
2. The account remains visible to administrators for audit and support.
3. A verified erasure request is a reviewed offline operation: back up, export the account first, delete or anonymize the account rows, keep audit events with the actor reference nulled, record the decision.
4. Do not hard-delete an account that owns collaboration history needed for accountability — prefer deactivation plus anonymization.
5. Legal holds and institutional retention override deletion until released.

### Personal-data export

```http
GET /admin/users/{user_id}/data-export
Authorization: Bearer <admin token>
```

The response includes account metadata, the student or faculty profile, the faculty–researcher link, the account's collaboration requests, requests in its faculty inbox, roadmap progress, session counts, and its audit events. Password hashes and session token hashes are never included. Each export writes an `account.data_export` audit event.

**This export is partial.** `api/admin.py:225-320` queries only those tables. Records created by the later feature phases — workspaces and their tasks/comments/milestones, teams and invitations, opportunity applications, literature, proposals, theses, publication submissions, lab and institution memberships, and search history — are **not** exported and are **not** covered by the deletion procedure above. For any subject-access or erasure request, enumerate those tables manually with an explicit `user_id`/membership filter; do not present the export response as a complete copy of a person's data.

## Database hosting and migration constraints

The deployed backend currently points at a free-tier managed PostgreSQL instance reported to **expire on 2026-11-21** and constrained on memory (the exact plan limits are dashboard state — not re-confirmed here). **That date is an unverified historical snapshot taken from earlier project documentation, not a re-confirmed platform fact** — it was never checked against the provider dashboard, and it must be re-confirmed there at the start of any cutover before anyone schedules work against it. The migration plan therefore requires, before cutover:

- Confirm, through [Confirm the database target first](#confirm-the-database-target-first-mandatory), the provider project, branch, and endpoint identity of **both** the restored rehearsal copy and the eventual target, and prove they are different branches. The operator's shell during a cutover normally holds the production connection string, so an unguarded "rehearsal" command can aim at production with no warning.
- A durable Postgres target that is not on an expiring plan, reachable over TLS, with a URL injectable as a secret only.
- A **final backup of the source database taken before it expires**, plus a verified restore drill on a disposable copy.
- `alembic upgrade head` applied to the **restored copy** first — re-running the pre-flight immediately beforehand — then, after approval, to the target, again with a fresh pre-flight, and only then `alembic check`. Never against an unbacked-up live database.
- Confirmation that the target is PostgreSQL whenever `RATE_LIMIT_REQUIRE_SHARED_DATABASE=true`, because shared limits refuse any other dialect.
- Reverification of `/ready` on the new target: the pinned Alembic head (`0012_search_history`), the active model artifact digest, and the ≥ 32-byte limiter secret.

Credentials and connection strings are deliberately **not** recorded here — they live in the hosting dashboard and in per-target secret files. Provider and public hostname identifiers **are** recorded in this document, because they are configuration rather than secrets. Provider project, branch, and endpoint identifiers are not: a connection string can resolve a branch identifier to a live database, so the target must be confirmed at runtime through the pre-flight above, never inferred from text in a repository file.

## HTTP conventions

- All protected routes use `Authorization: Bearer <token>`. Sessions are server-side rows; only a SHA-256 hash of the token is stored.
- Request models set `extra="forbid"` individually — 55 of the 70 models in `schemas.py`, with no shared base configuration — so an unrecognized field is normally a `422`. Of the 57 models actually used as request bodies, **exactly two omit it and silently drop unknown fields**: `ProfileRecommendationRequest` (`schemas.py:167`, used by `POST /students/me/recommendations`) and `TeamRecommendationRequest` (`schemas.py:482`, used by `POST /teams/{team_id}/recommendations`). A typo'd field on those two routes is ignored, not rejected.
- Timestamps in API payloads are **epoch seconds** (integers), not ISO strings.
- Role labels used by the [API reference](#api-reference):

| Label | Meaning |
|---|---|
| `public` | No token required or consulted. |
| `optional` | Anonymous allowed; a valid token, if present, is resolved and used. |
| `any` | Any authenticated, active account; ownership or membership checked in the handler. |
| `student` / `faculty` / `admin` | That role only, via `require_role(...)`. |
| `admin,faculty` / `faculty,student` | Any listed role. |

- Authorization comes from `backend/app/api/deps.py`: `get_current_session`, `get_current_user`, `get_optional_user`, `require_role(*roles)` with the `require_student` / `require_faculty` / `require_admin` aliases. The bearer scheme is `HTTPBearer(auto_error=False)`, so a missing token is handled explicitly.
- `/me` routes derive the owner from the authenticated account. Clients cannot choose another owner ID.

### Status-code behavior

| Situation | Response |
|---|---|
| Missing, expired, revoked, or unknown token; or the account is inactive | `401` `{"detail":"Authentication required"}` with `WWW-Authenticate: Bearer` (`api/deps.py:22-26,38-42`) |
| Optional-auth route asked for a credential-specific filter | `401` — two exceptions differ from the canonical form: `api/labs.py:67-70` repeats the detail **without** the `WWW-Authenticate` header, and `api/opportunities.py:116-120` sends a different detail (`"Sign in to filter opportunities by eligibility"`) |
| Authenticated but wrong role for the route | `403` `{"detail":"You do not have permission to perform this action"}` |
| Authenticated but not the owner/member of the target | `403` — **except** workspaces and teams, which answer `404` to non-members (see [Workspaces](#workspaces)) |
| Recommendation or roadmap requested before a profile is saved | `400` `{"detail":"Save your student profile before requesting recommendations"}` (`api/students.py:64-68`) |
| Uniqueness or state conflict (duplicate registration, duplicate collaboration, already-reviewed decision, invalid status transition) | `409` `{"detail":"Request conflicts with existing data"}` — `IntegrityError` handler at `backend/app/main.py:122-134`, plus explicit raises in `api/auth.py:141,163` and `api/collaboration.py:142,460` |
| Object does not exist, or is not visible to the caller | `404` |
| Schema violation, unknown extra field on a `forbid` model, `top_k` outside its route-specific range (1–10, 1–20, or 1–50) | `422` (no custom `RequestValidationError` handler exists) |
| Body above `MAX_REQUEST_BODY_BYTES` | `413` |
| Limit exceeded | `429` with `Retry-After` — seconds remaining in the current fixed window (`services/rate_limit.py:262-266`) |
| Model inference busy | `503` with `Retry-After` (`RecommendationBusy` handler, `backend/app/main.py:109-119`) |
| Model inference or semantic matching failed (`RecommendationError`, `SemanticMatchingError`) | `503` `{"detail":"Recommendation service unavailable"}` — per-route handlers at `api/profiles.py:178-182`, `api/students.py:87-91`, `api/teams.py:505-509`. Separately, a `RecommendationError` raised by the artifact check makes `/ready` answer `not_ready` (`backend/app/main.py:210-219`) |
| Limiter configuration missing or invalid | `503` `{"detail":"Request protection is not configured"}` |
| Database error during a request | `503` `{"detail":"Database unavailable"}` from the `SQLAlchemyError` handler (`backend/app/main.py:137-148`); **two paths raise `500` instead**: `api/auth.py:166-171` and `api/researchers.py:308` |
| `/health` with an unreachable database | `503` `{"status":"unhealthy"}` |
| `/ready` failing any gate | `503` `{"status":"not_ready", …}`; success is `{"status":"ready", …}` (`backend/app/main.py:187-231`) |

## API reference

**148 router operations** — 62 GET, 41 POST, 24 PUT, 21 DELETE. Four further route operations are declared directly in `backend/app/main.py` and are **outside** this count: `GET /` (liveness banner), `GET /health`, `GET /ready`, and `GET /readiness`. FastAPI also serves `/openapi.json`, `/docs`, `/redoc`, and `/docs/oauth2-redirect`. `/openapi.json` is the authoritative schema and the authoritative live route list — prefer it over this section for anything field-level, and treat this table as a map rather than a contract.

Access distribution: `any` 69, `admin` 29, `student` 16, `faculty` 14, `public` 8, `admin,faculty` 6, `optional` 5, `faculty,student` 1.

### Request and response schemas

This reference deliberately does **not** reproduce field-level bounds for all 148 operations — `GET /openapi.json` emits them from `backend/app/schemas.py`, and a hand-copied table drifts. Load `/openapi.json` (or `/docs`) for types, enums, and every `maximum`/`maxLength`. The rows below cover only what callers most often get wrong and what changes request *shape* rather than validity:

| Route family | Constraint | Source |
|---|---|---|
| Directory list | `offset` ≥ 0, `limit` ≤ 500; filters `search`, `department`, `research_area`, `skill` | `api/researchers.py:81-86` |
| Recommendations | `top_k` 1–10; computed from the **saved** profile only | `schemas.py:168`, `api/students.py:37,64-68` |
| Opportunity matches / trend summary | `top_k` 1–20 / 1–50 | `schemas.py:613`, `api/research_intelligence.py:122` |
| Roadmap progress | `milestone_index` 0–20 | `schemas.py:173` |
| Research network / knowledge graph | `min_similarity` (default 0.1), `max_edges`, `include_isolated`, `researcher_limit` | `api/research_intelligence.py:36-39,131-132` |
| Expertise gaps | `limit` ≤ 100, `verified_only` | `api/roadmap.py:95-96` |
| Verification queues | `limit` ≤ 200 | `api/verification.py:80-81,199-200` |
| Labs | `q`, `institution_id`, `mine` | `api/labs.py:59-63` |
| List responses | **Two shapes, and no common `items` key.** Paginated routes return `{total, offset, limit, <resource key>}` where the array key is named per resource (`opportunities`, `applications`, `requests`, `researchers`, `verifications`, `labs`, `members`, `theses`, `proposals`, `versions`, `entries`, `events`). Bare arrays are returned by `GET /researchers/` and `GET /researchers/intelligence` (`api/researchers.py:79,120,127-133`), `GET /search-history` (`api/search_history.py:18-30`), and the admin lists `GET /admin/users`, `/admin/groups`, `/admin/groups/{id}/members`, `/admin/audit-events` (`api/admin.py:78,404,427,541`). `GET /workspaces/me` (`api/workspaces.py:215`) and `GET /teams/me` (`api/teams.py:224`) return a keyed object with **no** `total`. Read each route's response in `/openapi.json` instead of assuming a shape | `api/researchers.py:79`, `api/admin.py:78`, `api/workspaces.py:215`, `api/teams.py:224` |
| Timestamps | epoch-second integers; no `date-time` field appears anywhere in the schema | `schemas.py:123,220,291` |

Field length limits (titles, bodies, DOI, notes, tag lists, expiry windows) are enforced by Pydantic and are visible per model in `/openapi.json`; they are not duplicated here by design.

### Authentication

| Method | Path | Access |
|---|---|---|
| POST | `/auth/register` | public |
| POST | `/auth/login` | public |
| POST | `/auth/logout` | any |
| GET | `/auth/me` | any |

### Student and faculty profiles, recommendations, roadmaps

| Method | Path | Access |
|---|---|---|
| GET | `/students/me/profile` | student |
| PUT | `/students/me/profile` | student |
| POST | `/students/me/recommendations` | student |
| GET | `/students/me/expertise-gaps` | student |
| GET | `/students/me/researchers/{researcher_id}/roadmap` | student |
| PUT | `/students/me/researchers/{researcher_id}/roadmap/progress` | student |
| GET | `/faculty/me/profile` | faculty |
| PUT | `/faculty/me/profile` | faculty |
| GET | `/faculty/me/researcher-link` | faculty |
| PUT | `/faculty/me/researcher-link` | faculty |
| GET | `/faculty/me/researcher-link/verification` | faculty |
| POST | `/faculty/me/researcher-link/verification` | faculty |

`top_k` on the recommendation route is bounded 1–10; other routes that take a `top_k` use different ranges (see [Request and response schemas](#request-and-response-schemas)). Recommendations are computed from the **saved** profile of the authenticated account; a client-supplied profile is ignored on these routes, and a request before any profile is saved is a `400`, not an empty list. Roadmap progress is written back against the server-recomputed roadmap.

### Compatibility recommendation routes (deprecated)

| Method | Path | Access |
|---|---|---|
| POST | `/recommendations/researchers` | student |
| POST | `/recommendations/roadmap/researcher` | student |

Both still require student authentication and use the saved profile. Prefer `/students/me/recommendations` and the roadmap routes.

### Researcher directory

| Method | Path | Access |
|---|---|---|
| GET | `/researchers/` | public |
| GET | `/researchers/{researcher_id}` | public |
| GET | `/researchers/intelligence` | public |
| GET | `/researchers/verification-summary` | public |
| GET | `/researchers/{researcher_id}/verification` | public |
| POST | `/researchers/` | admin |
| PUT | `/researchers/{researcher_id}` | admin |
| DELETE | `/researchers/{researcher_id}` | admin |
| POST | `/researchers/import` | admin |

List requests support `offset` and `limit` (maximum 500) plus search filters. Reads are public; every write, including the CSV import, is administrator-only.

### Researcher verification

| Method | Path | Access |
|---|---|---|
| GET | `/admin/verifications` | admin |
| PUT | `/admin/verifications/{verification_id}` | admin |
| GET | `/admin/researchers/{researcher_id}/verifications` | admin |

Faculty-submitted verification evidence is recorded through `POST /faculty/me/researcher-link/verification` and decided here.

### Collaboration requests

| Method | Path | Access |
|---|---|---|
| POST | `/students/me/collaboration-requests` | student |
| GET | `/students/me/collaboration-requests` | student |
| GET | `/faculty/me/collaboration-requests` | faculty |
| PUT | `/faculty/me/collaboration-requests/{request_id}/decision` | faculty |

Faculty inbox access depends on the administrator-verified faculty/researcher link, and the missing-link case is **not** uniform: the inbox list and the decision route answer `400` with the `NO_LINK` text (`api/collaboration.py:363`, `:429`), while `PUT /faculty/me/researcher-link` answers `403` with the same string (`:328`). A decision attempted on a request belonging to a *different* researcher receives `403` (`:438-439`), and a request ID that is not visible at all is `404` (`:434`). Only a `pending` request is decidable — the guard is a conditional update, so a second decision is a `409` (`:444-460`).

### Workspaces

| Method | Path | Access |
|---|---|---|
| GET | `/workspaces/me` | any |
| GET | `/workspaces/{workspace_id}` | any |
| GET / POST | `/workspaces/{workspace_id}/tasks` | any |
| PUT / DELETE | `/workspaces/{workspace_id}/tasks/{task_id}` | any |
| GET / POST | `/workspaces/{workspace_id}/milestones` | any |
| PUT / DELETE | `/workspaces/{workspace_id}/milestones/{milestone_id}` | any |
| GET / POST | `/workspaces/{workspace_id}/comments` | any |
| DELETE | `/workspaces/{workspace_id}/comments/{comment_id}` | any |

"any" means any authenticated account; membership is enforced inside each handler. Workspaces and teams deliberately answer **`404` "Workspace not found" / "Team not found"** to a non-member, because non-membership is made indistinguishable from a missing object — the API will not confirm that an ID exists (`services/workspaces.py:72,78-84`, `services/teams.py:14,26`). Where the object *is* visible but the specific action is not permitted, `403` is still used (`api/workspaces.py:332`).

### Teams

| Method | Path | Access |
|---|---|---|
| POST | `/teams` | faculty,student |
| GET | `/teams/me` | any |
| GET / DELETE | `/teams/{team_id}` | any |
| POST | `/teams/{team_id}/invitations` | any |
| PUT | `/teams/{team_id}/invitations/{invitation_id}` | any |
| DELETE | `/teams/{team_id}/members/{user_id}` | any |
| POST | `/teams/{team_id}/recommendations` | any |

### Opportunities and funding

| Method | Path | Access |
|---|---|---|
| GET | `/opportunities` | optional |
| GET | `/opportunities/{opportunity_id}` | optional |
| POST | `/opportunities` | admin,faculty |
| PUT | `/opportunities/{opportunity_id}` | admin,faculty |
| DELETE | `/opportunities/{opportunity_id}` | admin,faculty |
| GET | `/opportunities/mine` | admin,faculty |
| GET | `/opportunities/{opportunity_id}/applications` | admin,faculty |
| PUT | `/opportunities/{opportunity_id}/applications/{application_id}` | admin,faculty |
| POST | `/opportunities/{opportunity_id}/applications` | student |
| DELETE | `/opportunities/{opportunity_id}/applications/me` | student |
| GET | `/opportunities/{opportunity_id}/eligibility` | student |
| GET | `/students/me/opportunity-applications` | student |
| POST | `/students/me/opportunity-matches` | student |
| POST | `/admin/opportunities/import` | admin |
| GET | `/admin/opportunities/sources` | admin |

Applying is limited per account — see [Rate and size limits](#rate-and-size-limits).

### Literature

| Method | Path | Access |
|---|---|---|
| GET / POST | `/literature` | any |
| GET / PUT / DELETE | `/literature/{entry_id}` | any |

### Proposals

| Method | Path | Access |
|---|---|---|
| GET / POST | `/proposals` | any |
| GET / PUT / DELETE | `/proposals/{proposal_id}` | any |
| POST | `/proposals/{proposal_id}/sections` | any |
| PUT / DELETE | `/proposals/{proposal_id}/sections/{section_id}` | any |
| POST | `/proposals/{proposal_id}/collaborators` | any |
| DELETE | `/proposals/{proposal_id}/collaborators/{user_id}` | any |
| POST | `/proposals/{proposal_id}/citations` | any |
| DELETE | `/proposals/{proposal_id}/citations/{citation_id}` | any |
| GET | `/proposals/{proposal_id}/versions` | any |
| GET | `/proposals/{proposal_id}/versions/{version}` | any |

### Theses

| Method | Path | Access |
|---|---|---|
| GET | `/theses` | any |
| POST | `/theses` | student |
| GET / PUT / DELETE | `/theses/{thesis_id}` | any |
| GET | `/theses/{thesis_id}/history` | any |
| POST | `/theses/{thesis_id}/milestones` | any |
| PUT / DELETE | `/theses/{thesis_id}/milestones/{milestone_id}` | any |

Supervisor-side actions are authorization-checked per relationship; creation is student-restricted. Thesis status follows a fixed machine (`services/research_outputs.py:25-32`): `proposed → {in_progress, withdrawn}`, `in_progress → {submitted, withdrawn}`, `submitted → {defended, in_progress, withdrawn}`, `defended → {completed, in_progress}`, with `completed` and `withdrawn` terminal.

### Publication submissions

| Method | Path | Access |
|---|---|---|
| GET / POST | `/publication-submissions` | any |
| GET / PUT / DELETE | `/publication-submissions/{submission_id}` | any |
| POST | `/publication-submissions/{submission_id}/revisions` | any |
| POST | `/publication-submissions/{submission_id}/status` | any |

Publication status follows a fixed machine and every accepted transition appends to `publication_status_events`; an out-of-order transition is rejected and nothing is recorded (`services/research_outputs.py:34-43`): `draft → {submitted, withdrawn}`, `submitted → {under_review, rejected, withdrawn}`, `under_review → {revision_requested, accepted, rejected, withdrawn}`, `revision_requested → {submitted, withdrawn}`, `accepted → {published, withdrawn}`, with `rejected`, `published`, and `withdrawn` terminal. A revision may be attached only in `submitted`, `under_review`, `revision_requested`, or `accepted` (`PUBLICATION_REVISION_STATUSES`, `:45-50`).

### Research intelligence

| Method | Path | Access |
|---|---|---|
| GET | `/research-intelligence/clusters` | any |
| POST | `/research-intelligence/clusters/rebuild` | admin |
| GET | `/research-intelligence/trends` | any |
| GET | `/research-intelligence/network` | any |
| GET | `/research-intelligence/knowledge-graph` | any |
| POST | `/research-intelligence/topics/predict` | any |

Rebuilds are administratively gated, take a process-local lock, and are bounded: a semantic rebuild over 2000 researchers is rejected.

### Analytics

| Method | Path | Access |
|---|---|---|
| GET | `/analytics/departments` | any |
| GET | `/analytics/university` | any |

### Institutions, labs, and inter-university collaboration

| Method | Path | Access |
|---|---|---|
| GET | `/institutions` | public |
| GET | `/institutions/me` | any |
| GET | `/labs` | optional |
| POST | `/labs` | faculty |
| GET | `/labs/{lab_id}` | optional |
| PUT | `/labs/{lab_id}` | faculty |
| DELETE | `/labs/{lab_id}` | faculty |
| GET | `/labs/{lab_id}/members` | optional |
| POST | `/labs/{lab_id}/members` | faculty |
| DELETE | `/labs/{lab_id}/members/{user_id}` | any |
| GET | `/interuniversity-collaborations` | any |
| POST | `/interuniversity-collaborations` | faculty |
| GET | `/interuniversity-collaborations/{collaboration_id}` | any |
| POST | `/interuniversity-collaborations/{collaboration_id}/status` | faculty |
| GET | `/admin/institutions` | admin |
| POST | `/admin/institutions` | admin |
| PUT | `/admin/institutions/{institution_id}` | admin |
| GET | `/admin/institutions/{institution_id}/members` | admin |
| PUT | `/admin/institutions/{institution_id}/members/{user_id}` | admin |
| DELETE | `/admin/institutions/{institution_id}/members/{user_id}` | admin |

Directory and lab listings are public/optional by design so a student can discover a lab; membership writes, lab mutation, and institution administration are role-restricted.

### Groups

| Method | Path | Access |
|---|---|---|
| GET | `/admin/groups` | admin |
| GET | `/admin/groups/{group_id}/members` | admin |
| POST | `/admin/groups/{group_id}/members` | admin |
| DELETE | `/admin/groups/{group_id}/members/{user_id}` | admin |

### Search history

| Method | Path | Access |
|---|---|---|
| GET | `/search-history` | any |
| POST | `/search-history` | any |

Rows are keyed to the authenticated account; one client cannot read or write another's history. Retention is bounded at **20 entries per user** (`MAX_ENTRIES_PER_USER`, `api/search_history.py:15`), older rows are trimmed on write (`:61`), `GET` defaults to `limit` 10 and caps at 50 (`:20`), and **consecutive duplicates are suppressed** so typing the same query twice stores one row. `GET /search-history` returns a **bare array** — one of the list routes that skip the `{total, …}` envelope, alongside `GET /researchers/`, `GET /researchers/intelligence`, and the admin lists (see the List responses row in [Request and response schemas](#request-and-response-schemas)); it is not the only one.

### Administration

| Method | Path | Access |
|---|---|---|
| GET | `/admin/users` | admin |
| PUT | `/admin/users/{user_id}/active` | admin |
| PUT | `/admin/users/{user_id}/role` | admin |
| POST | `/admin/users/{user_id}/sessions/revoke` | admin |
| POST | `/admin/users/{user_id}/password-reset` | admin |
| GET | `/admin/users/{user_id}/data-export` | admin |
| PUT | `/admin/faculty/{faculty_user_id}/researcher-link` | admin |
| DELETE | `/admin/faculty/{faculty_user_id}/researcher-link` | admin |
| GET | `/admin/audit-events` | admin |

Self status and self role changes are rejected; sensitive operations revoke sessions. Faculty-link assignment and removal are audited.

## Rate and size limits

| Scope | Default | Key |
|---|---|---|
| Registration | 5 per 3600 s | IP + normalized email |
| Login (**failed attempts only**) | 10 per 900 s | IP + normalized email; a successful login neither consults nor increments the bucket |
| Recommendations | 8 per 300 s | IP + account |
| Research-intelligence network/graph | 6 per 60 s | IP + account |
| Opportunity applications | 20 per 3600 s | IP + account |
| Team recommendations | reuses the recommendation limit (8/300 by default) | account |
| Collaboration request creation | reuses the recommendation limit (8/300 by default) | account |
| Opportunity matches | reuses the recommendation limit (8/300 by default) | account |
| Topic prediction | reuses the recommendation limit (8/300 by default) | account |
| Researcher verification submission | 5 per 3600 s — **hardcoded** `VERIFICATION_MAX`/`VERIFICATION_WINDOW_SECONDS`, no environment override | account |
| Request body | 65 536 bytes | — |
| Model inference concurrency | 2 per process | `BoundedSemaphore` |
| Directory list page | max `limit` 500 | — |
| `top_k` | recommendations 1–10; opportunity matches 1–20; trends 1–50 | — |
| Semantic cluster rebuild | max 2000 researchers (source constant) | — |

Call sites: `api/teams.py:490-496`, `api/collaboration.py:112-118`, `api/opportunities.py:401-407,454-460`, `api/research_intelligence.py:43-48,101-107`, `api/verification.py:168-174`.

Counters live in `rate_limit_counters` and use atomic dialect-specific upserts. **Shared enforcement across workers or instances exists only when every instance uses the same PostgreSQL database**; SQLite counters are per-file, and local tests do not prove global production behavior. Identity (IP and email) is stored only as an HMAC digest using `RATE_LIMIT_HASH_SECRET`.

On login, the **password comparison runs first**; the failure limiter is consulted only on the failure branches and it raises before the audit write (`api/auth.py:192-194,201-203`). Two consequences: every attempt pays the full 600k-iteration PBKDF2 cost, because throttling does not short-circuit credential verification, and a throttled attempt produces **no** audit row, because the limiter raises before `_record_login_failure`. The audit trail is therefore not a substitute for limiter monitoring — use the counter rows for attempt volume.

## Features

Researcher recommendations combine textual, semantic, research-area, expertise, skill, project, and publication signals. The active model expects seven features in a fixed order and returns ranked scores with explanations.

Student profiles drive personalized recommendations and skill-gap roadmaps; saved progress is scoped to the student's account and researcher. Faculty collaboration inbox access depends on the administrator-verified faculty/researcher link.

Administrator accounts get an account-management console after sign-in: role and status filters, activation/deactivation, role changes, session revocation, password reset, faculty/researcher link assignment, verification decisions, per-account data export, and a filterable audit log. Every operation is enforced again by the API; the console is only a client of the administrator-only endpoints.

Session and race guards in the frontend prevent stale responses from replacing newer state. Role-aware UI controls are an aid only — the server re-checks everything.

### Grant-feed import

`POST /admin/opportunities/import` pulls external funding listings for administrators. The external fetch is **disabled by default** and requires `FUNDING_GRANTS_GOV_ENABLED`; the service stores no credentials, and imported rows are deduplicated by `(external_source, external_id)` so repeated imports update rather than duplicate. `GET /admin/opportunities/sources` reports the configured sources.

## Security

**Passwords.** PBKDF2-HMAC-SHA256 with 600,000 iterations and a per-user random salt. No plaintext storage in the authentication path; password input is not logged by the API.

**Sessions.** Tokens are 32 random bytes encoded for transport; only SHA-256 digests are stored. Expiry is checked on every authenticated request; logout writes `revoked_at`. Default TTL 12 hours, overridable by `AUTH_SESSION_TTL_SECONDS`.

**Authorization.** Server-side role and ownership checks; `/me` routes derive the owner from the token, never from a client-supplied ID. Researcher writes/import, faculty-link assignment, verification decisions, and account lifecycle operations require admin or the documented role. Public registration cannot create an administrator.

**Input validation.** Per-model `extra="forbid"` on 55 of the 70 models in `schemas.py` (the two recommendation-request bodies are the only request models without it — see [HTTP conventions](#http-conventions)) plus the configurable body cap middleware. CSV import reads only the fixed bundled path, never an uploaded file. Directory queries use SQLAlchemy ORM/parameters; no dynamic SQL from user input.

**Schema exposure.** `/openapi.json`, `/docs`, and `/redoc` are served **unauthenticated** (`backend/app/main.py:62` and FastAPI defaults). Route names, field bounds, enums, and validation limits are therefore public even though data routes are not. Never put internal-only route names or credential-shaped example values into schemas; disable the docs deliberately if that surface matters.

**CORS.** Allowlist from `FRONTEND_ORIGINS` plus two fixed localhost origins, with `allow_credentials=False`. Production origins must be exact; the localhost entries are always present in source.

**Browser headers.** CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and HSTS are configured in `frontend/_headers` — a Netlify publish-directory file, **not** `netlify.toml`. `tests/frontend/headers.test.cjs` parses it and fails if any external asset referenced by `frontend/index.html` or `frontend/researchtwin.html` is not allowed by the matching CSP directive (the test reads those two files from `frontend/`, not the repository root). That is repository configuration proven by static tests, not proof of what the deployed site returns.

**Audit trail.** `audit_events` is append-only and written in the same transaction as the change it describes.

| Event | When | Target | Detail |
|---|---|---|---|
| `auth.login_succeeded` | Credentials verified and account active | `user` / user ID | none |
| `auth.login_failed` | Unknown email, wrong password, or inactive account | `user` / user ID, or `login_identity` / null | `{"reason": "unknown_account" \| "invalid_password" \| "inactive_account"}` |
| `auth.logout` | Authenticated logout | `auth_session` / session ID | none |
| `account.sessions_revoked`, `account.deactivate`, `account.role_change`, `account.password_reset`, `account.data_export` | Administrator lifecycle operations | affected account / resource | action-specific |

The table above covers the authentication and account-lifecycle subset only. The application records **32 distinct audit actions**, including `account.reactivate`, `collaboration.decision`, `researcher.delete`, `opportunity.*`, `team.*`, `group.member_added`/`group.member_removed`, `faculty_link.*`, `lab.delete`, and `research_intelligence.clusters_rebuilt`. `SELECT DISTINCT action FROM audit_events` against a real database is the current list; do not treat this table as exhaustive when writing monitoring or retention rules.

Events never contain passwords, password hashes, bearer or session tokens, authorization headers, or raw request bodies. Unknown login emails are **not** stored at all — a plain hash of an email is dictionary-reversible, and the limiter already keeps an HMAC'd bucket for abuse control. Known failures reference the stable internal user ID.

A successful login writes the session and its audit row in one commit; if that commit fails, the API returns the database `503` and no session is persisted. On logout, the revoke and the audit row commit together, so a failed audit write cannot leave an unrevoked-but-reported-logged-out session. A failed-login audit write is caught, the event is skipped, and the login still returns the same `401` — audit failure never turns a rejected login into a success. Unknown-email attempts are compared against a fixed **dummy** hash to equalize timing (`api/auth.py:43-46,192`); known-email failures compare the **stored** hash (`:201`). Both branches then return the identical `401` body and headers (`:195-199` vs `:204-208`), so authentication does not leak account existence — but the two paths are not the same comparison, and the limiter is reached only after it (see [Rate and size limits](#rate-and-size-limits)).

Failure rows are deduplicated: at most one per known user per login window, and at most one for all unknown identities per window. An attacker rotating source addresses cannot grow the table unboundedly — but the row count is consequently **not** a raw attempt count; use limiter counters for attempt volume.

### Cookie migration prerequisites

Keep the bearer-token flow until a complete change is tested. A migration needs `HttpOnly`, `Secure`, and an appropriate `SameSite`; anti-CSRF token/origin validation for state-changing requests; explicit credentialed CORS origins; browser `credentials` handling; logout/expiry parity; and coordinated frontend/backend end-to-end coverage. No such migration has been performed.

## Residual risks

These are open, evidence-backed risks — not completed work.

1. **The bearer token is readable by same-origin JavaScript.** It lives in `sessionStorage`, so it does not survive a browser restart, but a successful XSS flaw can exfiltrate the active session. This is **not** mitigated in any way you should rely on: the CSP at `frontend/_headers:7` sets `script-src 'self' 'unsafe-inline'`, so an injected inline `<script>` still executes. CSP only narrows where running script can send data (`connect-src` is `'self'` plus the three API origins, `form-action 'self'`, `object-src 'none'`); it does not stop execution, DOM reading, or token theft by script that exfiltrates through a channel CSP permits. Treating stored content as XSS-safe requires removing `'unsafe-inline'` from `script-src` — an approved change, with the inline scripts it currently allows moved to files first.
2. **Production client-IP attribution is UNVERIFIED.** With trust disabled the limiter uses the TCP peer address. The real ingress peer, whether it terminates the connection, and whether it overwrites or strips `CF-Connecting-IP` have not been observed. **The declared start command is part of the gap:** `render.yaml:7` is `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`, with **no `--proxy-headers`** and no `--forwarded-allow-ips`, so Uvicorn never rewrites `request.client.host` from `X-Forwarded-For` and every request is attributed to the platform's proxy peer. If that is indeed one shared peer while trust is off, all clients collapse into a **single** rate-limit bucket and legitimate users throttle each other. Resolving this requires live evidence, not a config guess — do not enable trust, add the proxy flags, or populate CIDRs without it. See [Render (backend)](#render-backend).
3. **Shared rate limiting requires PostgreSQL** and is only proven globally once every instance shares the database. Local tests prove the logic, not the production topology.
4. **Model artifact and label provenance.** The active bundle is a pickle-based joblib artifact — load only from a trusted, integrity-checked source, and note that readiness never digest-pins the `.joblib` itself (`services/recommendation.py:194-234`). Training labels are derived from the same profile features the model scores, so reported quality is partly circular; there is no held-out human-labeled evaluation. Neither Torch nor sentence-transformers is a dependency at all — embeddings run on ONNX Runtime specifically to fit the hosting memory ceiling (`constraints.txt:9-12`) — so the residual risk is the **un-pinned transitive graph** of the ONNX/tokenizers/shap stack, not a Torch footprint.
5. **Roadmap retention gap.** Orphaned `roadmap_progress` rows after a researcher's skills are edited remain in the table and are never pruned.
6. **Production behavior remains unverified.** Live dashboard settings, response headers, cold-start memory, and the deployed database revision were not inspected as part of documentation work. Nothing here should be read as "production is fixed/ready".
7. **Startup fail-fast vs degraded health.** Initialization runs at import, so an unreachable database stops the process before `/health` can answer. Choose deliberately in an approved change.
8. **SQLite write contention.** These are **inherited defaults, not application settings**: `backend/app/database.py:14-16` passes only `check_same_thread` and the one PRAGMA issued per connection is `foreign_keys=ON` (`:19-22`), so nothing tunes journaling or locking. A file-backed SQLite database therefore runs with its default `journal_mode = delete`, and because no `timeout` connect argument is given, pysqlite's default 5-second busy timeout applies. A long import concurrent with traffic can still raise lock errors — surfaced as `503`, not silent loss.
9. **DSAR export is incomplete (confirmed in code).** `GET /admin/users/{id}/data-export` reads only profiles, links, collaboration, roadmap, sessions, and audit events; the later-phase tables are absent. See [Personal-data export](#personal-data-export).
10. **The open defect register lives in [Open defect register](#open-defect-register).** Four claims previously carried here as unverified hypotheses are recorded there with code-level evidence: `STB-46` (export cost is unbounded for accounts with large audit histories), `STB-64` (`verified_only` is applied *after* the row limit, so a filtered page comes back short), `STB-63` (ranking ties have no `ORDER BY` tie-break, so order can differ between SQLite and PostgreSQL) and `STB-48` + `STB-22` (a rate-limited request consumes pooled connections, so `pool_timeout` exhaustion may surface as `503` rather than `429`). "Code-level" means read from the quoted source lines, not executed.

## Open defect register

This is the project's live defect list, carried here from the pre-consolidation stabilization inventory so that one document holds it. The register was **re-checked against the current source on 2026-11-11**: the citations below are current, one High finding no longer reproduces, and the rows this pass could not re-confirm are labelled as such instead of being quietly trusted.

Read the labels literally:

- **verified 2026-11-11** — the mechanism was re-read in the current source at the cited lines. Still not executed.
- **not re-checked** — recorded 2026-11-06 against an earlier source state. The citation is by identifier because the old line numbers are no longer trustworthy.
- **code-level** — proven by reading source. **runtime** — reproduced against a local probe on a stubbed or temporary-SQLite harness, which says nothing about the deployed bundle.
- **DECISION REQUIRED** — a product or institutional choice is missing. Not a bug, and not fixable by a patch.
- **ACCEPTED RISK** — deliberate. Do not "fix" it inside an unrelated change.

**No regression test exists for any `STB-38` … `STB-70` item.** The tests proposed in the original register were plans. Nothing below may be described as fixed until its test has been observed failing and then passing. The register's baseline run was **508 passed on 2026-11-06**; the current documented run is 526 passed, which is exactly why this re-check was needed.

### Closed by later work — do not re-report

- **`STB-38` (was High): auth controls left disabled after a failed session restore no longer reproduces.** `init()` still disables `loginBtn`/`registerBtn` before calling `api.me()`, but the catch path now re-enables both before branching, on the `401` path as well as the restore-failure path (`frontend/researchtwin.html:3527-3540`, `setBusy` at `:1321-1324`; `handleUnauthorized` re-enables too at `:1642`). **No test pins this behavior**, so it is fixed by inspection only and is the first thing to re-test if the auth form ever goes dead again.

### Three open policy decisions

- **Faculty self-registration (`STB-67`, medium / institutional).** Anyone can register with the `faculty` role and immediately create labs; only the researcher-link inbox still requires an approved link, and `role` is `Literal["student", "faculty"]` so no one can self-select `admin` (`schemas.py:76-82` — verified 2026-11-11, `api/auth.py:124-167`, faculty-gated `api/labs.py`). Decide whether faculty accounts need approval before they can create a lab. This is an institutional-trust question, not a privilege-escalation bug.
- **Password policy (`STB-65`, low).** Three different bounds are in force: registration accepts 8–128 characters (`schemas.py:78`), admin reset requires 12–128 (`schemas.py:249`), and login accepts 1–128 (`schemas.py:110`) — all verified 2026-11-11. A password created at registration is rejected by the reset endpoint. Choose one validator and use it in both places.
- **Session lifecycle (`STB-66`, medium / product).** Sessions are an absolute 12 hours (`services/auth.py:62-64`) with no idle timeout, no refresh, no self-service password change and no forgot-password flow; only an administrator can reset (`api/admin.py:201-203`). Verified 2026-11-11.

### Locked and accepted decisions — do not silently reverse

- **`STB-10` (POLICY LOCKED).** Opportunity managers deliberately receive the applicant's email; the approved remedy is a pre-submission disclosure in the application UI, not a backend restriction. Backend authorization is unchanged and existing tests assert outsider/applicant `403` with manager receipt. The disclosure is **not implemented**, because no opportunities UI exists yet (`STB-33`) — deferred, not dropped.
- **`STB-16` (POLICY RECORDED).** User deletion is intentionally unsupported; deactivation is the account lifecycle, and `DELETE /admin/users/{id}` answers `404` `{"detail":"Not Found"}` today — no route declares that bare path (the admin user routes are `/users` and `/users/{id}/active`, `/role`, `/sessions/revoke`, `/password-reset`, `/data-export`, `api/admin.py:78,96,140,180,201,224`), so it is a routing miss, not a method rejection. Measured with the test client on 2026-11-11. Ownership foreign keys are `CASCADE`, so any future delete needs an ownership-transfer or `RESTRICT`/`SET NULL` migration **first** — otherwise purging an account erases its labs and workspaces.
- **`STB-17` (retention still PENDING).** Pagination shipped; bounded retention for `auth_sessions`, `audit_events`, proposal versions and publication revisions is still a decision. The [Retention rules](#retention-rules) table describes proposed policy, not implemented behavior — there is no retention job.
- **`STB-22` (VERIFIED + ACCEPTED).** A limited authenticated request holds **two** pooled connections, one for the limiter transaction, measured at +6.25 ms median locally, with a saturated pool blocking for `pool_timeout` before `503`. Keep it that way until a connection-budget review justifies a dedicated limiter pool.
- **`STB-18` (partially deferred).** Pagination pushdown landed except eligible-opportunity SQL filtering and the `latest_by_researcher` history scans, which remain deferred.
- **`STB-68` (ACCEPTED RISK).** Training labels are prototype heuristics, not outcome data, so the reported NDCG@5 ≈ 0.973 measures agreement with those labels rather than real user acceptance, and low-score calibration is weak. Keep this caveat in any release note; it cannot be fixed without a genuinely labelled dataset.
- **`STB-30`, `STB-31`, `STB-37`, `STB-32`, `STB-33`** stay open as deployment and coverage decisions: the API base URL is pinned to one production hostname and fails closed elsewhere, `FRONTEND_ORIGINS` is `sync: false` and so is not codified in the repo, `http://localhost:5500` and `http://127.0.0.1:5500` are always-permitted CORS origins (`allow_credentials=False`, so not an auth bypass), instance memory headroom has never been sampled on the platform, and the later-phase routers have no API-client methods or UI of their own. See [Residual risks](#residual-risks) item 2 and the deployment section.

### Confirmed open findings

| ID | Finding | Severity | Evidence | Basis |
|---|---|---|---|---|
| `STB-39` | The per-IP limiter bucket may collapse all clients into one: identity is always the direct socket peer while forwarding-header trust is off, so if the platform proxy is that peer the registration, login, recommendation, network and opportunity caps become global | High if the proxy peer is non-loopback | `services/rate_limit.py:86,213`; `render.yaml:7,20-21` | verified 2026-11-11 (code) / production impact UNVERIFIED |
| `STB-40` | Both login failure branches verify the password before consulting the failure limiter, so an already-throttled request still pays the full PBKDF2 cost — a cheap CPU-exhaustion lever on the single worker | Medium | `api/auth.py:192-193,201-202` | verified 2026-11-11 (was runtime) |
| `STB-41` | Admin filter changes made during an in-flight load are silently dropped, because `loadAdminUsers` and `loadAdminAudit` return the existing flight object before reading the filter controls | Medium | `frontend/researchtwin.html:3063-3064,3455-3456` | verified 2026-11-11 |
| `STB-42` | `loadAdminGroupMembers` has no sequence, epoch or in-flight guard, so a late response overwrites newer membership state — even after a session reset | Low-Medium | `frontend/researchtwin.html:3373-3380` | verified 2026-11-11 |
| `STB-43` | A non-array groups payload is coerced to `[]` (`Array.isArray(groups) ? groups : []`) instead of raising a protocol error, so a contract violation renders as an empty success | Low | `frontend/researchtwin.html:3348` | verified 2026-11-11 |
| `STB-44` | A failed directory load clears the rendered list and shows an error, but leaves `state.directory` populated, so the next search re-renders stale records | Low | `frontend/researchtwin.html:2291-2298` | verified 2026-11-11 |
| `STB-45` | `Retry-After` is never parsed, so no `429` or `503` message can tell the user when to retry | Low | no `Retry-After`/`retryAfter` reference exists anywhere in `frontend/api-client.js` or `frontend/researchtwin.html` | verified 2026-11-11 |
| `STB-46` | `GET /admin/users/{id}/data-export` is unbounded — every session and every audit event via `.all()`, with no cap or paging; the original run measured 5.65 s and 5.53 MB at 20,001 events on local SQLite | Medium | `api/admin.py:298-309` | verified 2026-11-11 (code); volumes are 2026-11-06 local figures |
| `STB-47` | The DSAR export omits later-phase records: literature, proposals/versions/sections/citations, theses and milestones, publication submissions and revisions, teams, workspaces and opportunity applications | Medium | see [Personal-data export](#personal-data-export) | confirmed in code during this work |
| `STB-48` | The engine is created with SQLAlchemy pool defaults — no explicit `pool_timeout` — so the pool wait exceeds the browser's default 15 s timeout, and there is no server-side request deadline: a browser abort can still complete server-side, and a timed-out registration leaves the account created so the retry returns `409` | Low-Medium | `database.py:16`; `frontend/api-client.js:5-7` | verified 2026-11-11 |
| `STB-49` | One global `adminBusy` flag makes eight separate admin mutations return early with no message, so actions — especially role changes, where the select keeps the new value — are lost silently | Medium-Low | `frontend/researchtwin.html:3121,3141,3159,3179,3256,3270,3397,3412` | verified 2026-11-11 |
| `STB-50` | Group-member candidates are drawn from `state.adminUsers`, which reflects the current role/active filters and the 200-row cap, so managing a faculty group while the list is filtered shows an empty or partial candidate set | Low-Medium | `frontend/researchtwin.html:3290` | verified 2026-11-11 |
| `STB-51` | Login is the only auth call that passes a timeout (`timeoutMs: LOGIN_TIMEOUT_MS`), so registration runs on the 15 s default while login gets 45 s — a slow registration shows a false failure and then a `409` on retry | Medium-Low | `frontend/api-client.js:5-7,252` | verified 2026-11-11 |
| `STB-52` | `resetAppState` clears the skill filter's value but not its options, so a new session inherits the previous directory's skill list | Low | `frontend/researchtwin.html:1464-1465` | verified 2026-11-11 |
| `STB-53` | Proposal and thesis list summaries are N+1: `proposal_summary` calls `latest_proposal_version` per row alongside its aggregates | Medium | `services/research_outputs.py:154,288,314,380` | verified 2026-11-11 (code) |
| `STB-54` | Opportunity matching scores every open opportunity and fits a fresh TF-IDF vectorizer per candidate inside `_signals`, so cost grows with the whole open catalogue per request | Medium | `services/opportunities.py:203,241,281` | verified 2026-11-11 (code) |
| `STB-55` | Collaboration paging orders by `created_at` alone — integer seconds, no `id` tie-break — so rows sharing a second can duplicate or disappear across pages | Low-Medium | `api/collaboration.py:183` (same pattern in the inbox query near `:373`) | verified 2026-11-11 (code); PG-unverified |
| `STB-56` | `GET /admin/verifications?status=unverified` always returns an empty page: `unverified` is a derived state implemented as an anti-join only in the public summary path | Low | `api/verification.py:28,102` versus the admin list at `:204-207` | verified 2026-11-11 (code) |
| `STB-57` | The snapshot signature hashes only id, department and `TEXT_FIELDS` (research areas, expertise, skills, projects, publications), so editing name, designation or experience leaves stale cached graph and cluster labels | Low-Medium | `services/research_intelligence.py:39,136` | verified 2026-11-11 (code) |
| `STB-58` | Unavailable semantic similarity enters the model as a real `0.0`; `semantic_available` is copied into the output and never consulted for ranking, so empty profiles are silently mis-ranked | Medium | `services/semantic_matching.py:264`; `services/recommendation.py:697-698,836-837` | verified 2026-11-11 (code) |
| `STB-59` | Embedding work is serialized: the researcher embedding lock is held across `model.encode`, so a second request waits for the entire encode rather than for cache access | Low-Medium | `services/semantic_matching.py`, `_researcher_embedding_cache_lock` (`:31,271,301`) | lock exists (verified); encode-inside-lock **not re-checked** |
| `STB-60` | Blank-profile researchers get zero vectors and are not excluded, so `AgglomerativeClustering` assigns them arbitrarily | Low | `services/research_intelligence.py:440` | verified 2026-11-11 (code) |
| `STB-61` | `model.predict_proba` and the SHAP-input `scaler.transform` may sit outside the `RecommendationError` handling, so a shape, NaN or value fault could escape as a bare `500` instead of a controlled `503`/`422` | Low | `services/recommendation.py:721-731,763-769` | **not re-checked** — try-block scope unconfirmed; original trigger was UNVERIFIED |
| `STB-62` | The joblib bundle is not content-pinned: feature order and pipeline steps are validated and `training_data_sha256` is reported but never enforced, so a replaced or edited `.joblib` loads silently. The ONNX and tokenizer files *are* digest-pinned | Low | [Readiness gate](#readiness) `services/recommendation.py:194-234` vs `services/semantic_matching.py:63-85` | confirmed during this work |
| `STB-63` | Recommendation ordering is not deterministic: candidates sort by `model_score` alone and the researcher query has no `ORDER BY`, so ties — common with sparse profiles — inherit an undefined database order that can differ between SQLite and PostgreSQL | Low | `services/recommendation.py:633-638,738-742` | verified 2026-11-11 (code); PG-unverified |
| `STB-64` | `verified_only` is applied *after* `researcher_limit` (`order_by(Researcher.id).limit(...).all()`), so a verified-only knowledge graph can be under-filled and `status_counts` describes only the first page | Low-Medium | `services/research_intelligence.py:810-823` | verified 2026-11-11 (code); PG-unverified |
| `STB-69` | Registration maps every `IntegrityError` to `409 Email already registered`, so a group or session unique conflict is reported as a duplicate email and a server-side data problem is hidden | Low | `api/auth.py:160-165` | verified 2026-11-11 (code) |
| `STB-70` | Artifact hashing keys its digest cache on `(path, st_size, st_mtime_ns)`, so rewriting an artifact and restoring both bypasses the ONNX digest check — requires local write access, which already implies code tampering | Low | `services/semantic_matching.py:58` | verified 2026-11-11 (ACCEPTED RISK) |

### Verification gaps that still apply

1. **PostgreSQL is only partly verified.** Migrations to head and the rate-limit connection, isolation, concurrency and pool-exhaustion paths ran on a real local PostgreSQL container, and the rehearsal branch served live read-only requests. Still code-reviewed rather than executed on PostgreSQL: the `FOR UPDATE`/compare-and-set paths, the partial unique indexes added by `0010`, and migration DDL parity beyond "upgrade head completes". SQLite is **not** accepted as proof for those.
2. **The frontend evidence is a local stub.** The `STB-41` … `STB-52` probes ran against a local static frontend with a stubbed or local API. They prove state-machine and race behavior, not the deployed bundle.
3. **Performance numbers are local, synthetic and single-process.** The `STB-20`/`STB-21`/`STB-35`/`STB-36` baselines used in-memory or synthetic profiles on Windows with the real ONNX embedder; `STB-21` measured only the isolated semantic stage after the cache change, never the full endpoint. They support relative comparison and regression detection — they are not hosted Linux RSS, not PostgreSQL, and not real profile text.
4. **Memory measurements are platform-separated and never hosted.** The import/ONNX figures are Windows working-set measurements from scratch scripts outside the repository, and the WSL figures are quoted from earlier runs. Neither is the hosting platform's memory, and no provider dashboard property was read. Do not present either as proof of hosted behavior.
5. **`STB-39` hinges on an unobserved fact** — whether the platform's edge proxy is the limiter's socket peer. Settle it with a read-only deployment probe or provider documentation; never by enabling header trust or adding proxy CIDRs on a guess.
6. **`STB-46`/`STB-53`/`STB-55`/`STB-63`/`STB-64` are reasoned or measured on temporary SQLite only.** Portable SQL is not the same as verified PostgreSQL behavior.
7. **`STB-32` remains blocked.** With `--workers 1` and `RECOMMENDATION_MAX_CONCURRENCY=2`, instance memory headroom has never been sampled on the hosting platform, so that concurrency choice is unvalidated rather than proven adequate.
8. **No clean-checkout artifact rebuild was performed.** Model artifacts were hashed before and after the measured runs and matched; that is not the same as a reproducible build from a fresh clone.
9. **This re-check is static reading.** "verified 2026-11-11" means the mechanism is present in the current source at the cited lines. No finding was executed, and no test suite run was attributed to any row.

Update this register in place when you fix something — add the test, move the row, or delete it once it is genuinely closed. Do not create a second defect document.

## Testing

### Backend

From `backend/`, with the Python 3.11 environment active:

```powershell
python -m pip install -r requirements.txt -c constraints.txt -r requirements-dev.txt
python -m pip check
python -m pytest -q
```

The current verified run is **526 passed, 0 skipped** in 2 m 28 s on Python 3.11.9, and `npm test` is **130 pass, 0 fail**. Both figures are environment-dependent, not properties of the repository: `pytest.ini` sets `testpaths = tests`, so top-level helper scripts are never collected, and the real-model regression tests **skip** unless scikit-learn is the pinned 1.7.x (`tests/test_integration_real_model.py:71,90`) — in any other environment the same command reports fewer passed and several skipped. Test counts quoted in older reports are stale snapshots; if you need a number, run the suite in this environment.

Run the suite with the environment's own interpreter. On Windows the bare `python` on `PATH` is often a different version, and a wrong interpreter both changes the result and can fail at collection — `shap` (a declared runtime requirement) is imported by `tests/test_explanations.py`, so an environment without it stops the whole run before any test executes. `pip check` is the fast way to confirm the environment is complete.

Isolation guarantees:

- `backend/tests/conftest.py` sets `DATABASE_URL` to a throwaway file under `%TEMP%\researchtwin-tests-*` **before** importing the application, so no test ever opens `backend/researchtwin.db`.
- `conftest.py` has exactly **one** autouse fixture, `reset_model_caches` (`:122-156`), which clears model/embedding caches and `rate_limit_counters`. Collaboration and opportunity truncation is done by **per-module** autouse fixtures (`tests/test_collaboration.py:27`, `tests/test_opportunities.py:43`) — cross-file isolation depends on those modules being collected, so do not describe it as a global guarantee.
- Tests write only to disposable databases. `create_all` idempotency is asserted against existing rows rather than by dropping them.
- Deleting the `%TEMP%` test directories is safe; they hold only seeded fixture rows.

Production-like checks worth knowing about: `tests/test_migrations.py` (models vs head, fresh upgrade, stamped legacy database, downgrade, incompatible upgrade) and `tests/test_database_reliability.py` (initialization idempotency, fail-fast, session rollback/close, `503` behavior, empty-database responses, recommendation ID and explanation integrity).

### Frontend

```powershell
npm test
```

The current locally verified run is **130 frontend tests**, including `tests/frontend/headers.test.cjs` (CSP/header directives and every external asset on both entry pages) and the API-base-URL configuration checks.

### Browser journeys

Run actual-browser journeys **only** against a new temporary SQLite database. The harness asserts this: it refuses any URL that is not `sqlite:///` and any path outside the OS temporary directory, so it can never be pointed at `backend/researchtwin.db` or a shared database by accident.

1. Create the isolated database and start the API against it (from `backend/`, with the Python 3.11 environment active). This first startup creates the schema:

   ```powershell
   $e2eDir = Join-Path $env:TEMP ("ResearchTwin-e2e-" + [guid]::NewGuid().ToString("N"))
   New-Item -ItemType Directory -Path $e2eDir | Out-Null
   $env:DATABASE_URL = "sqlite:///" + ($e2eDir.Replace('\','/') + "/application.sqlite")
   $env:RATE_LIMIT_HASH_SECRET = [guid]::NewGuid().ToString("N")
   $env:RATE_LIMIT_REQUIRE_SHARED_DATABASE = "false"
   $env:RATE_LIMIT_TRUST_CF_CONNECTING_IP = "false"
   $env:FRONTEND_ORIGINS = "http://127.0.0.1:5500"
   # Higher limits stop this multi-journey run from exhausting the shared local
   # test-IP bucket. Production limits are covered by the backend tests instead.
   $env:RATE_LIMIT_REGISTER_MAX = "100"; $env:RATE_LIMIT_LOGIN_MAX = "100"; $env:RATE_LIMIT_RECOMMENDATION_MAX = "100"

   uvicorn app.main:app --reload --port 8000
   ```

2. In a second shell, set the **same** `DATABASE_URL`, enable the CLI, and provision a test administrator with a test-only password of at least 16 characters (the CLI prompts without echoing):

   ```powershell
   $env:DATABASE_URL = "sqlite:///<the same temp path from step 1>/application.sqlite"
   $env:RESEARCHTWIN_ENABLE_ADMIN_PROVISIONING = "YES"
   python .\provision_admin.py
   ```

3. In a third shell, serve the static frontend, then run the journey from the repository root:

   ```powershell
   npx serve frontend --listen 5500 --no-clipboard
   ```

   ```powershell
   $env:RT_PHASE3_DATABASE_URL     = "<the same temp sqlite URL>"
   $env:RT_PHASE3_ADMIN_EMAIL      = "<the temporary admin email>"
   $env:RT_PHASE3_ADMIN_PASSWORD   = "<the temporary admin password>"
   $env:RT_PHASE3_PYTHON           = "<path to the Python 3.11 environment python.exe>"
   $env:RT_PHASE3_API_URL          = "http://127.0.0.1:8000"
   $env:RT_PHASE3_FRONTEND_URL     = "http://127.0.0.1:5500/researchtwin.html"
   $env:RT_PHASE3_ARTIFACT_DIR     = Join-Path $e2eDir "artifacts"
   node tests/e2e/researchtwin.phase3.e2e.cjs
   ```

   Playwright's Chromium is required (`npx playwright install chromium` once). Note the distinction: the harness `require`s the **`playwright`** package (`researchtwin.phase3.e2e.cjs:9`), while only `@playwright/test ^1.64.1` appears in `package.json` under `devDependencies`, so `playwright` itself arrives transitively — if that ever breaks, the fix is a declared devDependency, not a different command. The run registers temporary student and faculty users, imports the bundled researchers as the temporary admin, checks role denials and duplicate-import behavior, and exercises the UI journeys headlessly. A failed browser assertion saves a full-page screenshot and a Playwright trace in `RT_PHASE3_ARTIFACT_DIR`. Never write those `RT_PHASE3_ADMIN_*` values into a file or a shared shell history.

The harness records 13 journey groups, each reported by name at the point it completes:

1. isolated admin provisioning, authorization, and duplicate-safe import
2. invalid registration input handling
3. student register/login, session restore, profile create/edit, and safe empty-profile rejection
4. browser network failure handling
5. real seven-feature recommendation/model explanations (the report includes the ranked-result count)
6. researcher directory profile details
7. refresh during delayed roadmap request
8. roadmap generation, concurrent milestone lock, and persisted completion after refresh
9. collaboration request creation, duplicate rejection, and student-visible pending status
10. faculty profile/link/inbox, accept/reject decisions, and resulting student statuses
11. admin console account lifecycle, faculty link management, audit and export, and student denial of the admin API
12. expired session rejection
13. student and faculty logout revocation

The run prints `journeysCompleted` at the end and fails if the browser reported any page error.

Manual browser checklist (what the automated journeys do not prove):

1. Register a student and a faculty account in two profiles; confirm neither can open the other's console.
2. Save a student profile, request recommendations, and read the explanations; confirm scores are stable for the same profile.
3. Confirm an unsaved profile yields an explicit message rather than silent empty results.
4. Send a collaboration request; check the faculty inbox only shows it once the faculty account has a verified link.
5. Accept one request and reject another; check the student list reflects both statuses after a refresh.
6. Complete a roadmap milestone, reload, and confirm persistence; then complete the same milestone twice and confirm no duplicate row.
7. Sign out in one tab and confirm the other tab is rejected on its next request.
8. Open the admin console; verify role/status filters, session revocation, and the audit log; confirm self-demotion is refused.
9. Browse the directory, filter by department and skill, and expand a researcher's details.
10. Exercise a workspace: add a task and a milestone, comment; then repeat a request with a non-member token.
11. Create a team, invite, accept, and remove a member.
12. Check an opportunity's eligibility, apply, withdraw, and confirm the applicant sees only their own application.
13. Open a thesis with milestones, record progress, review the history; submit a publication and walk its status transitions.

### Memory measurement

To measure real process memory, query the OS for the actual worker process rather than the launcher. The venv `python.exe` is a **shim that re-execs**, so its own working set is not the application's. On Windows use `GetProcessMemoryInfo` against the re-executed child; on WSL use the child PID. Measurements taken this way landed around **412–421 MB** resident for a warmed service. Context for that figure: `constraints.txt:9-14` records that the torch import alone costs ~190 MB RSS and the sentence-transformers stack ~405 MB, "which does not fit the 512 MB Render Free instance", and that the full ONNX workflow in WSL peaked at 412.2 MB — 412–421 MB therefore sits close to that ceiling, not comfortably under it. **All of these are Windows/WSL local measurements and are not evidence of hosted-platform behavior**; measure the deployed instance during an approved change.

## Deployment

### Local demo

Use the isolated SQLite setup above, start the backend and static frontend locally, provision a test administrator through the CLI, and import the bundled researcher CSV. Keep the demo database in a temporary directory for a clean run. No production service or data is needed for local development.

### Render (backend)

The repository declares a Render Python service in `render.yaml`: `rootDir: backend`, Python 3.11.11, build `pip install -r requirements.txt -c constraints.txt && python scripts/fetch_embedding_model.py`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`, health check path `/ready`. The declared `--workers 1` is the platform-side confirmation of the process-local-lock rule above.

**The declared start command carries no proxy-header configuration** — `render.yaml:7` sets neither `--proxy-headers` nor `--forwarded-allow-ips`, so Uvicorn does not derive `request.client.host` from `X-Forwarded-For` and the application sees Render's proxy peer as the client for every request. This is an **unresolved deployment risk**, not a gap to close by guessing: it affects per-client rate-limit bucketing and the meaning of any IP in the logs. Confirm the real ingress peer and header behavior on the hosted service before choosing between the proxy-header flags and the `CF-Connecting-IP` path (see [Residual risks](#residual-risks), item 2).

Procedure — each step is an approved, one-at-a-time action, not a batch:

1. Back up the current live database and `verify` the backup.
2. Re-run [Confirm the database target first](#confirm-the-database-target-first-mandatory) in a **fresh shell** that contains only the rehearsal target's connection details, then restore the backup into that **disposable** copy and run `alembic upgrade head` there; review the result. Never rehearse in a shell that still holds the source connection string.
3. Confirm, through the provider's project/branch mapping rather than a hostname comparison, that the target database is a durable PostgreSQL instance that is not on an expiring plan.
4. Set `DATABASE_URL` as a secret in the dashboard (never in the repo).
5. Set `RATE_LIMIT_HASH_SECRET` (≥ 32 random bytes), `RATE_LIMIT_REQUIRE_SHARED_DATABASE=true`, `RATE_LIMIT_TRUST_CF_CONNECTING_IP=false`, `RATE_LIMIT_TRUSTED_PROXY_CIDRS` (empty until proven), `FRONTEND_ORIGINS` to the exact frontend origin, and `MAX_REQUEST_BODY_BYTES`.
6. Confirm `AUTH_SESSION_TTL_SECONDS` is an explicit, bounded policy value.
7. Deploy the release build to a **staging** service or preview and point it at the migrated copy.
8. `GET /ready` on staging; confirm the Alembic head, artifact digest, and limiter all pass.
9. Run the read-only smoke set against staging: `/health`, `/researchers/?limit=1`, and one authenticated recommendation request from a test student.
10. Only then repoint the production service's `DATABASE_URL`, deploy, and re-check `/ready` and the smoke set. Confirm the secret you typed resolves to the intended project and branch in the dashboard **before** the restart finishes.
11. Record the revision, artifact digest, commit SHA, and verification output.

The Blueprint does **not** declare a PostgreSQL service, persistent disk, plan, or migration command — those are dashboard state and must be confirmed, not assumed. If the start command is ever changed to use more than one worker, revisit the process-local-lock limitation first.

### Netlify (frontend)

Publish directory `frontend`; `frontend/_headers` supplies the CSP and the rest of the security headers.

1. Confirm the build publishes `frontend` and that `_headers` is included in the deploy output.
2. Confirm `frontend-config.js` resolves the intended API origin for the production host.
3. Add that API origin to the CSP `connect-src` deliberately.
4. After deploy, fetch the live page and check the response headers actually match `_headers` — the file being present is not proof the CDN served it.

### Pre-release sequence

`pip check` → backend `pytest -q` → `npm test` → `alembic check` → browser journeys on a throwaway database → secrets scan of the staged diff → clean-checkout verification that `backend/models/researchtwin_logistic_v2_7features.joblib` is present → staging `/ready` → read-only smoke → approval.

### Rollback

Roll back the **code** by redeploying the previous build. Roll back **data** only to a new, verified restore target and repoint `DATABASE_URL`; never overwrite a live database, and re-run the target-identity pre-flight before repointing — a rollback is exactly when an unverified connection string does the most damage. If the schema advanced, redeploy the previous application build *before* considering a downgrade, and remember a downgrade drops data.

**Frontend rollback** goes through the host's deploy history — select the previous published deploy and re-publish it; do not rebuild from cache when dependency pins changed. Keep the previous `frontend-config.js` API origin compatible with the rolled-back backend: a frontend pinned to a newer API origin against an older backend fails closed by design, which is safe but looks like an outage. Roll application code and model artifacts back **together** — the seven-feature order is validated at load (`services/recommendation.py:125-131`), so a mismatched artifact fails readiness rather than silently re-ranking.

After a credential exposure, rotate `DATABASE_URL`, `RATE_LIMIT_HASH_SECRET`, and affected passwords once service is restored.

### Incident checklist

1. Stop writes and preserve logs.
2. Confirm scope: data loss, corruption, credential compromise, or provider failure.
3. If credentials may be exposed, rotate secrets after restoring service.
4. Restore the newest verified backup to a new database and verify row counts.
5. Run migrations only when the restored schema is older than the code.
6. Repoint the service, verify `/ready` and a read-only API call, then reopen writes.
7. Document the timeline, evidence, and follow-up actions.

## Operational procedures

### Secrets hygiene

No secret belongs in a tracked file. Before any commit, scan the staged diff for credential-shaped strings:

```bash
git diff --cached | grep -nEi '(pass(word|wd)?|secret|token|api[-_]?key|BEGIN [A-Z ]*PRIVATE KEY|://[^/]*:[^@]*@)' | head -50
```

A `postgresql://<user>:<secret>@<host>` occurrence is the highest-value hit. Rotate anything that was ever committed; deleting a file does not remove it from history.

### Windows shell notes

Helper scripts that invoke a CLI such as `neon` through `subprocess` must resolve the `.CMD` wrapper (`shutil.which`) rather than the bare command name. Git Bash rewrites POSIX-looking API paths such as `/projects/...` into Windows paths unless you set `MSYS_NO_PATHCONV=1`.

## Troubleshooting

- **`401 Unauthorized`** — sign in again; the session may be expired or revoked, or the account was deactivated.
- **`403 Forbidden`** — the authenticated account lacks the role, ownership, or membership the route requires. Note that workspaces and teams answer **`404`** to non-members by design, so a "not found" on a workspace or team ID you were told exists usually means "you are not a member". Labs and other resources check membership per handler.
- **`413 Request body is too large`** — reduce the body; the default cap is 65,536 bytes.
- **`422 Unprocessable Entity`** — check the schema; an unexpected extra field is rejected by `extra="forbid"` **except on the two recommendation-request models**, where it is silently dropped. Verify `top_k` against the route (1–10 recommendations, 1–20 opportunity matches, 1–50 trends) and that timestamps are epoch-second integers.
- **`400` on a recommendation or roadmap call** — no saved profile exists for the authenticated student; save the profile first. Protected routes never accept a client-supplied profile.
- **`429 Too Many Requests`** — wait for `Retry-After`. If many unrelated users hit limits together on one deployment, suspect a single proxy peer address rather than abuse.
- **`503 Request protection is not configured`** — provide `RATE_LIMIT_HASH_SECRET` (≥ 32 bytes). If shared-database mode is on, the bind must be PostgreSQL.
- **`503` from `/ready`** — check database connectivity, the Alembic revision on PostgreSQL, the active model artifact path and digest, and limiter configuration. Each is an independent gate.
- **`503 {"detail":"Database unavailable"}` during requests** — the database errored or timed out. On SQLite this is usually a write lock; on serverless Postgres it may be a cold resume or pool exhaustion.
- **Recommendation or intelligence endpoints slow under concurrency** — inference is capped at `RECOMMENDATION_MAX_CONCURRENCY=2` per process, and each intelligence endpoint may open two pooled connections. Add instances, not workers.
- **Empty recommendations** — the directory has no researcher rows yet (a fresh database starts empty until an admin imports the bundled CSV). A *missing profile* is not silent: it returns `400`, see the row above.
- **`alembic current`/`check`/`upgrade` quietly reported nothing about the hosted database** — `DATABASE_URL` was unset or blank, so Alembic used `backend/researchtwin.db`. Remove the variable rather than assigning it empty, and run the pre-flight.
- **Session restored after refresh** — the token persists in `sessionStorage`; logging out revokes it. Clearing browser storage discards the token without revoking the server session until it expires.
- **API fails from a local browser** — serve the frontend on port 5500 and the API on 8000; check the browser console, the resolved API base, the network tab, and `FRONTEND_ORIGINS`.
- **A deploy loads but every request is blocked by the browser** — the API origin was changed in only one of the three places (frontend config, CSP, CORS).
- **Duplicate researchers after an import** — the bundled CSV import is idempotent; duplicates come from directory writes or a pre-repair database. Check `SELECT name, COUNT(*) FROM researchers GROUP BY name HAVING COUNT(*) > 1`.
- **Roadmap milestones vanished** — the researcher's `skills` text changed, orphaning keyed rows. Expected behavior, not corruption.

## Known limitations and open decisions

- **Institution/tenant isolation is an open decision.** The platform now stores institutions, memberships, labs, and inter-university collaborations, and enforces affiliation-based access on those routes. What has **not** been decided is whether a deployment is single-tenant (one institution per deployment) or multi-tenant (one shared deployment), and therefore whether a hard `tenant_id` boundary is required across every table and query. Until that is explicitly approved, do not add a `tenant_id` column or claim isolation between institutions sharing one deployment.
- **Rate limiting is not production-proven** until the client-IP boundary and shared PostgreSQL topology are verified live.
- **`/health` cannot report `unhealthy` when the database blocks import.** Import-time initialization means the process may never serve.
- **Pinned dependency completeness.** Direct runtime requirements and constraints are pinned; the **transitive** graph beneath `onnxruntime`/`tokenizers`/`shap` is not locked by a full lockfile. Torch is not a dependency at all. Cold-start resource use on the target runtime is unverified.
- **Free-tier durability.** The hosting tier is not assumed to provide durable backups or a persistent disk; both must be confirmed in the dashboard. The reported source-database expiry date is an unverified historical snapshot (see [Database hosting and migration constraints](#database-hosting-and-migration-constraints)).
- **Documentation policy.** This file is the project's only Markdown document, and there are no others to fall back on. The open defect list lives in [Open defect register](#open-defect-register) and is updated here, in place. The three operator-facing references in `backend/scripts/database_backup.py:7,70,312` now point at [Backups and restore](#backups-and-restore) instead of the removed `DISASTER_RECOVERY.md`. Only those strings changed: the utility's behavior, command-line interface and safety checks are unchanged, verified on 2026-11-11 by the 12 tests in `backend/tests/test_backup_restore.py` (13 pass when selection is widened with `-k backup`, which adds `test_database_selection.py::test_backup_utility_defaults_to_the_sqlite_demo_database`) and a 531-test full backend run. When you change behavior, update the relevant section here rather than adding a new document.

## License

Proprietary — All rights reserved.

## Support

For issues and questions: [ResearchTwin repository issues](https://github.com/venkatesh19-prog/ResearchTwin/issues).

## Documentation history

Earlier phases of this project accumulated separate setup, API-contract, security, database-verification, and phase-report documents. Their durable content has been consolidated into this file and the obsolete copies were removed. Where those documents disagreed with the code, the code won; anything that could not be verified is labelled UNVERIFIED rather than asserted. Per-phase changelogs, dated acceptance results and historical test-count snapshots were dropped deliberately because they could not be kept true. Two categories were **not** dropped: the open defect list, carried into [Open defect register](#open-defect-register), and the field-level API contracts, deliberately delegated to `/openapi.json` as the schema authority instead of being transcribed here.
