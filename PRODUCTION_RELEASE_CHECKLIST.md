# Production Release Checklist — ResearchTwin

> **Current Phase 4 update (2026-11-01):** this file contains historical Phase D/E/G
> evidence and must not be read as a current live-service report. The current
> source review found an active seven-feature model artifact that is untracked,
> no Alembic migration system, and production Render/Netlify settings that remain
> unverified. No deployment, live-service change, production database operation,
> or real administrator creation was performed. Current regression results and
> remaining gates are recorded in the Phase 4 section at the end; see
> `PRODUCTION_CONFIGURATION_CHECKLIST.md` for actionable settings.

**Audit date:** 2026-10-28
**Project root:** `C:\Users\Venkatesh\ResearchTwin`
**Repository:** `https://github.com/venkatesh19-prog/ResearchTwin.git` (branch `main`)
**Production API:** `https://researchtwin-api.onrender.com`
**Production frontend:** `https://starlit-empanada-a323e3.netlify.app`

## Release verdict

**BLOCKED — do not release as production-ready yet.**

The earlier live audit observed recommendation failures and a frontend access gate. Those observations
were not rechecked during Phase E. The current local changes are uncommitted and undeployed, so production
remains blocked pending configuration, deployment, and live verification.

Status legend:

- **PASS** — verified by command output or a live probe.
- **FAIL** — verified defect.
- **BLOCKED** — requires a dashboard change, approval, or a code/architecture decision.
- **UNVERIFIED** — no reliable evidence available from this environment.

| Area | Status | Evidence |
|---|---|---|
| Render service configuration file | **PASS** | `render.yaml` matches expected root/build/start/health values |
| Production service reachability | **PASS** | `/health` 200; `/` 200; `/researchers/` 200 |
| Production database connectivity | **PASS** | `/researchers/` returned 30 rows |
| Production recommendation endpoint | **FAIL** | Three POSTs: 500 after 152.3s, 130.4s, 119.9s |
| Production source revision | **FAIL** | `origin/main` at `6c1439a`; local `main` one commit ahead plus 8 modified files |
| Direct dependency pins | **PASS** | 24 exact pins; `psycopg[binary]>=3.2,<4` intentionally constrained |
| Transitive dependency pins | **FAIL** | torch/transformers/tokenizers/scipy/numba/etc. unpinned |
| Model artifact committed | **PASS** | `researchtwin_logistic_render.joblib` tracked; loads and scores locally |
| Environment variables (names only) | **PASS** (inferred) | `DATABASE_URL` and `FRONTEND_ORIGINS` declared `sync: false`; behavior proves both are set |
| Hard-coded secrets / debug mode | **PASS** | No source secrets, no `.env` files, no `debug=True`, no `--reload` |
| CORS for the Netlify origin | **PASS** | Preflight returned `access-control-allow-origin: https://starlit-empanada-a323e3.netlify.app` |
| Authentication on write/import/delete | **FAIL** | All write routes are public |
| Error-output safety | **FAIL** | Import and recommendation routes return raw exception strings |
| Health/readiness semantics | **FAIL** | `/health` is DB-only and green while recommendations are broken |
| Memory envelope | **BLOCKED** | Local peak 658.5 MB; Render Free/Starter is 512 MB; plan not specified in `render.yaml` |
| Cold-start model initialization | **FAIL** | Cold HF download took 136.6s; frontend timeout is 90s |
| Netlify publish directory | **PASS** | `netlify.toml` publishes `frontend` |
| Public frontend access | **FAIL** | Every live path returns 401 (Edge Access gate) |
| Local automated suite under Python 3.11 | **PASS** | 84 passed, exit 0, `pip check` clean |
| Production browser journey | **UNVERIFIED** | Blocked by the 401 gate; no deployment changes made |

---

## 1. Verified checks with evidence

### 1.1 Render configuration file

Source: [render.yaml](file:///C:/Users/Venkatesh/ResearchTwin/render.yaml)

```yaml
services:
  - type: web
    name: researchtwin-api
    runtime: python
    rootDir: backend
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.11
      - key: DATABASE_URL
        sync: false
      - key: FRONTEND_ORIGINS
        sync: false
```

- Root directory, build command, start command, and health path are internally consistent with a
  `backend` root and `app.main:app`.
- No `plan` and no `disk` are declared. Absence of a disk means an SQLite file would be ephemeral.
- Whether the Render dashboard actually matches this file is **UNVERIFIED**; the file is the only
  configuration evidence available without dashboard access.

### 1.2 Production reachability (read-only probes)

| Probe | Result |
|---|---|
| `GET /health` | **200** in 0.84s, body `{"status":"healthy"}` |
| `GET /` | **200** in 1.78s |
| `GET /researchers/` | **200** in 1.30s, 13,750 bytes, **30 rows** |
| `OPTIONS /recommendations/researchers` from Netlify origin | **200**, correct ACAO header |
| `GET /docs`, `/openapi.json`, `/redoc` | **200** (publicly exposed) |
| `POST /recommendations/researchers` (real profile) | **500** after 152.3s, body `Internal Server Error` |
| Same POST repeated | **500** after 130.4s |
| Same POST with an empty profile (to skip semantic matching) | **500** after 119.9s |

No write, import, update, or delete request was sent to production.

The 500 responses are plain-text Starlette errors, not the JSON 503 produced by `RecommendationError`
or `SemanticMatchingError`. That means an exception outside those typed paths escaped, or the deployed
revision does not contain the current error handling.

### 1.3 Production source drift

- `origin/main` is at `6c1439a` ("Fix production API URL").
- Local `main` is `0f42834`, one commit ahead, and the working tree has **8 modified tracked files**
  (442 insertions, 85 deletions) plus new tests and audit documents.
- Current local code cannot be what production is running. The deployed recommendation failure cannot
  be attributed to the current working tree until the current tree is deployed and retested.
- No staging, commit, push, or deploy was performed.

### 1.4 Local production-like tests

Environment: `C:\Users\Venkatesh\researchtwin-venv311` (Python 3.11.9, closest available to the
declared 3.11.11).

| Check | Result |
|---|---|
| `python -m pytest -q` in `backend/` | **84 passed**, 2 deprecation warnings, 1.38s, exit 0 |
| `python -m pip check` | **No broken requirements found** |
| `POST /recommendations/researchers`, warm HF cache | **200** in 8.46s |
| Same request, cold HF cache | **200** in 136.55s |
| Peak working set during the request | **658.5 MB** |
| RSS after `import app.main` | 162.5 MB |
| RSS after `import sentence_transformers` | 442.0 MB (torch dominates) |

The cold-cache run downloaded `all-MiniLM-L6-v2` (88 MB) into a test cache created under
`backend/hub`. That directory was an artifact of this audit, was untracked, and was removed.

### 1.5 Model artifact

- [backend/models/researchtwin_logistic_render.joblib](file:///C:/Users/Venkatesh/ResearchTwin/backend/models/researchtwin_logistic_render.joblib)
  is tracked, 2,233 bytes, SHA-256 `9abbcee82aebd41652c4a6f29a2f865d21b15ed0a098cc91ce6f2a1bdc62b5cf`.
- The serving code validates the feature order and the `scaler`/`classifier` pipeline steps
  ([recommendation.py:71](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L71)).
- It loads and produces scores under scikit-learn 1.7.2 / joblib 1.6.0 locally.
- Production compatibility is **FAIL** as a user-facing flow: the recommendation endpoint returns 500.

### 1.6 Environment variables (names only)

`render.yaml` declares `PYTHON_VERSION`, `DATABASE_URL`, and `FRONTEND_ORIGINS`. No values were read or
printed. Two behavioral proofs show the secrets are configured:

- `/researchers/` returns 30 rows, so `DATABASE_URL` is set and points at a populated database.
  If it were unset, the app would create a fresh SQLite file with zero rows.
- CORS preflight from the Netlify origin returns that exact origin, so `FRONTEND_ORIGINS` includes it.

The database engine, host, backup policy, and persistence across deploys remain **UNVERIFIED**.

### 1.7 Secret, debug, and logging scan

- No hard-coded credentials in tracked source. Pattern matches were limited to placeholder values in
  tests and audit documentation; no live-looking keys or connection strings were found.
- No `.env`, `.env.local`, or `backend/.env` file exists in the working tree.
- `.gitignore` excludes `.env`, `.env.*`, and `*.db`.
- No `debug=True`, `--reload`, or equivalent development mode in the start command.
- The DB exception handler logs only method, path, and exception class
  ([main.py:56](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L56)). It does not log
  query text or credentials.
- `/health` logs only the exception class on a failed probe
  ([main.py:87](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L87)).

### 1.8 CORS

Verified preflight response:

```
HTTP/1.1 200 OK
access-control-allow-origin: https://starlit-empanada-a323e3.netlify.app
access-control-allow-methods: GET, POST, PUT, DELETE, OPTIONS
access-control-allow-headers: content-type
access-control-allow-credentials: (not present; allow_credentials=False)
```

The origin allow-list is built from localhost plus `FRONTEND_ORIGINS`
([main.py:37](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L37)). This is scoped, not a
wildcard, and does not permit credentialed requests.

### 1.9 Frontend/backend agreement

> **Update 2026-10-28 (Phase D):** the application now calls `/auth/*`,
> `/students/me/profile`, `/faculty/me/profile`, and
> `/students/me/recommendations` through `frontend/api-client.js`. The legacy
> section below describes the pre-Phase-D state and is retained for history.

- [frontend/frontend-config.js:1](file:///C:/Users/Venkatesh/ResearchTwin/frontend/frontend-config.js#L1)
  sets `window.RESEARCHTWIN_API_BASE` to `https://researchtwin-api.onrender.com`.
- [frontend/api-client.js:1](file:///C:/Users/Venkatesh/ResearchTwin/frontend/api-client.js#L1)
  reads that value and attaches the bearer token to authenticated calls.
- [frontend/researchtwin.html:439](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L439)
  loads `frontend-config.js` and `api-client.js` before the application script.
- The app calls `GET /researchers/` (public directory) and the authenticated
  profile/recommendation endpoints; it does not call the unauthenticated
  write/import/delete routes.
- [netlify.toml](file:///C:/Users/Venkatesh/ResearchTwin/netlify.toml) publishes the `frontend`
  directory. The duplicate root-level HTML files are not published.
- Live frontend paths return **401**: `/`, `/researchtwin.html`, and `/frontend-config.js`.
  The 401 redirects to Netlify Edge Access. This may be intentional protection or a launch blocker;
  it must be decided explicitly.
- Production CORS must include the deployed frontend origin via
  `FRONTEND_ORIGINS`; only `127.0.0.1:5500` and `localhost:5500` are allowed by default.

---

## 2. Release blockers

### P0-1 — Production recommendation endpoint is broken

**Status: FAIL**

Evidence: three production POSTs returned 500 after 152.3s, 130.4s, and 119.9s, including an
empty-profile payload that should skip semantic matching. `/health` returned 200 throughout, and
`GET /researchers/` returned 30 rows.

Likely contributors, in order:

1. The deployed revision predates the current code (P0-2), so its behavior may differ from the
   locally tested code.
2. The runtime loads `all-MiniLM-L6-v2` from Hugging Face on first use with no persistent cache.
   Locally, a cold download took 136.55s. Production timings are consistent with that cold path.
3. Peak RSS is 658.5 MB locally with CPU torch. A 512 MB Render instance would exhaust memory while
   loading torch plus the model.

Do not mark this fixed until a production POST returns 200 in under the frontend timeout with
Render logs free of exceptions/OOM messages.

### P0-2 — Production cannot be running the current code

**Status: FAIL**

Evidence: `origin/main` is `6c1439a`; local `main` is `0f42834` (one commit ahead), and 8 tracked
files have uncommitted changes. The current recommendation hardening, tests, and database error
handling are not deployable from GitHub in their current state. A deploy from the remote cannot
contain them.

Action: review, commit, push, and deploy the intended release revision. This requires your approval and
was not performed.

### P0-3 — Public frontend is gated by Netlify Edge Access

**Status: FAIL / decision required**

Evidence: `https://starlit-empanada-a323e3.netlify.app/`, `/researchtwin.html`, and
`/frontend-config.js` all return 401 and redirect to Edge Access.

Action: decide whether the site is intentionally private. If public, remove the access rule in the
Netlify dashboard. If private, document the access policy and verify the authenticated browser journey;
neither was possible here.

### P1-1 — Memory envelope exceeds the likely instance size

**Status: BLOCKED**

Evidence: 658.5 MB peak, 653.2 MB final RSS; 442.0 MB after importing `sentence_transformers`;
162.5 MB after importing the app. `render.yaml` declares no `plan`. Render Free and Starter instances
provide 512 MB. A Standard instance provides 2 GB.

Action: confirm the dashboard instance type. Either move to at least 1 GB (Standard for headroom) or
reduce runtime memory (see §4). Re-measure in production after the change.

### P1-2 — Cold start exceeds the frontend timeout

**Status: FAIL**

Evidence: cold-cache request 136.55s versus 8.46s warm. The frontend aborts at 90s
([researchtwin.html:404](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L404)).
Production requests took 120–152s.

Action: eliminate the runtime download or persist the model cache (see §4), then set a timeout that
reflects measured warm latency. Do not simply raise the timeout while the endpoint still fails.

### P1-3 — Heavy transitive dependencies are unpinned and pull the CUDA torch build

**Status: FAIL**

[backend/requirements.txt](file:///C:/Users/Venkatesh/ResearchTwin/backend/requirements.txt) has 25
entries: 24 exact pins plus `psycopg[binary]>=3.2,<4` (an intentional compatible range). The runtime
stack pulled in by `sentence-transformers`, `shap`, and `scikit-learn` is not pinned, including:

`torch`, `transformers`, `tokenizers`, `huggingface_hub`, `safetensors`, `scipy`, `numba`, `llvmlite`,
`cloudpickle`, `slicer`, `tqdm`, `sympy`, `networkx`, `filelock`, `fsspec`, `hf-xet`, `regex`,
`PyYAML`, `Jinja2`, `MarkupSafe`.

PyPI metadata for the latest `torch` (2.14.1) lists four `nvidia-*` dependencies for Linux x86_64, and
`2.14.1+cpu` is not published on PyPI. The requirements file has no CPU index, so a Render build will
resolve the CUDA wheel by default. This increases image size, build time, and memory pressure.
`sentence-transformers==6.1.0` only constrains `torch>=2.2`.

Action: pin the tested transitive versions and install CPU torch from the PyTorch CPU index as a
separate build step, or generate a constraints/lock file. Rebuild and verify in production.

### P1-4 — Write, import, and delete routes are unauthenticated

**Status: FAIL**

[backend/app/api/researchers.py](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/researchers.py)
exposes:

- `POST /researchers/` — create arbitrary records
- `PUT /researchers/{id}` — overwrite a record
- `DELETE /researchers/{id}` — delete a record
- `POST /researchers/import` — import the bundled CSV, with no idempotency (a prior audit verified
  30 rows becoming 60 after a repeat import)

There is no authorization on these routes, and no rate limiting anywhere. The
legacy recommendation endpoint is also still public and expensive. The new
`/auth/*` and profile routes are protected, but that does not cover the
researcher write/import surface described above. Combined with public `/docs`,
this is an abuse and data-integrity risk.

Action: protect these routes with a faculty/admin role or remove them from the
public deployment; disable or protect import; add request rate limits and input
size limits; protect or retire `POST /recommendations/researchers`. This is a
design decision and requires approval.

### P1-5 — Health does not reflect readiness

**Status: FAIL**

Evidence: `/health` returns 200 while `/recommendations/researchers` returns 500. The probe only runs
`SELECT 1` ([main.py:87](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L87)). It does not
check the model bundle, the semantic model, the CSV background data, or a warm-up inference.

Action: keep `/health` as a cheap liveness probe and add `/ready` that verifies the model artifact,
SHAP background data, semantic model availability, and DB. Point Render's health check at the probe
whose semantics you intend. Ensure a cold model load cannot make deploys appear healthy while requests
fail.

### P2 — Additional findings

| Finding | Status | Action |
|---|---|---|
| Import leaks internals in `detail=f"Import failed: {str(e)}"` ([researchers.py:214](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/researchers.py#L214)) | **FAIL** | Log the full error server-side; return a generic message/code |
| Recommendation 503 returns `str(exc)` ([students.py:50](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/students.py#L50)) and errors include absolute paths ([recommendation.py:120](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L120), [semantic_matching.py:20](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/semantic_matching.py#L20)) | **FAIL** | Sanitize client messages; keep detail in logs |
| `/docs`, `/redoc`, `/openapi.json` are public (200) | **FAIL (hardening)** | Disable in production if not needed for consumers |
| CORS allows `PUT`/`DELETE` and always allows localhost origins | **PASS (minor)** | Reduce methods to `GET, POST, OPTIONS`; gate localhost to dev |
| Request schemas have unbounded strings ([schemas.py:6](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/schemas.py#L6), [students.py:21](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/students.py#L21)) | **FAIL (hardening)** | Add `max_length` and body-size limits |
| No rate limiting on an endpoint that can take 2+ minutes | **FAIL** | Add per-IP limits or a queue |
| `Base.metadata.create_all` runs at import ([main.py:24](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L24)); no migrations | **PASS (documented risk)** | Fail-fast is intentional; use additive migrations for future schema changes |
| Production DB persistence and backups | **UNVERIFIED** | Confirm provider, backups, and survival across a redeploy; do not run import/seed in production |
| Production interpreter is really 3.11.11 | **UNVERIFIED** | Confirm in the Render dashboard; local evidence is 3.11.9 |
| Render dashboard matches `render.yaml` | **UNVERIFIED** | Compare root/build/start/health/plan/disk in the dashboard |
| Deployed commit SHA | **UNVERIFIED** | Check the Render deploy log; it cannot be `0f42834` or the current working tree |

---

## 3. Dependency pinning detail

### Direct runtime dependencies

All direct imports used by the service are declared. Except for the psycopg range, every declared
dependency is an exact pin.

| Package | Declared | Installed in 3.11 env |
|---|---|---|
| fastapi | `==0.141.1` | 0.141.1 |
| starlette | `==1.6.0` | 1.6.0 |
| uvicorn | `==0.53.0` | 0.53.0 |
| pydantic / pydantic_core | `==2.13.5` / `==2.46.5` | match |
| SQLAlchemy | `==2.0.53` | 2.0.53 |
| numpy | `==2.2.6` | 2.2.6 |
| pandas | `==2.3.3` | 2.3.3 |
| scikit-learn | `==1.7.2` | 1.7.2 |
| joblib | `==1.6.0` | 1.6.0 |
| shap | `==0.51.0` | 0.51.0 |
| sentence-transformers | `==6.1.0` | 6.1.0 |
| psycopg | `[binary]>=3.2,<4` | 3.3.6 |

### Tested transitive versions that are not pinned

```text
torch==2.14.1+cpu        transformers==5.21.0     tokenizers==0.23.3
huggingface_hub==1.33.0  safetensors==0.8.0       scipy==1.17.1
numba==0.68.1            llvmlite==0.50.0         cloudpickle==3.1.2
slicer==0.0.8            tqdm==4.70.1             sympy==1.14.0
networkx==3.6.1          filelock==3.32.3         fsspec==2026.7.0
hf-xet==1.7.0            regex==2026.9.29         PyYAML==6.0.3
Jinja2==3.1.6            MarkupSafe==3.0.3
```

These are the versions that passed the 84-test suite locally. They are not guaranteed to be what a fresh
Render build resolves. Pin them (or generate a lock) and rebuild before treating the build as
reproducible.

### CPU torch

PyPI's default Linux `torch` wheel depends on four `nvidia-*` packages. The CPU build is distributed from
`https://download.pytorch.org/whl/cpu`, and `2.14.1+cpu` is not on PyPI. A safe build needs an explicit
CPU install step and a constraint that prevents a later `pip install -r requirements.txt` from replacing
it with the CUDA wheel. Validate the exact command in a clean build before changing the Render build
command.

---

## 4. Options to fix memory and cold start

These are design options; none was implemented in this audit.

**Fastest path to a safe release**

1. Move the service to an instance with at least 1 GB of RAM (Standard/2 GB gives headroom).
2. Ship the MiniLM model with the deployment (vendor the 88 MB model or populate a cache during the
   build) and load it with local-files-only behavior so runtime never depends on Hugging Face.
3. Warm the model and SHAP explainer before declaring readiness, or expose `/ready` and keep `/health`
   as liveness. Budget the warm-up time explicitly.
4. Measure production RSS and request latency, then set the frontend timeout above the measured warm
   latency with margin.

**Lower-memory path**

Replace `sentence-transformers`/torch with a lighter embedding runtime (for example an ONNX MiniLM
model served by `onnxruntime`) or precompute researcher embeddings. This removes the 442 MB torch
import but is a code and model-format change that needs its own design, tests, and rollback plan.

Do not attempt to squeeze the current torch stack into 512 MB; the import alone is 442 MB locally, and
the Linux CUDA build is heavier.

---

## 5. Exact manual Render steps

Perform these in the Render dashboard. They change production and were **not** performed here.

1. Open the `researchtwin-api` service → **Settings → Build & Deploy**. Confirm:
   - Root Directory: `backend`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health Check Path: `/health`
2. Open **Environment**. Confirm the names and non-secret values only:
   - `PYTHON_VERSION` = `3.11.11`
   - `DATABASE_URL` = your PostgreSQL URL (do not paste it into logs or this document)
   - `FRONTEND_ORIGINS` = `https://starlit-empanada-a323e3.netlify.app` (comma-separated if more origins
     are needed; no trailing slash)
3. Open **Settings → Instance Type**. Confirm the memory. If it is 512 MB, upgrade to at least 1 GB
   (Standard/2 GB preferred) before testing the recommendation endpoint again.
4. Decide and implement the model strategy from §4:
   - vendor the model, or
   - add a build step that downloads it into a path included in the deploy, and
   - set the corresponding `HF_HOME`/cache environment variable and local-files-only behavior.
5. If using CPU torch, add the CPU install step and a constraints file so the CUDA wheel is never
   selected. Rebuild and check the build log for the torch wheel variant.
6. Commit and push the release revision (requires your approval; not done). Then use **Manual Deploy →
   Deploy latest commit** and record the deployed SHA from the deploy log.
7. After deploy, verify from outside Render:
   - `GET /health` returns 200
   - `GET /researchers/` returns 30 rows
   - `POST /recommendations/researchers` returns 200 in under the frontend timeout
   - Render logs show no OOM, traceback, or Hugging Face download errors
8. Only then consider hardening items: auth for write/import/delete, rate limiting, sanitized error
   responses, disabled docs, reduced CORS methods, and a `/ready` probe.
9. Confirm the database provider's backup/PITR policy and test that data survives a redeploy. Do not
   run `POST /researchers/import` against production; it is not idempotent.

## 6. Exact manual Netlify steps

1. Open the site → **Site configuration → Build & deploy → Build settings**. Confirm the publish
   directory is `frontend` (also declared in `netlify.toml`).
2. Open **Site configuration → Access & security → Edge Access** (the 401 redirect points at
   `app.netlify.com/edge-access?domain=...`). Decide:
   - Public launch: remove the access rule for this domain, save, and republish.
   - Private site: keep the rule, document who has access, and verify the authenticated journey.
3. Confirm the deploy is from the intended commit and trigger a deploy if the frontend was changed.
4. After publishing, open `https://starlit-empanada-a323e3.netlify.app/researchtwin.html` and verify:
   - the page loads without the 401 redirect
   - the browser console has no CORS or JavaScript errors
   - a recommendation request returns 200 and renders results
   - a second request is served from a warm backend within the timeout
5. If a custom domain is added, update `FRONTEND_ORIGINS` on Render at the same time.

## 7. Rollback considerations

**Render**

- Roll back with **Deploys → previous successful deploy → Rollback** (or redeploy the previous commit).
- This release contains no schema migrations; `create_all` only creates missing tables. Rolling back
  code is schema-safe for the current single-table model.
- Revert code and the model artifact together if the model path or feature order changes. The bundle
  validator rejects an incompatible feature order, so a mismatch fails requests rather than silently
  mis-scoring.
- If the rollback target used different dependency pins, rebuild rather than reusing a cached build.

**Netlify**

- Use **Deploys → previous published deploy → Publish deploy**. Static rollback is immediate.
- Keep the previous `frontend-config.js` API URL compatible with the backend revision you roll back to.

**Database**

- Take a provider snapshot or `pg_dump` before any production write, import, or migration. Obtain
  approval before changing production data.
- Do not run the import endpoint in production; a repeat import was verified to duplicate records
  (30 → 60).
- No destructive reset, drop, or seed command should be part of the release.

**Verification after rollback**

Run the same three checks: `/health` 200, `/researchers/` count as expected, one recommendation POST
200 within the timeout. Then repeat one browser journey once the Netlify gate allows it.

## 8. Items not verified

- Render dashboard values (root, build, start, health, plan, disk) versus `render.yaml`.
- The actual production Python interpreter and installed wheel variants.
- The deployed commit SHA.
- Render logs and the root cause of the 500 responses.
- The production database engine, identity, backup policy, and persistence across deploys.
- The live frontend journey, because every path is 401-gated.
- A clean Render build from the current requirements, including build time and image size.
- Browser-observed CORS (only the preflight was tested from the command line).

## 9. Reproduction commands

```bash
# Production read-only probes
curl -sS -m 20 https://researchtwin-api.onrender.com/health
curl -sS -m 20 https://researchtwin-api.onrender.com/researchers/
curl -sS -m 20 -i -X OPTIONS https://researchtwin-api.onrender.com/recommendations/researchers \
  -H 'Origin: https://starlit-empanada-a323e3.netlify.app' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
curl -sS -m 300 -X POST https://researchtwin-api.onrender.com/recommendations/researchers \
  -H 'Content-Type: application/json' \
  -d '{"research_areas":"machine learning","expertise":"deep learning","skills":"python, pytorch","projects":"image classification","publications":"","top_k":3}'

# Local suite and environment consistency
cd C:/Users/Venkatesh/ResearchTwin/backend
C:/Users/Venkatesh/researchtwin-venv311/Scripts/python.exe -m pytest -q
C:/Users/Venkatesh/researchtwin-venv311/Scripts/python.exe -m pip check

# Local production-like request with a temporary database copy
# The harness copies backend/researchtwin.db to %TEMP%, sets DATABASE_URL to the copy,
# and makes no repo changes. Use a separate HF_HOME to simulate a cold cache.
HF_HOME="$TEMP/rt-hf-cold" PYTHONUNBUFFERED=1 \
  C:/Users/Venkatesh/researchtwin-venv311/Scripts/python.exe "$TEMP/rt-prod-repro.py"
```

The harness reported: app import 162.5 MB, `sentence_transformers` import 442.0 MB, final 653.2 MB,
peak 658.5 MB, warm request 8.46s, cold request 136.55s.

## 10. Files changed in this audit

- Added [PRODUCTION_RELEASE_CHECKLIST.md](file:///C:/Users/Venkatesh/ResearchTwin/PRODUCTION_RELEASE_CHECKLIST.md).
- No application, deployment, or configuration source was modified.
- No files were staged, committed, pushed, or deployed.
- Test-created Hugging Face artifacts (`backend/hub` cache, 88 MB, and a `backend/xet` log directory)
  were removed.
- Temporary test artifacts remain outside the repository under `%TEMP%`.

## 11. Release sign-off

Do not check these until the evidence exists.

- [ ] P0-1: production `POST /recommendations/researchers` returns 200 within the agreed timeout
- [ ] P0-2: release commit pushed and deployed; deployed SHA recorded
- [ ] P0-3: Netlify access decision made and the public/private journey verified
- [ ] P1-1: instance memory confirmed and production RSS measured below the limit
- [ ] P1-2: cold start removed or bounded below the frontend timeout
- [ ] P1-3: transitive pins and CPU torch build verified in a clean Render build
- [ ] P1-4: write/import/delete protected; rate and input limits in place
- [ ] P1-5: readiness reflects model/semantic availability; health path chosen intentionally
- [ ] P2: error responses sanitized; docs access decided; CORS methods reviewed
- [ ] Database: backup policy confirmed and persistence tested across a redeploy
- [ ] Browser: public desktop and mobile journey passes against production
- [ ] Rollback: previous Render and Netlify deploys identified and the rollback rehearsed

---

## Addendum — authentication release items (2026-10-28)

Added with the Phase B/C implementation. **None of these are deployed.**

- [ ] Set `AUTH_SESSION_TTL_SECONDS` deliberately (default 12 hours). No new
      secret is required: session tokens are random and only their SHA-256
      digests are stored.
- [ ] Decide whether public self-registration is acceptable for the demo, or
      gate `POST /auth/register` behind an invite/admin flow. Anyone who can
      reach the API can currently create a student or faculty account.
- [ ] Protect `POST /researchers/`, `PUT/DELETE /researchers/{id}`, and
      `POST /researchers/import`. They are still public and destructive.
- [x] Wire the frontend to `/auth/*` and `/students/me/recommendations`
      (completed locally in Phase D; not deployed). The legacy
      `POST /recommendations/researchers` still needs to be protected or retired.
- [ ] Set `FRONTEND_ORIGINS` to the deployed site origin so the browser can call
      the API; verify CORS preflight for `Authorization` and `Content-Type`.
- [ ] Confirm the deployed frontend ships `api-client.js` and that the browser
      token remains in `sessionStorage`. Bearer tokens in web storage are
      readable by any script on the origin; this is acceptable for the demo but
      is not equivalent to HttpOnly secure cookies and should be revisited for
      production. No passwords are stored client-side.
- [ ] Add login and recommendation rate limiting before exposing the service.
- [ ] Add session cleanup for expired/revoked rows, or accept unbounded growth
      in `auth_sessions` for the demo.
- [ ] Add password reset/email verification only if the demo requires it; do not
      claim institutional SSO.
- [ ] Re-run production probes after any deploy: `/ready` must report `ready`;
      register/login/profile/recommendation flows must pass with a temporary
      account.
- [ ] Confirm the new tables were created without altering `researchers` on the
      production database, and take a backup first.

Production blockers from the sections above remain open. Local suite:
**133 passed** in the pinned Python 3.11 environment.

## Phase E current checklist and policy (2026-10-28)

The preceding audit table and checklist items are a historical Phase D snapshot.
The current local code and final tests establish:

- [x] Researcher create/update/delete require `admin`.
- [x] Researcher CSV import requires `admin`; source type/size/schema/rows are
      validated before a single transaction.
- [x] Public researcher read/search behavior remains available.
- [x] Legacy `POST /recommendations/researchers` remains for compatibility,
      requires a student token, uses only the saved profile, and is deprecated.
- [x] Registration, login, and recommendations have configurable 429 limits;
      limits use atomic database counters and return `Retry-After`.
- [x] Render configuration requires shared PostgreSQL for globally shared
      counters, a generated `RATE_LIMIT_HASH_SECRET`, and uses `/ready` for its
      health check. Readiness fails if the secret or required DB dialect is
      missing.
- [x] API request body capped at 65,536 bytes. Authentication/profile tests
      verify password hashing, token hashing, revocation, expiry, ownership,
      role walls, and rejected ownership/role payload fields.
- [x] Frontend API-client compatibility: public directory request and
      authenticated `/students/me/recommendations` path pass Node tests.

Final local commands:

```text
backend: C:\Users\Venkatesh\researchtwin-venv311\Scripts\python.exe -m pytest -q
        → 156 passed, 2 warnings (Python 3.11.9)
root:    node --test tests/frontend/api-client.test.cjs
        → 13 passed, 0 failed
```

### Phase E release blockers / unverified items

- [ ] Set a generated random `RATE_LIMIT_HASH_SECRET` (at least 32 bytes) in
      the actual Render service. The value is not in the repository and was not
      inspected.
- [ ] Verify `DATABASE_URL` is the shared PostgreSQL instance used by every
      Render worker/instance. SQLite is rejected in the Render-required shared
      mode. No live Render environment was inspected.
- [ ] Decide whether researcher maintenance is needed. If so, a trusted
      operator must provision an `admin` account through a secure, audited
      out-of-band process. There is no in-app bootstrap or default password.
- [ ] Deploy through the approved process and verify `/ready`, auth, profile
      isolation, all 429 paths, directory reads, and both recommendation routes
      against the live app. No live probe or deployment occurred in Phase E.
- [ ] Accept or plan mitigation for the `sessionStorage` XSS token exposure.
      Cookie auth requires coordinated credentialed CORS and CSRF protections;
      no frontend change is needed for this phase.
- [ ] Plan cleanup/retention for expired and revoked `auth_sessions` and
      `rate_limit_counters`; limiter counters are pruned after seven days.

**Exact next phase: Phase F — Production configuration and release
verification**, covering the Render secret and shared database, any secure
out-of-band administrator provisioning, deployment, and live verification.

## Phase G current checklist and policy (2026-10-31)

Phase G added product workflows, not deployment changes. The Phase E checklist
above remains the current deployment policy; this section records what a release
now has to account for.

Locally verified (pinned Python 3.11 suite plus the browser journey):

- [x] Readiness roadmap API: authenticated student only, derived from the saved
      profile, full structured plan (matched skills, gaps, priority, reason,
      milestones, mini-project, completion criteria).
- [x] The empty-skill defect: a student with no skills listed gets
      `student_skills_provided: false`, zero claimed gaps and guidance instead
      of "missing every researcher skill".
- [x] Milestone progress persisted server-side, owned by student + researcher,
      validated against the recomputed roadmap, reopenable, idempotent via the
      `uq_roadmap_progress_milestone` constraint.
- [x] Collaboration lifecycle `pending → accepted|rejected` with an optional
      faculty reply, per-student isolation, and claim-based faculty ownership.
- [x] Faculty inbox never exposes the student's account email.
- [x] Researcher directory search/filtering over the existing `researchers`
      table with `%` and `_` escaped; no duplicate faculty model.
- [x] Recommendation engine, scores, component breakdown and explanations
      unchanged; the legacy roadmap route is authenticated and deprecated.
- [x] Three new tables created by `create_all` with no `ALTER`, no drop, no
      reseed, no migration run, and no production data touched.

Final local commands:

```text
backend: C:\Users\Venkatesh\researchtwin-venv311\Scripts\python.exe -m pytest -q
        → 189 passed, 2 warnings (Python 3.11.9)
root:    node --test tests/frontend/api-client.test.cjs
        → 19 passed, 0 failed
```

### Phase G release blockers / unverified items

- [ ] The seven new routes must be checked against the live API after any
      deploy: `GET/PUT` roadmap, `POST/GET` student collaboration requests,
      `GET/PUT` faculty link, `GET` faculty inbox, `PUT` faculty decision.
      Confirm CORS allows the Netlify origin for all of them, including `PUT`.
- [ ] Confirm the three new tables are created on the production PostgreSQL
      database at first start, without altering `researchers`. Back up the
      database first; do not hand-create them.
- [ ] Operational dependency: faculty can only see requests after claiming a
      directory record, and claiming depends on the imported directory being
      populated and recognisable to the right person. A fresh deployment has no
      in-app admin path to seed or maintain researchers, so an operator must
      provision one out of band before the collaboration workflow is usable.
- [ ] `POST /students/me/collaboration-requests` reuses the recommendation
      limiter budget (8 per IP+student per 5 minutes). Decide whether that is
      the intended product limit or needs its own window in Render.
- [ ] Orphaned `roadmap_progress` rows: editing a researcher's `skills` text can
      retire completed milestones silently, because progress is keyed by
      `(skill, milestone_index)`. No retention or reconciliation job exists.
- [ ] No notification when a faculty member replies; the student has to open
      "My Requests" to learn the outcome.
- [ ] Mobile rendering of the roadmap and inbox panels is unverified — the same
      headless-viewport limitation as Phase D. Desktop only was checked.
- [ ] `sessionStorage` XSS token exposure is unchanged by Phase G.

Phase F production configuration and live verification still comes first: the
deployment was not probed or published during this task, and nothing was
staged, committed, pushed, or deployed.

## Phase 4 — final development hardening (2026-11-01)

### Current source configuration review

- `render.yaml` declares the backend root, Python 3.11.11, `pip install -r requirements.txt`, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, readiness path `/ready`, externally supplied `DATABASE_URL`, `FRONTEND_ORIGINS`, rate-limit secret placeholder, shared-PostgreSQL limiter mode, body limit, and numeric limiter settings. It does not declare a PostgreSQL database, service plan, persistent disk, or migration command.
- `netlify.toml` only sets `publish = "frontend"`. `frontend/frontend-config.js` defaults to the current Render API URL for non-local hosts; no Netlify build-time substitution or response security headers/CSP are configured in the repository.
- The active recommendation service loads `backend/models/researchtwin_logistic_v2_7features.joblib`; Git reports that file as untracked. A clean checkout containing only tracked source will not include the active artifact unless a future approved release packages it.
- `create_all()` runs at application import/start. No Alembic configuration, revisions, or dependency were found.
- Rate-limit counters are database-backed and coordinate across instances only when all use the same PostgreSQL database. Render config trusts `CF-Connecting-IP`; actual proxy behavior is unverified.
- The browser bearer token remains in `sessionStorage`, so same-origin script execution can read it. Cookie migration was not attempted.

### Final regression results

All Phase 4 tests ran locally. No live service or production database was contacted.

| Suite | Exact command / environment | Result |
|---|---|---|
| Backend (canonical Python 3.11) | From `backend/`: `C:\Users\Venkatesh\researchtwin-venv311\Scripts\python.exe -m pytest -q` | **228 passed**, 2 upstream deprecation warnings, 57.91 s. Warnings are Starlette's `httpx` TestClient integration and AnyIO's `BlockingPortal` alias. |
| Frontend API-client/config/dashboard | From root: `node --test tests/frontend/api-client.test.cjs tests/frontend/config.test.cjs tests/frontend/dashboard.test.cjs` | **79 passed, 0 failed**, 264 ms. |
| Browser E2E | `node tests/e2e/researchtwin.phase3.e2e.cjs`; local API on `127.0.0.1:8000`, static frontend via `npx --yes serve frontend --listen 5500 --no-clipboard`, new temporary SQLite DB under `%TEMP%`, test-only admin created by the documented CLI, local rate limits raised to 100 for this run. | **PASS — 12 journey groups.** Imported 30 bundled researchers; produced 10 finite, descending recommendations. Browser checked all seven feature scores and explanations. Included invalid registration, network failure, delayed roadmap refresh, concurrent milestone locking/persistence, collaboration accept/reject, expired token, and logout revocation. |
| Fresh-install environment recheck | Existing Phase 3 temporary Python 3.11.9 environment: `C:\Users\Venkatesh\AppData\Local\Temp\ResearchTwin-FreshInstall-b13e851b000e4ecfa909890e27fd665b\Scripts\python.exe -m pytest -q` and `-m pip check` | **228 passed**, 2 same deprecation warnings, 48.95 s; `pip check`: no broken requirements. This revalidated the previously created fresh environment; dependencies were not reinstalled during Phase 4. |
| Model | Active file loaded in Python 3.11.9 / scikit-learn 1.7.2; model inspection plus E2E recommendations. | **Pass locally:** 2,309 bytes; seven ordered features; no load warning; finite ranked scores and corresponding explanations. The file remains untracked, so a tracked-source clean build is still blocked. |
| `git diff --check` | Project root | **Existing issue:** `index.html:164` has trailing whitespace. Git also reports line-ending normalization warnings for pre-existing dirty files. No new whitespace issue was reported in the updated documentation. |

Browser output contained three expected console messages: a failed-resource message from the deliberate network-failure journey, HTTP 409 for the duplicate collaboration request, and HTTP 401 for the expired session. The E2E report marked all as expected; there were no unexpected browser console errors or page errors. No screenshot/trace was produced because no journey failed.

Fresh-install limitation: this Phase 4 run reused the separate temporary environment created and installed during Phase 3; it reran dependency consistency and the complete backend suite, but did not create another environment or reinstall packages.

### Production gates

Resolve active model artifact packaging; verify durable PostgreSQL, backups and restore; set and verify the HMAC secret and exact CORS origin; confirm the trusted client-IP header boundary; measure runtime memory/cold start and dependency resolution; add Alembic before schema evolution; and review frontend security headers and token exposure. See `PRODUCTION_CONFIGURATION_CHECKLIST.md` and `SECURITY_ASSESSMENT.md`. No live application verification is claimed.
