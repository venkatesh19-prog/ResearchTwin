# ResearchTwin — Final Acceptance Report

> **Current update 2026-10-28 (Phase E API security):** the final local backend
> suite passed **156 tests with 2 dependency deprecation warnings**, and the
> frontend API-client suite passed **13/13**. Researcher mutations/import are
> admin-only, the legacy recommendation endpoint is authenticated and uses the
> caller's saved profile, and Render is configured to require database-backed
> limits on shared PostgreSQL. This is local verification only. No live
> production checks, staging, commit, push, or deployment occurred. Production
> remains **NOT ACCEPTED** pending Render configuration and post-deployment
> verification. The acceptance results below are the earlier Phase D snapshot;
> current findings are at the end.

> **Update 2026-10-28 (Phase D frontend integration):** the browser journey is
> now authenticated end to end locally — register/login, session restore,
> student and faculty profile persistence, recommendations from the saved
> profile, directory search, role denial, and logout revocation all passed in a
> real browser against a temporary database. The frontend client tests add
> **12 passed**; the backend suite remains **133 passed**. The production
> verdict below is unchanged: **NOT ACCEPTED**, because the deployed
> recommendation endpoint and Netlify access were not re-verified and nothing
> was deployed.

> **Update 2026-10-28 (local blockers):** Tests 2, 7, and 13 now pass locally.
> `/ready` and `/readiness` exist, error details are sanitized, and the suite is
> **133 passed** (including 25 new auth/profile tests). The verdict below remains
> **NOT ACCEPTED for production** because the deployed recommendation endpoint
> still returns 500 and Netlify Edge Access still returns 401. No deployment was
> performed.

- **Date:** 2026-10-28
- **Project root:** `C:\Users\Venkatesh\ResearchTwin`
- **Live frontend:** https://starlit-empanada-a323e3.netlify.app
- **Live backend:** https://researchtwin-api.onrender.com
- **Verification environment:** Python 3.11.9 at `C:\Users\Venkatesh\researchtwin-venv311`
- **Verdict: NOT ACCEPTED — release blockers remain.**

The next paragraph records the repository state at the time of the earlier Phase D
report; Phase E changes and tests are listed in the current addendum below.

---

## 1. Summary

| # | Acceptance test | Local | Production | Overall |
|---|---|---|---|---|
| 1 | App imports/starts with intended production dependencies | PASS | BLOCKED | BLOCKED |
| 2 | Health and readiness checks | FAIL | FAIL | **FAIL** |
| 3 | Database connects and reads records | PASS | PASS | **PASS** |
| 4 | Valid profile returns requested recommendations | PASS | **FAIL** | **FAIL** |
| 5 | Match scores numeric, finite, ordered | PASS | BLOCKED | BLOCKED |
| 6 | Explanation and skill-gap schema | PASS | BLOCKED | BLOCKED |
| 7 | Invalid requests produce appropriate errors | PASS | **FAIL** | **FAIL** |
| 8 | Empty researcher results handled gracefully | PASS | BLOCKED | BLOCKED |
| 9 | Semantic/model inference edge cases | PASS | BLOCKED | BLOCKED |
| 10 | Frontend submits profile and renders real API response | PASS | BLOCKED | BLOCKED |
| 11 | Loading and error states | PASS | BLOCKED | BLOCKED |
| 12 | CORS for the actual frontend origin | PASS | PASS | **PASS** |
| 13 | No secrets/private DB details exposed | **FAIL** | PARTIAL | **FAIL** |
| 14 | Memory under repeated requests / crash risks | PASS | BLOCKED | BLOCKED |

**Critical blockers**

1. The deployed recommendation endpoint returns **HTTP 500 on every attempt**
   (165.4 s, 149.5 s, 45.5 s) while `/health`, `/`, `/researchers/`, OpenAPI, and
   CORS work. This makes the product's core feature unusable in production.
2. The deployed API cannot answer even an invalid request reliably: `POST` with
   `top_k: 0` timed out after 45 s instead of returning 422.
3. The deployed frontend is still behind **Netlify Edge Access (401)**, so the
   released UI cannot be exercised by an ordinary visitor.
4. No readiness endpoint exists (`/ready` and `/readiness` both 404), locally and
   in production.
5. Error responses echo absolute server paths when the model or import service
   fails locally (`ResearchTwin model not found: C:\...`,
   `Import failed: unable to open database file: C:\...`).

---

## 2. Automated test suite

Command:

```bat
cd C:\Users\Venkatesh\ResearchTwin\backend
C:\Users\Venkatesh\researchtwin-venv311\Scripts\python.exe -m pytest -q
```

Actual result (fresh run):

```text
4 failed, 104 passed, 2 warnings in 2.03s
```

- All **84 pre-existing tests pass**.
- The 4 failures are new acceptance assertions that expose the blockers above:
  - `test_readiness_probe_is_available[/ready]`
  - `test_readiness_probe_is_available[/readiness]`
  - `test_model_failure_detail_does_not_leak_server_path`
  - `test_import_failure_detail_does_not_leak_database_path`
- The 2 warnings are Starlette/httpx deprecation warnings, not failures.

New tests added in `backend/tests/test_acceptance.py` cover: requested result
count, finite/bounded/descending scores, full explanation and skill-gap schema,
DB reads without path leakage, six invalid `top_k` variants plus malformed and
non-JSON bodies, readiness, empty DB, semantic-unavailable behavior, CORS for the
real Netlify origin (allowed and unlisted origins), and error-detail leakage.
`backend/tests/conftest.py` now registers
`https://starlit-empanada-a323e3.netlify.app` in `FRONTEND_ORIGINS` before the app
is imported so the CORS test exercises the deployed origin.

---

## 3. Production probes

Read-only probes only. No production writes, no imports, no environment changes.

| Probe | Result |
|---|---|
| `GET /health` (cold) | No response, 61.9 s timeout |
| `GET /` (cold) | No response, 30.2 s timeout |
| `GET /ready`, `/readiness` (cold) | No response, 30.4 s timeout |
| `GET /health` (warm) | **200** `{"status":"healthy"}` in 0.69 s |
| `GET /` (warm) | **200** success JSON in 0.40 s |
| `GET /ready` / `/readiness` (warm) | **404** `{"detail":"Not Found"}` |
| `GET /researchers/` | **200**, 30 rows, 3.08 s, no DB path in payload |
| `GET /openapi.json` | **200**, 8 paths, matches local route set |
| `GET /docs` | **200** (public API docs) |
| `OPTIONS /recommendations/researchers` (Origin: Netlify) | **200**, allow-origin echoes exact origin |
| `GET /health` with `Origin: https://attacker.example` | No allow-origin echo |
| `POST /recommendations/researchers` `top_k: 3` | **500** in 165.4 s, 149.5 s, and 45.5 s |
| `POST /recommendations/researchers` `top_k: 0` | No response, 45.2 s timeout (expected 422) |
| `GET` Netlify site | **401** Login Redirect (Edge Access) |
| `GET` Netlify `frontend-config.js` | **401** Login Redirect |

The 500 bodies are the generic `Internal Server Error` text, so no server path is
exposed by that path in production. The fault is not visible without Render logs.
Three independent attempts failed, so this is not a single flaky request.

---

## 4. Local end-to-end verification

An isolated stack was run entirely under `%TEMP%`:

- `8010` — current backend with a **copy** of `backend/researchtwin.db` (30 rows)
- `8011` — backend with an empty SQLite database
- `8012` — stub API returning 503 for the error-state test
- `5500` — a temporary copy of the current `frontend/` with only `API_BASE`
  overridden to the local backend

No repository database was written to, and no repository frontend file was changed.

### Local API results

| Check | Result |
|---|---|
| `/health` | 200 `{"status":"healthy"}` |
| `/` | 200 success |
| `/researchers/` | 200, 30 unique IDs, no DB path |
| `top_k=5` | 5 results, scores `[0.9676, 0.6104, 0.4997, 0.4213, 0.4064]` |
| `top_k=3` | 3 results, same top three in the same order |
| First match | Dr. Anil Kumar; matched `python, pytorch, tensorflow`; gap `opencv` |
| Explanation | 8 contributions, finite SHAP and feature values, magnitude-sorted |
| Invalid `top_k` 0 / 51 / `"five"` | 422 for each |
| Malformed JSON | 422 |
| Empty database | 200 with `recommendations: []` |
| CORS preflight | 200, exact Netlify origin, methods `GET, POST, PUT, DELETE, OPTIONS`, credentials `null` |
| Unlisted origin | Not echoed |
| Repeated requests | 6 requests, RSS 645.2 → 646.4 MB (+1.2 MB), 0.269–0.312 s each |

### Local browser results (Chrome 156 headless, CDP)

| Flow | Result |
|---|---|
| Submit profile | Exactly 1 POST, status 200, payload expertise `Computer Vision` |
| Loading state | `Running researcher matching…` visible immediately after submit |
| Rendering | 5 cards; displayed `96.8% model score` equals API `0.9676` |
| Skill tags | `✓ python`, `✓ pytorch`, `✓ tensorflow`, `＋ opencv` |
| Explanation | Summary rendered; top-5 SHAP rows match the API's top-5 contributions |
| Console / page errors | None |
| Empty API result | `No researchers found. Check that researcher records are available.` |
| 503 backend | `Could not load recommendations: API 503: {"detail": "stub service unavailable"}…` |
| Mobile 390 px | No horizontal overflow, card 358 px wide, badge and nav fully visible |

---

## 5. Test-by-test detail

### Test 1 — App imports/starts with intended production dependencies

- **Command:** Python 3.11.9 venv; `import app.main`; package version dump;
  `pip check`.
- **Actual:** Import OK, 8 OpenAPI paths, `pip check` reports no broken
  requirements. Versions: FastAPI 0.141.1, Starlette 1.6.0, Pydantic 2.13.5,
  SQLAlchemy 2.0.53, uvicorn 0.53.0, scikit-learn 1.7.2, joblib 1.6.0, SHAP 0.51.0,
  sentence-transformers 6.1.0, torch 2.14.1+cpu, transformers 5.21.0,
  pandas 2.3.3, numpy 2.2.6, psycopg 3.3.6.
- **Status:** PASS locally; **BLOCKED in production.** The Render build log,
  installed versions, and actual Python runtime cannot be read without dashboard
  access. `requirements.txt` is largely unpinned, so the deployed set is not
  guaranteed to match the verified set.
- **Evidence:** Import/version output above; `render.yaml` sets
  `PYTHON_VERSION=3.11.11` while local verification used 3.11.9.
- **Corrective action:** Pin all production dependencies to the verified versions,
  redeploy, then confirm the deployed runtime via Render logs. Re-run this test.

### Test 2 — Health and readiness checks

- **Command:** Local and production `GET /health`, `GET /ready`, `GET /readiness`.
- **Actual:** Health 200 locally and 200 warm in production (it timed out cold);
  readiness 404 in both environments.
- **Status:** **FAIL.**
- **Evidence:** Production `/ready` → `404 {"detail":"Not Found"}`; same locally.
  Local `/health` → `{"status":"healthy"}`. Health does perform a DB `SELECT 1`,
  so it doubles as a dependency check, but there is no distinct readiness probe
  for deployment gating.
- **Corrective action:** Add `GET /ready` returning 200 only when the DB and model
  artifact are usable, or explicitly document `/health` as the readiness probe and
  remove the ambiguity. Add the matching acceptance test (already written; it will
  turn green once the endpoint exists).

### Test 3 — Database connects and reads records

- **Command:** `GET /researchers/` against a copied local DB and production.
- **Actual:** 200 in both; 30 rows; unique IDs; names match; no DB path or
  `sqlite:///` string in the payload.
- **Status:** **PASS.**
- **Evidence:** Local 30 rows in 0.0 s; production 30 rows in 3.08 s; first row
  `Dr. Anil Kumar`.
- **Corrective action:** None.

### Test 4 — Valid profile returns requested number of recommendations

- **Command:** `POST /recommendations/researchers` with the documented profile,
  `top_k=5` and `top_k=3`, locally and in production.
- **Actual:** Local returns exactly 5 and 3. Production returns **500** every
  time.
- **Status:** **FAIL** (production); PASS locally.
- **Evidence:** Production 500 after 165.4 s, 149.5 s, 45.5 s; body
  `Internal Server Error`. Local 5/5 and 3/3.
- **Corrective action:** Inspect Render logs for the unhandled exception; reproduce
  the deployed startup locally with the same dependency set. The leading hypothesis
  is process memory exhaustion during model/semantic initialization (local RSS is
  ~645 MB; Render instance limit is not visible in `render.yaml`), but this is not
  proven until the logs are read. Do not treat the hypothesis as the diagnosis.

### Test 5 — Match scores numeric, finite, correctly ordered

- **Command:** New acceptance test plus live local requests.
- **Actual:** Local scores are numeric, finite, within [0, 1], and strictly
  non-increasing: `[0.9676, 0.6104, 0.4997, 0.4213, 0.4064]`; all 8 component
  scores finite and within tolerance of [0, 1].
- **Status:** PASS locally; **BLOCKED in production** because no recommendation
  response was produced.
- **Corrective action:** Fix Test 4, then re-run this check against production.

### Test 6 — Explanations and skill-gap data follow the documented schema

- **Command:** New acceptance tests on the real model artifact with semantic
  matching stubbed deterministically, plus live local API.
- **Actual:** Every recommendation has `summary`, `why_recommended`, 8 unique
  contributions with `feature`, finite `shap_value`, finite `feature_value`, and
  magnitude-sorted contributions. `matched_skills` and `skill_gap` are sorted,
  disjoint, and together equal the researcher's normalized skill set. For the
  fixture researcher Ada Lovelace: matched `["python","pytorch","transformers"]`,
  gap `[]`.
- **Status:** PASS locally; **BLOCKED in production.**
- **Evidence:** `tests/test_acceptance.py::test_explanation_schema_is_complete_and_numeric`
  and `::test_skill_gap_schema_matches_researcher_record` pass. Live response
  first match: matched `python, pytorch, tensorflow`, gap `opencv`.
- **Corrective action:** None for schema; re-verify after the production fix.

### Test 7 — Invalid requests produce appropriate errors

- **Command:** Local and production POSTs with `top_k` 0, 51, `"five"`, `2.5`,
  `null`; malformed JSON; non-JSON body; unknown roadmap researcher.
- **Actual:** Locally 422 for all invalid bodies, 404 for the unknown roadmap
  researcher. Production `top_k: 0` timed out after 45 s.
- **Status:** **FAIL** in production; PASS locally.
- **Evidence:** Local `invalid_requests` all 422; production invalid request
  `status: null, seconds: 45.16`.
- **Corrective action:** Fix the production instability first; then re-test that
  validation runs before any model work and returns 422 quickly.

### Test 8 — Empty researcher results handled gracefully

- **Command:** Local backend on an empty SQLite DB; browser flow against it.
- **Actual:** API 200 with `recommendations: []`; UI shows
  `No researchers found. Check that researcher records are available.` No error.
- **Status:** PASS locally; **BLOCKED in production** (cannot create an empty
  production DB without a destructive data change, which was not authorized).
- **Evidence:** `empty_database` local check and `empty_results_state` browser
  flow, both passing.
- **Corrective action:** None locally. Production behavior can be unit-verified
  from the same code path; no live empty-DB test is possible without approval.

### Test 9 — Semantic matching/model inference edge cases

- **Command:** Existing semantic and service tests plus the new
  semantic-unavailable acceptance test; full suite.
- **Actual:** Empty researcher list returns before model load; empty/short profiles
  are handled; one result per researcher; results sorted; empty researcher text
  handled; single batch encoding; model/encode failures raise
  `SemanticMatchingError`; missing/duplicate/unknown semantic IDs raise
  `RecommendationError`; semantic-unavailable results keep scores finite with
  `semantic_available: false`.
- **Status:** PASS locally; **BLOCKED in production** (the production failure mode
  is an unhandled 500, so the controlled error path is not what production is
  exhibiting).
- **Evidence:** `tests/test_semantic_matching.py`,
  `tests/test_recommendation_service.py`, and the new
  `test_semantic_unavailable_keeps_scores_finite` pass.
- **Corrective action:** After the production fix, deliberately exercise a
  semantic failure in staging and confirm it returns a sanitized 503, not 500.

### Test 10 — Frontend submits profile and renders the actual API response

- **Command:** Chrome headless CDP against the current frontend served locally,
  pointed at the local backend; fill `sAreas`, `sExpertise`, `sSkills`, `sProjects`;
  submit; inspect DOM and network.
- **Actual:** One POST, 200, payload expertise `Computer Vision`, 5 cards rendered.
  Displayed score `96.8% model score` matches API `match_score: 0.9676`.
  Console and page errors: none.
- **Status:** PASS locally; **BLOCKED in production** (Netlify returns 401 for the
  site and `frontend-config.js`; the API also returns 500).
- **Evidence:** `%TEMP%\rt-accept\run\e2e_results.json` and screenshots in
  `%TEMP%\rt-accept\run\shots\`.
- **Corrective action:** Remove or document the Netlify Edge Access gate so the
  release can be tested as an ordinary visitor; fix the API 500; then rerun the
  same browser flow against the deployed URLs.

### Test 11 — Loading and error states

- **Command:** Same browser harness; inspect immediately after submit; drive a 503
  stub and an empty DB; mobile viewport.
- **Actual:** Loading text appears immediately; 503 produces
  `Could not load recommendations: API 503…`; empty results produce the documented
  message; mobile 390 px has no horizontal overflow, card 358 px, badge and nav
  visible.
- **Status:** PASS locally; **BLOCKED in production** (no reachable frontend).
- **Evidence:** `success_renders_api_response.loadingVisible = true`,
  `error_state.postStatus = 503`, `empty_results_state`, `mobile_layout`.
- **Corrective action:** Re-run after the production deployment is reachable.

### Test 12 — CORS for the actual frontend origin

- **Command:** Preflight and simple requests with
  `Origin: https://starlit-empanada-a323e3.netlify.app`; also an unlisted origin.
- **Actual:** Local and production both return the exact origin; methods include
  POST; credentials are not enabled; an attacker origin is not echoed.
- **Status:** **PASS.**
- **Evidence:** Production `allow_origin` and `simple_allow_origin` equal the
  Netlify origin; `attacker_echo: null`; local same.
- **Corrective action:** None. Keep `FRONTEND_ORIGINS` in sync with the final
  frontend hostname.

### Test 13 — No secrets/private database details exposed

- **Command:** Inspect error bodies, researcher payloads, and headers; new leakage
  tests.
- **Actual:** DB payloads are clean, production 500 bodies are generic, and no
  credentials are printed. However, local model and import failures echo absolute
  filesystem paths; `/docs` and `/openapi.json` are public; the API has no
  authentication on any route, including `POST/PUT/DELETE /researchers/…` and
  `/researchers/import`.
- **Status:** **FAIL.**
- **Evidence:** `test_model_failure_detail_does_not_leak_server_path` and
  `test_import_failure_detail_does_not_leak_database_path` fail with paths such as
  `C:\Users\...\missing\researchtwin_logistic_render.joblib` and
  `Import failed: unable to open database file: C:\deploy\secret-location\...`.
  Public docs: `GET /docs` → 200.
- **Corrective action:** Return generic messages to clients
  (`"Recommendation service unavailable"`, `"Import failed"`), log the detailed
  exception server-side only, and add regression tests. Decide whether public
  write endpoints and `/docs` are acceptable for the intended audience; if not,
  add authentication and disable docs in production.

### Test 14 — Memory under repeated requests and prior crash risks

- **Command:** Six repeated `top_k=5` requests against the isolated local server;
  process working-set measurement via Windows `GetProcessMemoryInfo` on the real
  interpreter (the venv shim re-execs a child); production observed via latency and
  errors only.
- **Actual:** Local RSS 645.2 MB before, 646.4 MB after (+1.2 MB), all requests
  0.269–0.312 s. Production has no externally readable memory metric; three
  recommendation attempts returned 500 after 45–165 s, and cold-start HTTP probes
  timed out for up to 62 s.
- **Status:** PASS locally; **BLOCKED in production.** The local footprint is well
  above a common 512 MB instance limit, and the production pattern is consistent
  with resource exhaustion during model initialization, but that remains a
  hypothesis without Render metrics/logs.
- **Evidence:** Local memory JSON above; production probe timings and 500s.
- **Corrective action:** Read Render memory/CPU graphs around a failed request;
  confirm the instance plan and limit; if memory is the cause, reduce the resident
  footprint (avoid loading both transformer and SHAP background copies, use a
  smaller/quantized model, or increase the instance memory) and retest under
  repeated load. Do not change the hosting plan without approval.

---

## 6. Exact next steps to clear the blockers

1. **Read the Render logs (no code change yet).**
   Render Dashboard → `researchtwin-api` → Logs → trigger one recommendation
   request → capture the traceback/exception type and the memory graph. This
   distinguishes OOM from a dependency/import failure. Do not paste environment
   values or credentials into the report.
2. **Confirm what is deployed.**
   Render → Events/Deploys: record the live commit and deploy time; compare with
   the repository commit that contains the verified code. If it is stale,
   redeploy the intended commit.
3. **Reproduce production locally with the deployed dependency set.**
   Create a fresh 3.11 environment from the exact production pins (not the
   existing venv), run the recommendation request, and compare. Pin
   `requirements.txt` to the versions verified here before the next deploy.
4. **Fix the production recommendation failure.**
   Apply the smallest change supported by the logs (dependency pin, memory
   reduction, model artifact path, or startup handling), then redeploy and rerun
   `POST /recommendations/researchers` with `top_k=3` and `top_k=5`.
5. **Add and deploy `GET /ready`.**
   Return 200 only when the DB is reachable and the model artifact can be loaded;
   return 503 otherwise. Point the Render health check at it after confirming the
   platform supports the change. Re-run Test 2.
6. **Sanitize error responses.**
   Replace path-bearing `detail` strings in `app/api/researchers.py` and the model
   loaders with generic client messages; log details internally. Re-run the two
   leakage tests.
7. **Make the deployed frontend reachable.**
   Either remove Netlify Edge Access for the release or explicitly accept a private
   release and document how authorized testers sign in. Then rerun the browser
   flows against the real URLs (Tests 10 and 11).
8. **Re-run the complete acceptance pass.**
   ```bat
   cd C:\Users\Venkatesh\ResearchTwin\backend
   C:\Users\Venkatesh\researchtwin-venv311\Scripts\python.exe -m pytest -q
   ```
   Expected after fixes: 108 passed (104 current + 4 previously failing).
   Then rerun the local stack and production probes and update this report.

Because the deployed core feature returns 500 and the deployed frontend is not
reachable by an ordinary visitor, **the project cannot be marked complete**. The
local implementation and the automated contract are in good shape; the remaining
work is production diagnosis and deployment, not local feature development.

---

## Addendum — local blockers cleared, auth phase added (2026-10-28)

The four failing acceptance assertions were fixed in code, and the pre-existing
tests that asserted path-bearing details were updated to the new privacy
contract.

| Blocker | Resolution | Verification |
|---|---|---|
| `/ready` and `/readiness` missing | Both routes now probe the database and model artifact; 503 when not ready | 2 acceptance tests pass; live smoke returned `{"status":"ready"}` |
| Model failure leaked a server path | 503 returns `Recommendation service unavailable`; details logged server-side | Leakage test passes |
| CSV import failure leaked a DB path | 500 returns `Researcher import failed`; details logged server-side | Leakage test passes |

Fresh full-suite result in the documented Python 3.11.9 environment:

```text
133 passed, 2 warnings in 7.59s
```

That total includes 25 new tests for registration, login, logout, session
expiry/revocation, token hashing, role separation, student/faculty profile
persistence, cross-account isolation, and recommendations driven by a saved
profile. A live uvicorn smoke test on a temporary SQLite database confirmed the
end-to-end register → me → profile save → logout flow.

**Production status is unchanged.** The deployed API recommendation 500, the
deployed frontend 401, and the stale-vs-local commit gap were not touched
because no deployment or production configuration change was authorized. The
overall verdict remains **NOT ACCEPTED for production** until those live issues
are resolved and verified.

---

## Addendum — Phase D authenticated browser journey (2026-10-28)

Method: a temporary copy of `frontend/` with a temporary `frontend-config.js`
pointing at a local API on `127.0.0.1:8799`, a temporary copy of
`backend/researchtwin.db`, and a local static server on `127.0.0.1:5510`. The
repository database, model artifacts, backups, and user data were not modified.
Test data used synthetic `@example.com` accounts.

| Acceptance check | Result | Evidence |
|---|---|---|
| Canvas shows login before any session | PASS | auth shell visible, app hidden |
| Student registration and dashboard | PASS | 201, 3 role-aware nav items, "Profile 0%" |
| Empty-profile state (no fake matches) | PASS | guidance + "Open student profile" action |
| Student profile save | PASS | 100% completion, success status, DB row |
| Recommendations from saved profile | PASS | 5 cards, scores 91.8%–47.9%, explanations, skills, gaps, SHAP |
| Profile change affects recommendations | PASS | score 91.8% → 95.4%, gaps cleared after adding OpenCV/TensorFlow |
| Persistent session after reload | PASS | `/auth/me` restore, profile and matches reload |
| Directory and search | PASS | 30 records; "speech" → 1; unknown → empty state |
| Logout revokes server session | PASS | token removed client-side; old token → 401 |
| Wrong password | PASS | "Invalid email or password"; no session |
| Duplicate registration | PASS | "Email already registered"; no session |
| Faculty dashboard and profile save | PASS | 2 role-aware nav items, 100% completion |
| Role enforcement on API | PASS | faculty → student endpoints 403; student → faculty endpoints 403 |
| Expired/revoked token handling | PASS | session cleared, forms reset, sign-in notice shown |
| Password/token storage | PASS | only `researchtwin.sessionToken` in sessionStorage; no password anywhere |
| Console cleanliness | PASS | no uncaught JS exceptions; only expected 4xx network logs |
| Mobile viewport | BLOCKED | browser tool has no viewport resize; responsive CSS reviewed statically only |

Commands run:

```text
node --test tests/frontend/api-client.test.cjs   → 12 passed
python -m pytest -q (3.11.9 pinned env)          → 133 passed, 2 warnings
```

**Verdict:** the local authenticated journey is accepted for demo use. The
project remains **NOT ACCEPTED for production**: the deployed recommendation
endpoint, Netlify access, CORS origin configuration, public write/import
routes, and rate limiting are unresolved. No commit, push, or deployment was
performed.

## Addendum — Phase E API security acceptance (2026-10-28)

### Current route authorization

| Route | Verified local policy |
|---|---|
| `GET /researchers/`, `GET /researchers/{id}`, `GET /researchers/intelligence` | Public read/search retained. |
| Researcher create/update/delete and `POST /researchers/import` | Admin role only. Anonymous requests return 401; student/faculty return 403. Tests provision the admin directly in the throwaway test database. Public registration cannot create admins; no production admin mechanism or account is verified. |
| `POST /recommendations/researchers` | Deprecated authenticated compatibility route, student only. Uses the caller's stored profile, ignores submitted profile text, caps `top_k` at 10, and returns the old body shape plus deprecation/successor headers. |
| `POST /students/me/recommendations` | Student only; uses the caller's saved profile; current frontend route. |
| `/auth/register`, `/auth/login` | Public, restricted to student/faculty roles, rate-limited. |
| `/auth/logout`, `/auth/me` | Bearer session required; logout revokes token hash; expiry is enforced. |
| Student/faculty `/me/profile` routes | Matching role only; profiles bind to authenticated user; client ownership/role overrides are rejected. |
| `POST /recommendations/roadmap/researcher` | Public read-only operation using the stored researcher record. |

CSV validation checks file extension, a 2 MiB size ceiling, allowed/required
columns, row count, row content, field lengths, integer experience range, and
HTTP(S) profile URLs. Every row is validated before a single transaction; a bad
row prevents partial insertion. Failure details are sanitized. Request bodies
are capped at 65,536 bytes.

### Implementation and verification

- Registration: 5 attempts per IP/email/hour. Login: 10 per IP/email/15 minutes.
  Recommendations: 8 per IP/student/5 minutes. Atomic fixed-window counters
  contain HMAC’d keys only and return 429 with `Retry-After`.
- Render configuration requires `RATE_LIMIT_HASH_SECRET`, trusted
  `CF-Connecting-IP`, and PostgreSQL for shared counters. Readiness and limiter
  calls fail closed if the secret is missing or the configured shared DB is
  SQLite. The deployed Render environment values were not checked. Counters
  are global only for instances sharing the same PostgreSQL database.
- Passwords are salted PBKDF2-HMAC-SHA256 (600,000 iterations); tokens are
  random and stored as SHA-256 hashes. Existing and new tests cover password
  hashing, expiry, logout revocation, and cross-account profile isolation.
- Frontend code was not changed for Phase E. It still stores only its bearer
  token in `sessionStorage`, which remains exposed to same-origin XSS; passwords
  are not stored. Safe HttpOnly-cookie migration remains future work requiring
  coordinated CORS and CSRF protections.

Exact final commands and results:

```text
cd C:\Users\Venkatesh\ResearchTwin\backend
C:\Users\Venkatesh\researchtwin-venv311\Scripts\python.exe -m pytest -q
→ 156 passed, 2 warnings (Python 3.11.9)

cd C:\Users\Venkatesh\ResearchTwin
node --test tests/frontend/api-client.test.cjs
→ 13 passed, 0 failed
```

The two Python warnings are upstream deprecations in Starlette's TestClient
`httpx` integration and AnyIO's `BlockingPortal` alias. The first focused run
had 21 test failures because old fixtures still assumed the legacy route was
anonymous, passed `top_k` into strict profile payloads, and reused an import-test
marker across parameterized cases; those tests were updated, the focused rerun
passed, and the final full suite passed.

No production request was made. The prior production 500 and Netlify 401 are
historical findings, not reverified in Phase E. No database, model, backup or
production data was modified, and nothing was staged, committed, pushed or
deployed.

**Next phase: Phase F — Production configuration and release verification.**
Set and verify shared PostgreSQL and a generated limiter secret in Render;
provision an admin out of band only if needed; deploy through the approved
release process; then verify readiness, CORS, auth, role/profile isolation,
rate limits, directory reads, and recommendations against the live frontend and
API.

## Addendum — Phase G feature acceptance (2026-10-31)

Phase G implemented the remaining product workflows: per-researcher readiness
roadmaps from the saved student profile, persisted milestone progress, the
student→faculty collaboration request lifecycle, faculty directory search, and
the empty-skill-gap defect. Acceptance below is local; the deployed services
were not probed, so this section does not change the production verdict.

### Acceptance matrix

| # | Acceptance condition | Result | Evidence |
| --- | --- | --- | --- |
| G1 | Roadmap is served only to an authenticated student | PASS | `401` anonymous and `403` for a faculty token in `test_roadmap_progress.py` / `test_acceptance.py`; live `401` logged by the server during the browser run |
| G2 | Roadmap needs a saved profile, never a client-computed gap | PASS | `400 "Save your student profile before generating a roadmap"`; `test_roadmap_ignores_client_supplied_skill_lists` shows client skill lists are ignored and gaps come from the stored profile |
| G3 | Blank student skills are not reported as gaps in every researcher skill | PASS (defect fixed) | `student_skills_provided: false`, `skill_gaps: []`, guidance message, and the researcher's own skill list still returned — in `test_roadmap_progress.py` and reproduced live for a second account |
| G4 | Roadmap structure: matched skills, gaps, priority, per-skill reason, milestones, mini-project, completion criteria | PASS | Full-plan assertions in `test_roadmap_progress.py`; browser panel rendered 3 items with high/medium/low pills, 3 milestones, 1 mini-project, 3 criteria |
| G5 | Progress persists server-side, is reopenable, and survives refresh/another device | PASS | `test_roadmap_persists_progress_and_reopens` plus browser: ticked `pytorch` milestone → "1 of 9 / Roadmap 11%" → full page reload and session restore kept the checkbox and percentage |
| G6 | Progress is owned by the student and bounded by the current roadmap | PASS | Cross-student and cross-researcher isolation tests; `404` for an unknown skill or out-of-range milestone index |
| G7 | Students request collaboration with a message and see their own requests and status | PASS | `201 pending` → student "My Requests" list; duplicate pending returns `409`, blank message `422`, unknown researcher `404` |
| G8 | Students cannot read another student's requests | PASS | Isolation test plus `403` for a student token on both faculty routes in the live run |
| G9 | Faculty see only requests addressed to their own directory record and can accept/reject with an optional reply | PASS | Claim-based ownership (`faculty_researcher_links`); `403 "You can only respond to requests addressed to your linked record"`; accept-with-reply and reject-without-reply both tested and demonstrated live |
| G10 | Faculty cannot claim a record already owned | PASS | `409 "This researcher record is already linked to another account"` |
| G11 | Student contact email is not leaked into the faculty inbox | PASS | `"email" not in record["student"]` assertion and the rendered inbox row in the browser run |
| G12 | Faculty directory listing supports search and filtering over real records | PASS | `test_free_text_search_matches_descriptive_fields_and_escapes_wildcards` (name and publication matches, `%` escaped to no rows); routes read `researchers` only |
| G13 | Recommendation engine untouched; scores come from the model, not literals | PASS (unchanged) | Existing suite still green; browser run returned 5 real directory researchers with model score `81.1%`, component scores and SHAP-style explanation |
| G14 | No duplicate faculty model introduced | PASS | Linking reuses the existing `Researcher` records; the new table stores only the ownership binding |

### Exact final commands and results

```text
cd C:\Users\Venkatesh\ResearchTwin\backend
C:\Users\Venkatesh\researchtwin-venv311\Scripts\python.exe -m pytest -q
→ 189 passed, 2 warnings in 31.05s (Python 3.11.9)

cd C:\Users\Venkatesh\ResearchTwin
node --test tests/frontend/api-client.test.cjs
→ 19 passed, 0 failed
```

The two warnings are the same upstream Starlette/`httpx` and AnyIO deprecations
recorded in Phase E. Nine of the new tests failed on the first run. Most were
collaboration tests poisoned by stale `faculty_researcher_links` rows: `seeded_db`
recycles researcher ids while the link table survived, and `researcher_id` is
unique, so an unrelated test inherited an owner. An autouse fixture that clears
the two Phase G tables inside the test database fixed them. The remaining
failures were wrong expectations of mine — the fixtures share a publication
string, and `conftest` hardcodes `full_name` — corrected without weakening a
check, and the dead `full_name` parameter was removed.

### Manual verification still required

- **Blocked (not attempted):** every live Render/Netlify probe. Deployment was
  out of scope for this task, so `NOT ACCEPTED FOR PRODUCTION` from §6 stands.
- **Blocked:** mobile-viewport rendering of the new roadmap and inbox panels —
  the same headless resize limitation recorded in Phase D. The new panels were
  verified at desktop width only.
- **Known product gaps:** a faculty reply does not notify the student (they
  must open "My Requests"); there is no in-app admin path to seed or maintain
  researcher records, so a fresh deployment's directory stays empty until an
  operator provisions an admin out of band; `sessionStorage` bearer-token XSS
  exposure is unchanged.

Nothing was staged, committed, pushed, or deployed during Phase G, and no
production data, database, or environment value was modified.
