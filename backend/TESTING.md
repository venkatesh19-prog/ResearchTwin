# Backend testing

## Latest local verification — Phase 5H (2026-11-03)

Canonical Python 3.11 run from `backend/`:

```powershell
C:\Users\Venkatesh\researchtwin-venv311\Scripts\python.exe -m pytest -q
```

Result: **250 passed, 2 upstream deprecation warnings** in 48.66 seconds on
Windows (CPython 3.11.9). The WSL Linux environment (CPython 3.11.11, matching
Render's configured `PYTHON_VERSION`) passed the same **250 tests in 28.30 seconds**, and
`pip check` reported no broken requirements. The warnings are from Starlette's
`httpx` TestClient integration and AnyIO's `BlockingPortal` alias.

The frontend suite (`npm test -- --run`) passed **81 tests**. The real-browser
Playwright suite passed **12 journey groups** on a separate temporary SQLite
database. See `../PRODUCTION_RELEASE_CHECKLIST.md` for the browser setup and
expected console messages. Historical Phase E/G counts below are snapshots from
those phases, not the latest totals.

All commands below run from `backend/`.

## Requirements

Runtime dependencies: `requirements.txt`.
Test-only dependencies: `requirements-dev.txt`.

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
```

Render is configured for Python 3.11.11 (see `../render.yaml`) with the pinned
versions in `requirements.txt` (scikit-learn 1.7.2, shap 0.51.0, pandas 2.3.3).
The model artifact was
trained with scikit-learn 1.7.2, so pinned-environment checks only execute
when that version is installed; elsewhere they are reported as skipped.

## Run the suite

```bash
.venv/Scripts/python.exe -m compileall -q app tests
.venv/Scripts/python.exe -m pytest
```

`pytest.ini` restricts collection to `tests/`, so the legacy top-level
scripts (`test_semantic_matching.py`, `model_comparison.py`, ...) are not
collected. Tests are isolated:

- `tests/conftest.py` points `DATABASE_URL` at a throwaway SQLite file in
  the system temp directory *before* importing `app`, so
  `backend/researchtwin.db` is never touched.
- Semantic matching is stubbed (`patch_semantic`), so no embedding model is
  loaded and ONNX Runtime is not initialised.
- `tests/test_integration_real_model.py` loads the shipped joblib bundle and
  `data/matching_topk_labeled.csv` and compares predictions against fixed
  reference probabilities.
- `tests/test_auth.py` covers registration, duplicate/weak input, login,
  token hashing, logout revocation, and expiry.
- `tests/test_profiles.py` covers student/faculty profile persistence,
  completion scoring, cross-account isolation, role denial, and
  recommendations driven by the saved profile.
- `tests/test_database_reliability.py` proves `create_all` is idempotent,
  that a failed request rolls back and closes its session, that an
  unavailable database yields 503s (and an unhealthy `/health`), and that
  recommendation ids and explanation features match database rows.

Password hashing is deliberately slow (PBKDF2-HMAC-SHA256, 600,000
iterations). The earlier Phase D baseline was 133 passed, 2 warnings; the
current Phase E full suite result is recorded below.

## Phase E API security verification (2026-10-28)

The final canonical run used Python 3.11.9 and the pinned production libraries
(FastAPI 0.141.1, SQLAlchemy 2.0.53, Pydantic 2.13.5, NumPy 2.2.6,
pandas 2.3.3, scikit-learn 1.7.2, joblib 1.6.0, and SHAP 0.51.0):

```powershell
C:\Users\Venkatesh\researchtwin-venv311\Scripts\python.exe -m pytest -q
```

Final result: **156 passed, 2 warnings**. The warnings are upstream
deprecations for Starlette's `httpx` TestClient integration and AnyIO's
`BlockingPortal` alias. The final run took 24.04 seconds. Tests cover
admin-only researcher writes/import, legacy recommendation authorization and
saved-profile ownership, authentication and recommendation limits, fail-closed
limiter configuration, oversized requests,
CSV validation/atomicity, expiry/revocation, and profile isolation.

## Isolated production-equivalent environment (Python 3.11)

```bash
py -3.11 -m venv C:/Users/<you>/researchtwin-venv311
C:/Users/<you>/researchtwin-venv311/Scripts/python.exe -m pip install --upgrade pip
C:/Users/<you>/researchtwin-venv311/Scripts/python.exe -m pip install \
  -r requirements.txt -c constraints.txt -r requirements-dev.txt
C:/Users/<you>/researchtwin-venv311/Scripts/python.exe scripts/fetch_embedding_model.py
C:/Users/<you>/researchtwin-venv311/Scripts/python.exe -m pytest
```

`fetch_embedding_model.py` downloads the SHA-256-verified ONNX MiniLM graph
used by semantic matching; it is not committed to the repository.

## Live API check

1. Copy the database to a unique temporary filename so the original stays
   untouched and an older temporary copy is never overwritten:

   ```bash
   python -c "import shutil, os, tempfile, uuid; target=os.path.join(tempfile.gettempdir(), 'rt_live_'+uuid.uuid4().hex+'.db'); shutil.copy2('researchtwin.db', target); print(target)"
   ```

2. Start the server against the copy:

   ```bash
   DATABASE_URL="sqlite:///C:/Users/<you>/AppData/Local/Temp/rt_live.db" \
     .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
   ```

3. Check `GET /health`, register or log in as a student, save a profile through
   `PUT /students/me/profile`, then request recommendations through
   `POST /students/me/recommendations` with that token. The compatibility route
   `POST /recommendations/researchers` now requires student authentication and
   uses the saved profile; submitted profile fields are ignored.

The first recommendation request lazily loads the ONNX `all-MiniLM-L6-v2`
session. With the 30-row directory, WSL Linux (CPython 3.11.11) measured a
**412.2 MB** peak for the service workflow and **414.9–421.4 MB** through the
HTTP route; warm requests took 0.28–0.33 s and memory stayed flat afterwards.
These are **WSL Linux measurements, not Render measurements**, and Render Free
compatibility has not been measured on Render. Earlier torch-based runs peaked
at ~644 MB, which exceeded the 512 MB Render Free limit.

## HTTP behaviour

| Situation | Status |
|---|---|
| `top_k` outside 1..10 | 422 |
| Malformed or missing JSON body | 422 |
| No researchers in the database | 200 with `recommendations: []` |
| Model bundle missing, corrupt, or feature order mismatch | 503 |
| Embedding model load/encode failure | 503 |
| Database unreachable while handling any DB-backed route | 503 `{"detail":"Database unavailable"}` |
| `GET /health` while the database is unreachable | 503 `{"status":"unhealthy"}` |
| Database unreachable while `app.main` is imported (schema init) | process fails to start (fail-fast) |
| Protected route without a token, or with an expired/revoked token | 401 |
| Student calling a faculty-only route, or faculty calling a student-only route | 403 |
| Registration with an email that already exists | 409 |
| Profile update containing unknown fields such as `user_id` | 422 |
| Recommendations requested before a student profile is saved | 400 |
| `GET /ready` or `/readiness` when the DB or model artifact is unavailable | 503 `{"status":"not_ready"}` |
| Researcher create/update/delete/import without a token | 401 |
| Researcher create/update/delete/import as student or faculty | 403 |
| Legacy `POST /recommendations/researchers` without token / as faculty | 401 / 403 |
| Oversized request body | 413 `{"detail":"Request body is too large"}` |
| Auth/recommendation rate limit exceeded | 429 with `Retry-After` |
| Missing/short limiter hash secret | 503; readiness is not ready |
| Render shared-DB mode connected to SQLite | 503 for limiter; readiness is not ready |

### Deployment-only rate-limit settings

The limiter uses atomic database upserts and is shared across instances only
when they use the same PostgreSQL database. Render configuration sets
`RATE_LIMIT_REQUIRE_SHARED_DATABASE=true`,
`RATE_LIMIT_TRUST_CF_CONNECTING_IP=false` (the header is honored only when trust
is enabled *and* the peer matches `RATE_LIMIT_TRUSTED_PROXY_CIDRS`), and limits
of 5 registrations/IP+email per hour, 10 logins/IP+email per 15 minutes, and 8
recommendations/IP+student per 5 minutes. Configure `RATE_LIMIT_HASH_SECRET` in Render with a generated
random secret of at least 32 bytes; it is deliberately not committed. Render's
health check uses `/ready`. Live Render settings were not inspected, so deployed
limiter status remains unverified. Local SQLite tests do not prove
cross-instance coordination.

The frontend still stores only the bearer token in `sessionStorage`, not the
password. Same-origin JavaScript can read it, so XSS remains a token-theft risk.
Cookie migration is deferred until credentialed CORS and CSRF defenses can be
deployed and reviewed together.

`semantic_available` is `false` when a profile contains no text to embed
(student or researcher). The semantic component is then `0.0` by documented
fallback, not because the candidate was judged dissimilar.

## Frontend tests (Node)

The browser API client is a UMD module and can be tested without a DOM:

```bash
cd C:/Users/Venkatesh/ResearchTwin
node --test tests/frontend/api-client.test.cjs
```

Current expected result: **19 passed** (13 through Phase E, six added in the
Phase G addendum). Coverage: login stores only the token,
bearer attachment, 401 clears the session and notifies once without retrying,
403 keeps the session, non-JSON error bodies, timeout abort, profile PUT body,
saved-profile recommendation endpoint/body, logout revocation even when the
request fails, public researcher directory compatibility, registration schema,
and FastAPI validation-detail flattening.

The page itself (`frontend/researchtwin.html`) has no DOM test harness; the
authenticated journey was exercised manually in Chrome against a temporary
database copy. See the Phase D addendum in `PROJECT_COMPLETION_AUDIT.md` for
the flow matrix and the one blocked check (mobile viewport resize).

## Addendum — Phase G roadmap, collaboration and search (2026-10-31)

Suite: **189 passed** in the pinned Python 3.11 environment (was 156 after
Phase E).

```bash
cd C:/Users/Venkatesh/ResearchTwin/backend
C:/Users/Venkatesh/researchtwin-venv311/Scripts/python.exe -m pytest -q
# → 189 passed, 2 warnings in 31.05s   (the two warnings are upstream
#    Starlette/httpx and AnyIO deprecations, not project failures)
```

Focused reproduction:

```bash
C:/Users/Venkatesh/researchtwin-venv311/Scripts/python.exe -m pytest -q \
  tests/test_roadmap_progress.py tests/test_collaboration.py
# → 29 passed in 9.99s
```

### New files

`tests/test_roadmap_progress.py` — 12 tests. Anonymous request `401`, faculty
account `403` on the roadmap route, missing saved profile `400`, unknown
researcher `404`, matched/missing skills derived from the stored profile rather
than the client (`skills="Python, SQL"` against Ada → matched `["python"]`, gaps
`["pytorch","transformers"]`), the blank-skills regression (`student_skills_provided`
is `false`, zero claimed gaps, a guidance message, and the researcher's own
skill list still returned), the full structured plan (priority, per-skill reason,
milestones, mini-project, completion criteria), a generic plan for a skill not in
the researcher record, persistence and re-opening, cross-student and
cross-researcher isolation, `404` for a skill or milestone index that is not in
the recomputed roadmap, and `405` for `POST` on the read route.

`tests/test_collaboration.py` — 17 tests. `201` on a new request, `422` for a
blank message, `404` for an unknown researcher, `409` for a duplicate pending
request, `403` for a student token on faculty routes, per-student isolation,
`401` anonymous, `400` for a faculty member with no linked record, `404`/`409`
on the link route, the faculty inbox showing the student's profile while
asserting `"email" not in record["student"]`, request scoping to the linked
record, `403` when answering a request that belongs to another record, `404` for
an unknown request, accept with a reply, reject without a reply, `403` for a
student attempting a decision, `422` for an invalid decision value, and the
`?status=` filter.

Both files share an autouse fixture that clears `collaboration_requests` and
`faculty_researcher_links` in the test database. Without it, `seeded_db`
recycles researcher ids while a previous test's ownership row survives, and
because `researcher_id` is unique the next faculty test inherits a stale owner —
this was the cause of the first red run, not a product defect.

### Updated files

- `tests/test_imports_and_routes.py` — the seven new route/method pairs are in
  `EXPECTED_ENDPOINTS`, so an accidental deregistration fails the suite.
- `tests/test_recommendations_api.py` — the legacy roadmap route now requires a
  student token, returns `404` for an unknown researcher, emits the
  `Deprecation` header, and ignores client-supplied skill lists.
- `tests/test_acceptance.py` — the legacy roadmap `404` case authenticates first,
  and a faculty account is asserted to get `403`.
- `tests/test_researchers_api.py` — free-text search matches name and
  descriptive fields, and `search="%"` returns no rows because wildcards are
  escaped before the `ILIKE`.

### Frontend

Node tests: **19 passed** (six added in Phase G — roadmap GET path and bearer
header, milestone PUT payload, collaboration POST body, `409` detail surfacing,
`403` keeping the session, and `?status=` passthrough).

```bash
cd C:/Users/Venkatesh/ResearchTwin
node --test tests/frontend/api-client.test.cjs
```

On Windows, pass the explicit file path; the bare-directory form is not reliable
here.

`frontend/researchtwin.html` still has no DOM test harness. The new roadmap
panel, progress checkboxes, request form, "My Requests" list and faculty inbox
were verified in the browser against a temporary copy of
`backend/researchtwin.db`; the repository database was not opened for writing and
no production service was contacted.
