# ResearchTwin — Project Completion Audit

> **Current update 2026-10-28 (Phase E API security):** researcher mutations and
> CSV import now require the `admin` role; the legacy recommendation route
> requires a student token and uses that student's saved profile. Registration,
> login, and recommendation limits use atomic database counters. The final
> Python 3.11 run is **156 passed, 2 warnings**; Node API-client tests are
> **13 passed**. This was local-only: no live application was probed or changed,
> and nothing was staged, committed, pushed, or deployed. The Phase D gap list
> below is historical; see the Phase E addendum at the end.

> **Update 2026-10-28 (Phase D frontend integration):** the existing static
> frontend now authenticates against the backend, persists student/faculty
> profiles through the API, and requests recommendations from the saved profile.
> Verified locally in a real browser; nothing was deployed. See
> "Addendum — Phase D" at the end. The production blockers below are unchanged.

> **Update 2026-10-28 (Phase B/C implementation):** The local readiness and
> error-leakage blockers are fixed, and authentication plus persistent
> student/faculty profiles have been added. The suite is now **133 passed**.
> See "Addendum — Phase B/C" at the end. Production status is unchanged:
> nothing was deployed, and the production recommendation 500 / Netlify 401
> blockers still stand.

**Audit date:** 2026-10-28
**Auditor role:** Senior engineer, read-only evidence gathering
**Scope:** `C:\Users\Venkatesh\ResearchTwin` (repo `venkatesh19-prog/ResearchTwin`, branch `main`)
**Historical posture (original Phase D audit):** No source file, database, model, backup, or user data was modified during that audit. The later Phase E work changed local source and test files only; it did not touch a database, model, backup, or user data. Nothing was staged, committed, pushed, or deployed.
**Method:** Filesystem inventory, Git inspection, SQLite read-only queries, joblib bundle inspection, live local uvicorn + curl matrix, real-browser end-to-end test (browser-use), and read-only production probes.

---

## Executive summary

The project is **functionally complete as a demo on a developer machine** and **not release-ready**.

| Area | Status | Evidence |
|---|---|---|
| Local backend (Python 3.14 venv) | **Working** | 20/21 endpoint checks passed; recommendation returns 5 scored, explained results in ~0.45 s warm |
| Local frontend ↔ local backend | **Working** | Browser test rendered 5 cards, 30 faculty rows, 0 console errors, both fetches HTTP 200 |
| Production API — read endpoints | **Working** | `/health`, `/`, `/researchers/` (30 records), `/openapi.json`, `/docs` all 200 |
| Production API — recommendation | **Broken** | `POST /recommendations/researchers` returned **no response in 180 s** (curl `HTTP 000`) |
| Production frontend | **Not publicly reachable** | Anonymous request to the Netlify URL returns **HTTP 401** and redirects to `app.netlify.com/edge-access` |
| Automated tests | **None** | `pytest --collect-only` → `no tests collected` |
| Documentation | **None** | `README.md` is 34 bytes (`# ResearchTwin`) |
| Repo ↔ deployment parity | **Diverged** | Local `main` is **1 unpushed commit ahead** of `origin/main` |

**One-line verdict:** the product works locally, the delivered production deployment does not serve the core feature, and the repository has no test or documentation safety net.

---

## 1. Existing architecture and data flow

### 1.1 Topology

```
Browser (static HTML + vanilla JS)
  ├─ frontend/index.html            UMS shell page ("Launch Application")
  └─ frontend/researchtwin.html     Single-page app: 3 views, no framework
        └─ reads window.RESEARCHTWIN_API_BASE from frontend/frontend-config.js
                │  HTTPS + CORS
                ▼
FastAPI service (Render, rootDir=backend, uvicorn app.main:app)
  ├─ CORS middleware                backend/app/main.py:28-34
  ├─ /researchers/*                backend/app/api/researchers.py
  ├─ /recommendations/*            backend/app/api/students.py
  │      └─ ML + SHAP engine       backend/app/services/recommendation.py
  │             ├─ TF-IDF           sklearn TfidfVectorizer (fitted per call)
  │             ├─ semantic         sentence-transformers all-MiniLM-L6-v2
  │             ├─ classifier       joblib: sklearn Pipeline(StandardScaler, LogisticRegression)
  │             └─ explainer        shap.LinearExplainer (background = training CSV)
  └─ SQLAlchemy 2.x                backend/app/database.py
         ├─ DATABASE_URL if set (postgres:// → postgresql+psycopg:// rewrite)
         └─ else SQLite file backend/researchtwin.db
```

### 1.2 Request flow for `POST /recommendations/researchers`

1. Pydantic `StudentProfile` accepts `research_areas, expertise, skills, projects, publications, top_k` — [backend/app/api/students.py:15](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/students.py#L15).
2. `db.query(Researcher).all()` — no filtering, no pagination — [recommendation.py:475](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L475).
3. One batched semantic encode of student + all researchers — [semantic_matching.py:46](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/semantic_matching.py#L46).
4. Per researcher, 8 features are computed — [recommendation.py:215](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L215): `tfidf_similarity, semantic_similarity, research_area_similarity, expertise_similarity, skill_overlap, project_similarity, publication_similarity, department_match`.
5. `model.predict_proba(X)[:,1]` → `match_score` — [recommendation.py:533](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L533).
6. Sort descending, slice `[:top_k]` — [recommendation.py:550-556](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L550).
7. SHAP over the top-k rows, summarized into a sentence — [recommendation.py:562](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L562), [recommendation.py:368](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L368).
8. Skill gap computed from student skills vs researcher skills — [skill_gap.py:24](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/skill_gap.py#L24).
9. JSON returns `researcher_id, name, department, match_score, component_scores, why_recommended, explanation, matched_skills, skill_gap`.

### 1.3 Persistence model

One table only — [backend/app/models.py:6](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/models.py#L6): `researchers(id, name, department, designation, experience, research_areas, expertise, skills, publications, projects, profile_url)`.

There is **no** `students`, `users`, `matches`, or `roadmaps` table. Student profiles exist only in browser `localStorage` ([researchtwin.html:262](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L262)).

Schema is created at import time via `Base.metadata.create_all` ([main.py:15](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L15)); there are **no migrations** (no Alembic).

---

## 2. Implemented features (verified working)

| Feature | Location | Evidence |
|---|---|---|
| Health + root endpoints | [main.py:47-63](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L47) | 200 locally and in production |
| Researcher create / list / filter / get / update / delete | [researchers.py:23-180](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/researchers.py#L23) | list + get + 404 + `?department=` filter verified live |
| CSV import endpoint | [researchers.py:187](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/researchers.py#L187) | route present in prod OpenAPI; **not executed** (mutating) |
| Researcher intelligence profiles | [researcher_intelligence.py:75](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/researcher_intelligence.py#L75) | 200, 30 profiles |
| ML recommendation with 8 features + scores | [recommendation.py:469](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L469) | 5 results, numeric `match_score` (0.49–0.87 observed) |
| SHAP per-feature explanation + natural-language summary | [recommendation.py:368](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L368) | `all_contributions` + `summary` present; rendered in UI |
| Skill gap + matched skills | [skill_gap.py:24](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/skill_gap.py#L24) | returned and rendered as tags |
| Readiness roadmap generator (8 curated skills + generic fallback) | [readiness_roadmap.py:7-194](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/readiness_roadmap.py#L7) | 200 for `researcher_id=1`, 404 for unknown id |
| SPA shell with 3 views, XSS-escaped rendering | [researchtwin.html:259-527](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L259) | `escapeHTML` used on every interpolated field; browser test clean |
| Faculty directory with client-side search | [researchtwin.html:466](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L466) | 30 entries rendered |
| Local profile persistence | [researchtwin.html:444-464](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L444) | localStorage read/write in code; honest alert that it is browser-only |
| ML training/eval scripts (dataset, labels, logistic/RF/XGBoost, ablation, error analysis) | `backend/train_*.py`, `evaluate_*.py`, `create_topk_labels.py`, `save_model.py` | artifacts present (`ablation_results.csv`, `ranking_ablation_results.csv`) |

---

## 3. Missing or broken features

### 3.1 Critical — production recommendation endpoint does not return

`POST https://researchtwin-api.onrender.com/recommendations/researchers` with the documented baseline profile returned **no bytes in 180 s** (`HTTP 000`), while the same payload on a local warm server returned 200 in 0.44 s. Immediately afterwards `/health` answered in 2.28 s, so the instance itself is alive.

Contributing causes, all evidenced:

- **Unpushed fix.** `origin/main` is `6c1439a`; local `HEAD` is `0f42834` "Prepare ResearchTwin production recommendation release" (**ahead 1, not pushed**). That commit is exactly the fix that batches semantic encoding ([recommendation.py:485-513](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L485)) instead of calling `model.encode` twice inside the per-researcher loop, as the `origin/main` version does. If Render deploys from GitHub `main`, production is running the unbatched code.
- **Model load cost at request time.** `sentence-transformers` + `torch` are imported and `all-MiniLM-L6-v2` (~90 MB) is downloaded/loaded on the first request ([semantic_matching.py:9-11](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/semantic_matching.py#L9)). Local cold start was **7.46 s**; Render's free tier (0.1 CPU / 512 MB) with an ephemeral disk re-downloads and re-loads this on every cold start.
- **Unbounded request cost.** Each request refits 5 TF-IDF vectorizers per researcher ([recommendation.py:108-131](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L108)) and builds the SHAP explainer from a CSV read ([recommendation.py:82](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L82)).

### 3.2 High — `top_k` is unvalidated and can 500

- `top_k=0` → **HTTP 500**, `ValueError: at least one array or dtype is required` (empty DataFrame reaches `StandardScaler`/SHAP). Reproduced with full traceback.
- `top_k=-5` → accepted, returns `candidate_rows[:-5]` (silently drops the last 5 ranked researchers).
- `top_k=1000` → accepted, silently clamped to 30 by data size.
- Guard point: [students.py:21](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/students.py#L21) (`top_k: int = 5`) and [recommendation.py:556](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L556).

### 3.3 High — `department_match` is a dead feature (training/serving skew)

- Training data: `department_match` was generated as a **researcher-only constant** — `"computer science" in researcher.department.lower()` ([generate_matching_dataset.py:189-193](file:///C:/Users/Venkatesh/ResearchTwin/backend/generate_matching_dataset.py#L189)). Distribution in `matching_topk_labeled.csv`: 200 ones / 100 zeros. It carries no student signal.
- Serving: `StudentProfile` has **no `department` field**, so `student_profile.get("department", "")` is always empty and the feature is **always 0.0** ([recommendation.py:191-207](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L191)). Confirmed in every live response (`department_match: 0.0`), including when a `department` key was sent explicitly (silently ignored by Pydantic).
- Impact: scaler mean 0.6667 / scale 0.4714 with coef 0.008178 ⇒ a **constant −0.0116 logit offset** for every researcher, plus a model input that is pure noise. The UI does not show this feature, so the bias is invisible.

### 3.4 High — frontend hardcodes student `expertise`

[researchtwin.html:279](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L279) sends `expertise: "Machine Learning"` for **every** student, and `publications` is always empty. There is no input for either. `expertise_similarity` — the second-highest weighted feature in the observed SHAP output (+1.0255 on the top card) — is therefore driven by a constant string, not the user. Reproduced: the UI's top result differed from the curl baseline purely because of this hardcode.

### 3.5 Medium — roadmap endpoint produces self-contradictory output

[students.py:58-90](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/students.py#L58) recomputes `skill_gap` with an **empty student skill string** (`calculate_skill_gap("", researcher)`), so every researcher skill becomes a "gap", while `matched_skills` is taken **from the client**. Live result for `researcher_id=1`: `matched_skills: ["python"]` **and** `skill_gaps` containing `python` (priority "high") in the same response. The client can also mark arbitrary skills as matched.

### 3.6 Medium — no roadmap UI despite the claim

The recommendations card says "Calculates student-researcher compatibility, SHAP attributions, **and readiness roadmaps**" ([researchtwin.html:220](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L220)), but no frontend code calls `/recommendations/roadmap/researcher`. The feature exists server-side only.

### 3.7 Medium — no student persistence

The "Update & Re-index Profile" button only writes `localStorage` ([researchtwin.html:455](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L455)); the alert honestly says so, but the button label and the "re-index" wording overstate what happens. There is no student table or API, so matches cannot be saved, audited, or reproduced.

### 3.8 Medium — reproducibility scripts broken / dead code

| File | Problem | Evidence |
|---|---|---|
| `backend/generate_matching_dataset.py:8` | `from app.services.semantic_matching import model` — no module-level `model` exists after the lazy-load refactor | `ImportError: cannot import name 'model'` (executed) |
| `sys,py:15` | `from core.nlp_extractor import` with no names | `SyntaxError: invalid syntax` line 15 (executed) |
| `backend/app/services/matching.py` | Unused legacy TF-IDF ranker | no imports found |
| `backend/app/services/researcher_similarity.py` | Unused weighted scorer | no imports found |
| `backend/app/services/researcher_features.py` | Unused helper | no imports found |
| `backend/app/services/recommendation_explanation.py` | Unused; also reads `scores["research_areas"]` which no longer exists in `component_scores` (would `KeyError` if wired) | no imports found |
| `backend/app/researcher_import.py` | Byte-for-byte duplicate of `services/researcher_import.py` | duplicate |
| `main.py`, `recommender.py`, `nlp_extractor.py`, `students.csv`, `index.html`, `researchtwin.html`, `frontend-config.js` (repo root) | Legacy v3 app; root `main.py` points at `data/` and `models/` paths that do not exist at root | duplicated with `backend/` + `frontend/` |
| `backend/test_semantic_matching.py` | Not a test — prints results at import time | 0 tests collected |

### 3.9 Medium — duplicate frontend sources

`researchtwin.html` exists at the repo root and in `frontend/` and is **byte-identical**; `index.html` differs only by CRLF. `netlify.toml` publishes `frontend`, so the root copies are dead but look editable — a real risk of fixing the wrong file.

### 3.10 Low

- No pagination on `GET /researchers/` (fine at 30 rows, not at scale).
- No `.env.example` although `.gitignore` explicitly allow-lists it.
- `README.md` has no content — no setup, run, test, or deploy instructions.
- Pydantic v2 still uses the deprecated `class Config` style ([schemas.py:29](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/schemas.py#L29)); works, but emits legacy-style API.
- Labels in `<form>` are not associated with inputs (`for`/`id` missing) — screen-reader labels are lost ([researchtwin.html:231-241](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L231)).
- `backend/seed_researchers.py` calls `db.query(Researcher).delete()` before inserting — running it destroys existing researcher data.
- Frontend depends on two external CDNs (Font Awesome, `lpu.in` banner image).

---

## 4. Security and reliability issues

### 4.1 Security

| # | Issue | Severity | Location |
|---|---|---|---|
| S1 | **Unauthenticated destructive write APIs.** `DELETE /researchers/{id}`, `PUT /researchers/{id}`, `POST /researchers/`, `POST /researchers/import` are all public on the deployed API. Anyone can delete the entire dataset or duplicate it. | Critical | [researchers.py:23-220](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/researchers.py#L23) |
| S2 | **No rate limiting on an expensive endpoint.** Each `POST /recommendations/researchers` costs seconds of CPU and ~hundreds of MB; it is a trivially amplified DoS against a free-tier instance. | High | [students.py:24](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/students.py#L24) |
| S3 | `/docs` and `/openapi.json` are public (verified 200) — publishes the full attack surface including the import endpoint. | Low | FastAPI defaults, [main.py:22](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L22) |
| S4 | CORS is correctly scoped (explicit allow-list from `FRONTEND_ORIGINS`, `allow_credentials=False`) — **no issue**. Wrong origins are not echoed back. | — | [main.py:28-34](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L28) |
| S5 | Frontend escapes all interpolated values (`escapeHTML`), so the SHAP/skill rendering is not XSS-prone — **no issue**. | — | [researchtwin.html:266](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L266) |
| S6 | No secrets committed. Scanned tracked files for key/secret/password/token/postgres URLs and private-key blocks: only `database.py`'s scheme-rewrite strings matched. No `.env` files present. | — | repo-wide |

### 4.2 Reliability

| # | Issue | Evidence |
|---|---|---|
| R1 | Recommendation endpoint does not respond in production within 180 s | live probe |
| R2 | `top_k=0` → unhandled 500 (no exception handler, raw stack trace in server log) | local traceback |
| R3 | SHAP background and TF-IDF are rebuilt/refit per request instead of cached at startup | code + 7.46 s cold / 0.44 s warm |
| R4 | No health signal beyond `{"status":"healthy"}` — it does not check DB reachability, model presence, or embedding availability, so a broken deployment still reports healthy | [main.py:59](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L59) |
| R5 | No request timeouts / graceful degradation: if the embedding model cannot load, the endpoint 500s rather than falling back to TF-IDF-only | [recommendation.py:275-297](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py#L275) |
| R6 | SQLite fallback writes to the container filesystem — fine for dev, silently ephemeral in a container | [database.py:6-11](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/database.py#L6) |
| R7 | `Base.metadata.create_all` with no migrations — any future column change will not apply to an existing database | [main.py:15](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L15) |

---

## 5. Frontend / backend integration status

| Check | Result | Evidence |
|---|---|---|
| API base URL wiring | **Correct** | `frontend/frontend-config.js` → `https://researchtwin-api.onrender.com`; root copy → `http://127.0.0.1:8000`; overridable via `window.RESEARCHTWIN_API_BASE` |
| Deployed CORS for the Netlify origin | **Correct** | preflight `OPTIONS` returned `access-control-allow-origin: https://starlit-empanada-a323e3.netlify.app`, methods `GET, POST, PUT, DELETE, OPTIONS`, `vary: Origin` |
| Response contract match | **Correct** | UI consumes `match_score`, `explanation.all_contributions`, `matched_skills`, `skill_gap`, `department` — all present |
| Golden path in a real browser | **Pass** (local API) | filled profile → 5 cards with % score, summary, matched/missing skill tags, SHAP bars |
| Faculty view | **Pass** | 30 rows rendered from `GET /researchers/` |
| Console / network errors | **None** | 0 console errors; `POST /recommendations/researchers [200]`, `GET /researchers/ [200]` |
| Error state when backend is down | **Not tested** | handler exists ([researchtwin.html:346](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L346)) but was not exercised |
| Roadmap UI | **Missing** | no fetch to `/recommendations/roadmap/researcher` anywhere in the HTML |
| Profile persistence to backend | **Missing** | localStorage only |
| Deployed site reachability | **Fails** | HTTPS 401 + redirect to Netlify edge-access for `/`, `/researchtwin.html`, and `/frontend-config.js` |

Integration conclusion: the **code-level contract is sound and demonstrably renders**. The blockers are deployment-side (site gating, API latency) plus the frontend gaps in §3.4–3.7.

---

## 6. Database and model compatibility status

### 6.1 Databases

| Path | Size | Table | Rows | Notes |
|---|---|---|---|---|
| `backend/researchtwin.db` | 24,576 B | `researchers` | **30** | The DB the app actually opens (`database.py` default path resolves to `backend/researchtwin.db`) |
| `researchtwin.db` (repo root) | 12,288 B | `researchers` | **0** | Stale duplicate from before the path fix (`database.py.pre-db-path-fix.bak`); the app no longer reads it |
| Production | — | `researchers` | **30** (ids 1–30) | Names/departments match the seed set |

Schema in both files matches [models.py:6-27](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/models.py#L6) exactly: `id, name, department, designation, experience, research_areas, expertise, skills, publications, projects, profile_url`. **No schema drift.** No foreign keys, no indexes beyond the primary key.

Production data source cannot be confirmed from outside: the SQLite file is gitignored, so it cannot ship inside the container — meaning production rows came from either a configured Postgres `DATABASE_URL` or a post-deploy call to `POST /researchers/import`. Both are plausible; verification requires dashboard access.

### 6.2 Model bundle

```
backend/models/researchtwin_logistic_render.joblib   (2,233 B)  ← loaded by the app
backend/models/researchtwin_logistic.joblib          (2,233 B)  ← identical numbers
backend/models/researchtwin_logistic_compat_test.joblib (2,233 B, untracked)
```

Bundle keys: `['model', 'features']`. Pipeline: `StandardScaler → LogisticRegression`, classes `[0, 1]`, `C=0.01`, `liblinear`, `random_state=42`.

- **Coefficients and intercept are numerically identical between `researchtwin_logistic.joblib` and `researchtwin_logistic_render.joblib`.** Swapping the bundle therefore changes no numbers; only the surrounding request code changed in that commit.
- Pickle was written by **scikit-learn 1.7.2**. Loaded successfully under **scikit-learn 1.9.1 / Python 3.14.3** with `InconsistentVersionWarning` (a warning, not an error). Production pins 1.7.2, which is an exact match — the model is compatible with the declared stack.
- Not re-tested under Python 3.11 + sklearn 1.7.2 because the local 3.11 interpreter does not have `fastapi`, `pandas`, or `scikit-learn` 1.7.2 installed. **This baseline claim is inherited, not re-verified by me.**

### 6.3 Training data and label quality

`backend/data/matching_topk_labeled.csv` — 300 rows, 10 synthetic students × 30 synthetic researchers, 30 positives / 270 negatives (10 % positive).

Labels are **heuristic, not human annotations**: `relevance_label = rank(prototype_relevance_score) <= 3`, where the score is a hand-weighted sum of five of the same features the model consumes ([create_topk_labels.py:15-33](file:///C:/Users/Venkatesh/ResearchTwin/backend/create_topk_labels.py#L15)). This is circular: the model is trained to reproduce the ranking of its own inputs.

Reported offline metrics (`backend/data/ablation_results.csv`, `ranking_ablation_results.csv`):

| Model | ROC-AUC | Precision | Recall | F1 | NDCG@3 |
|---|---|---|---|---|---|
| TF-IDF Only | 0.976 | 0.938 | 0.500 | 0.652 | 0.847 |
| Semantic Only | 0.935 | 0.867 | 0.433 | 0.578 | 0.847 |
| Structured Features | 0.991 | 0.844 | 0.900 | 0.871 | 0.953 |
| **Hybrid Model (deployed)** | **0.988** | **0.675** | **0.900** | **0.771** | **0.953** |

Two honest observations: `Precision@1 = 1.0` for every model is a signature of circular labels, and the **deployed hybrid has the worst precision of the four**. These numbers should not be presented as evidence of real-world quality without a human-labeled holdout.

---

## 7. Deployment readiness

### 7.1 Render (`render.yaml`)

```yaml
runtime: python
rootDir: backend
buildCommand: pip install -r requirements.txt
startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
healthCheckPath: /health
PYTHON_VERSION: 3.11.11
DATABASE_URL: sync false
FRONTEND_ORIGINS: sync false
```

Correct in shape and verified live for read paths. Gaps:

1. **No seed/migration step.** A fresh instance has no researchers unless `DATABASE_URL` already points at a populated database or someone calls the import endpoint. (Production currently has 30 rows; origin is unverified.)
2. **No model/embedding warm-up at build.** `all-MiniLM-L6-v2` is fetched at first request.
3. **`torch` is not pinned** in `requirements.txt` — it arrives transitively via `sentence-transformers==6.1.0`, so builds are not reproducible and can pull a large CUDA-less wheel whose size/startup cost is uncontrolled.
4. **Runtime sizing is incompatible with the workload** — the observed 180 s timeout is consistent with 0.1 CPU / 512 MB loading torch + a transformer.
5. **The fix is not deployed.** `origin/main` = `6c1439a`; local `main` = `0f42834` (ahead 1, unpushed). Whether Render is wired to GitHub `main` cannot be confirmed from here, but the repo state and the observed latency are consistent with production running the older, unbatched code.

### 7.2 Netlify (`netlify.toml`)

```toml
[build]
  publish = "frontend"
```

Valid static publish; `frontend/` contains `index.html`, `researchtwin.html`, `frontend-config.js` (production API URL). No build step, no redirects needed.

**Blocker:** every URL on `https://starlit-empanada-a323e3.netlify.app` returns **401** and redirects to `app.netlify.com/edge-access?domain=…&site_id=…`. Verified with curl *and* in a real browser. Whether this is intentional password/SSO protection or a misconfiguration, the consequence is that the "deployed frontend" is **not publicly usable**. This must be confirmed and resolved (or the protection explicitly acknowledged as intended).

### 7.3 Release readiness matrix

| Gate | Status |
|---|---|
| Repo == deployed backend | ❌ unpushed commit |
| Core feature works in production | ❌ 180 s timeout |
| Frontend publicly reachable | ❌ 401 |
| Frontend can call API (CORS) | ✅ |
| Model loads on pinned runtime | ✅ (numerically identical bundle, sklearn 1.7.2) |
| Database populated | ✅ (30 rows) |
| Write endpoints protected | ❌ none |
| Automated tests | ❌ zero |
| Docs / run instructions | ❌ none |
| Monitoring / error reporting | ❌ none |

**Verdict: NOT RELEASE-READY.**

---

## 8. Tests actually executed and their results

> Everything below was run by me in this session. Nothing here is inferred. "Not run" items are listed at the end and were deliberately skipped because they mutate state.

### 8.1 Production probes (read-only)

| # | Command (abridged) | Result |
|---|---|---|
| P1 | `GET /health` | **200** `{"status":"healthy"}` 1.06 s |
| P2 | `GET /` | **200** success payload 0.89 s |
| P3 | `OPTIONS /recommendations/researchers` from Netlify origin | **200**, `ACAO: https://starlit-empanada-a323e3.netlify.app`, `vary: Origin` |
| P4 | `GET /researchers/` | **200**, 13,750 B, **30 records**, ids 1–30 |
| P5 | **`POST /recommendations/researchers`** (baseline profile) | **FAIL — HTTP 000, no response, 180.01 s timeout** |
| P6 | `GET /health` immediately after P5 | **200**, 2.28 s (instance alive) |
| P7 | `GET /openapi.json` | **200** — routes `/researchers/`, `/researchers/intelligence`, `/researchers/{id}`, `/researchers/import`, `/recommendations/researchers`, `/recommendations/roadmap/researcher`, `/`, `/health` |
| P8 | `GET /docs` | **200** (public) |
| P9 | `GET https://starlit-empanada-a323e3.netlify.app/` | **401** → Netlify edge-access redirect |
| P10 | `GET …/researchtwin.html` | **401** |
| P11 | `GET …/frontend-config.js` | **401** |
| P12 | Browser navigation to deployed `/researchtwin.html` | redirected to `app.netlify.com/edge-access…` — confirmed in a real browser |

### 8.2 Local service matrix

Server: `backend/.venv/Scripts/python.exe -m uvicorn app.main:app --port 8123` (Python 3.14.3, FastAPI 0.141.1, sklearn 1.9.1). Health up after 10 s.

| # | Request | Result |
|---|---|---|
| L1 | `GET /` | 200 (90 ms) |
| L2 | `GET /health` | 200 (65 ms) |
| L3 | `POST /recommendations/researchers` baseline (cold) | **200**, 5 recs, 7,456 ms (model cold load) |
| L4 | Same, warm | **200**, 5 recs, **476 ms** |
| L5 | CV student profile, `top_k=3` | 200, 442 ms (body truncated in capture, item count not asserted) |
| L6 | Empty profile | 200, 5 recs at 0.1333 (all features 0) — no crash |
| L7 | **`top_k=0`** | **500** `ValueError: at least one array or dtype is required` |
| L8 | `top_k=-5` | 200 (silently slices from the end) |
| L9 | `top_k=1000` | 200 (clamped to 30 by data) |
| L10 | profile + `department` key | 200; `department_match` still **0.0** (field ignored) |
| L11 | 300-repetition long input | 200, 379 ms |
| L12 | `GET /researchers/` | 200, **30** |
| L13 | `GET /researchers/intelligence` | 200, **30** |
| L14 | `GET /researchers/1` | 200 |
| L15 | `GET /researchers/9999` | **404** `{"detail":"Researcher not found"}` |
| L16 | `GET /researchers/?department=Mechanical` | 200, 1 record |
| L17 | `POST /recommendations/roadmap/researcher` id=1 | 200 — but `python` appears in both `matched_skills` and `skill_gaps` |
| L18 | roadmap unknown id | **404** |
| L19 | malformed JSON | **422** |
| L20 | all responses | `department_match` = 0.0 in every single recommendation |

### 8.3 Browser end-to-end (Chrome via browser-use)

Served the **unmodified** `frontend/researchtwin.html` and `frontend/index.html` from a temp directory (only `frontend-config.js` overridden to point at the local API), plus the local API.

| # | Check | Result |
|---|---|---|
| B1 | `index.html` (UMS shell) loads | **Pass** — sidebar, 5 pills, banner |
| B2 | "Launch Application" opens `researchtwin.html` | **Pass** |
| B3 | Empty-state message before data entry | **Pass** — "Add your research interests…" |
| B4 | Fill profile → ML Recommendations | **Pass** — 5 cards: Dr. Divya Menon 77.5 %, Anil Kumar 62.7 %, Priya Sharma 59.5 %, Aditya Rao 57.7 %, Shalini Bose 52.6 % |
| B5 | SHAP bars, summaries, skill tags render | **Pass** |
| B6 | Faculty Directory | **Pass** — 30 entries |
| B7 | Console errors | **0** |
| B8 | Network | `POST /recommendations/researchers [200]`, `GET /researchers/ [200]` |
| B9 | Readiness roadmap section | **Absent** (feature not wired) |

### 8.4 Code, data, and model checks

| # | Check | Result |
|---|---|---|
| C1 | Load `researchtwin_logistic_render.joblib` | **Pass** — keys `model`/`features`, 8 features, classes `[0,1]`; `InconsistentVersionWarning` 1.7.2→1.9.1 |
| C2 | Compare render bundle vs base bundle | **Numerically identical** (same coef/intercept) |
| C3 | SQLite `backend/researchtwin.db` | 30 rows, expected columns |
| C4 | SQLite `researchtwin.db` (root) | 0 rows |
| C5 | `pytest --collect-only` in `backend/` | **`no tests collected in 19.45s`** |
| C6 | `from app.services.semantic_matching import model` | **ImportError** (breaks `generate_matching_dataset.py:8`) |
| C7 | `compile(open('sys,py').read())` | **SyntaxError line 15** |
| C8 | Import graph for `matching`, `researcher_similarity`, `researcher_features`, `recommendation_explanation`, `app/researcher_import` | **Unreferenced** |
| C9 | Secret scan of tracked files | **Clean** |
| C10 | `diff` of root vs `frontend/` HTML | identical (modulo CRLF) |

### 8.5 Deliberately NOT run

- `POST /researchers/`, `PUT`, `DELETE`, `POST /researchers/import` — mutating; would alter the database.
- `seed_researchers.py` — destructive (deletes all researchers).
- `generate_matching_dataset.py` — would overwrite `matching_features.csv` (already known broken via C6).
- Any production write, deploy, `git add/commit/push`, or model retraining.
- Load testing the production endpoint — it already failed at one request.
- The Python 3.11 + sklearn 1.7.2 exact-model-load check (interpreter lacks the app's dependencies).

---

## 9. Prioritized remaining tasks

### P0 — must be fixed before any public release

**P0-1. Make the recommendation endpoint answer in production.**
Files: [backend/app/services/semantic_matching.py](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/semantic_matching.py), [backend/app/services/recommendation.py](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/services/recommendation.py), [render.yaml](file:///C:/Users/Venkatesh/ResearchTwin/render.yaml)
- Precompute and cache researcher embeddings at startup (they only change when the DB changes); keep only the student encode per request.
- Cache the TF-IDF vocabulary instead of refitting per researcher per request.
- Either pin the embedding model into the image at build time (`sentence-transformers` cache dir inside the build) or ship precomputed vectors as a committed artifact so `torch` is not required at runtime at all.
- Re-evaluate the Render plan (0.1 CPU / 512 MB is below this workload) or switch to a CPU-appropriate tier.
- **Acceptance probe:** 5 consecutive `POST /recommendations/researchers` from a cold instance each return 200 in < 10 s.

**P0-2. Push the production fix so the deployed code matches the repo.**
`main` is ahead 1 (`0f42834`) of `origin/main` (`6c1439a`). Requires explicit owner approval — not done in this audit.

**P0-3. Resolve the Netlify access gate.**
Every URL 401s and redirects to Netlify edge-access. Confirm whether this is intended; if not, disable site protection so `/` and `/researchtwin.html` are publicly reachable.

**P0-4. Validate `top_k`.**
[backend/app/api/students.py:21](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/students.py#L21) — enforce `top_k: int = Field(default=5, ge=1, le=50)`. Stops the reproduced 500 and the silent negative-slice behaviour. Also return `[]` (not a shapeless 500) when no researchers exist.

**P0-5. Protect or remove the mutating researcher endpoints.**
[backend/app/api/researchers.py:23](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/researchers.py#L23) (POST), `:121` (PUT), `:157` (DELETE), `:187` (import). Minimum viable: require an admin token header for all four; disable `/docs` in production (`FastAPI(docs_url=None)`).

### P1 — correctness and product completeness

**P1-1. Fix or drop `department_match`.**
Either add `department` to `StudentProfile` ([students.py:15](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/students.py#L15)), send it from the UI, and regenerate the dataset with a genuine student-vs-researcher comparison ([generate_matching_dataset.py:189](file:///C:/Users/Venkatesh/ResearchTwin/backend/generate_matching_dataset.py#L189)); **or** remove the feature from `FEATURES` in [save_model.py:17](file:///C:/Users/Venkatesh/ResearchTwin/backend/save_model.py#L17), retrain, and re-export. Leaving it as a constant 0 is the worst option.

**P1-2. Give the student real profile inputs.**
[researchtwin.html:279](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L279) hardcodes `expertise`. Add `expertise` and `publications` fields (and optionally `department`) to the Student Profile form and to `getStudentProfile()`.

**P1-3. Make the roadmap endpoint coherent.**
[backend/app/api/students.py:78-90](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/students.py#L78) — derive `skill_gap` from the **student's** skills (accept them in the request or persist the profile), and stop trusting client `matched_skills`.

**P1-4. Ship the roadmap in the UI, or remove the claim.**
Either render `POST /recommendations/roadmap/researcher` per card ([researchtwin.html:220](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L220) currently promises it) or edit the subtitle.

**P1-5. Decide on student persistence.**
Either add a `students` table + `POST/GET /students/{id}` and make "Update & Re-index Profile" actually persist, or rename the button to "Save in this browser" ([researchtwin.html:243](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L243)).

**P1-6. Restore reproducibility of the dataset script.**
[backend/generate_matching_dataset.py:8](file:///C:/Users/Venkatesh/ResearchTwin/backend/generate_matching_dataset.py#L8) — replace `from app.services.semantic_matching import model` with `get_model()`.

**P1-7. Add the missing test suite.**
Create `backend/tests/` with: model-bundle contract test (8 features, classes `[0,1]`), `POST /recommendations/researchers` shape test, `top_k` boundary tests (0, 1, 50, 51, negative), 404/422 tests, and a model-driven ranking regression snapshot. `backend/test_semantic_matching.py` is not a test — convert or delete it.

**P1-8. Quarantine dead and duplicate code (after approval).**
Remove or move to an `archive/` folder: repo-root `main.py`, `recommender.py`, `nlp_extractor.py`, `students.csv`, `index.html`, `researchtwin.html`, `frontend-config.js`, `sys,py`, `ablation_study.py`; `backend/app/services/{matching,researcher_similarity,researcher_features,recommendation_explanation}.py`; `backend/app/researcher_import.py`. Keep exactly one frontend source (`frontend/`) and one study script location (`backend/`).

**P1-9. Remove the untracked backup/artifact clutter** (explicit approval required):
`backend/app/*.bak` (3 files), `backend/app/services/*.bak` (5 files), `backend/requirements.txt.predeploy.bak`, `researchtwin.html.predeploy.bak`, `backend/models/researchtwin_logistic_compat_test.joblib`, `backend/save_model_compat_test.py`.

### P2 — hardening and operator experience

**P2-1.** Pin `torch` and `transformers` in [backend/requirements.txt](file:///C:/Users/Venkatesh/ResearchTwin/backend/requirements.txt); add `httpx`/`pytest` dev requirements file.
**P2-2.** Make `/health` meaningful: report DB connectivity, model file presence, and embedding availability — [main.py:59](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L59).
**P2-3.** Add structured logging + a global exception handler that returns `{"detail": "..."}` instead of bare 500s.
**P2-4.** Seed the database deterministically at deploy time (idempotent import), not via a public endpoint — [render.yaml:6](file:///C:/Users/Venkatesh/ResearchTwin/render.yaml#L6).
**P2-5.** Add pagination (`limit`/`offset`) to `GET /researchers/` — [researchers.py:43](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/researchers.py#L43).
**P2-6.** Write a real `README.md`: setup, env vars (`DATABASE_URL`, `FRONTEND_ORIGINS`), run, test, deploy, model provenance, known limitations.
**P2-7.** Add `.env.example` (already allow-listed in `.gitignore`).
**P2-8.** Remove or fix `sys,py`; fix or delete `seed_researchers.py`'s destructive delete ([seed_researchers.py](file:///C:/Users/Venkatesh/ResearchTwin/backend/seed_researchers.py)).
**P2-9.** Associate `<label for>` with inputs in the student form ([researchtwin.html:231-241](file:///C:/Users/Venkatesh/ResearchTwin/frontend/researchtwin.html#L231)).

### P3 — model quality and honesty

**P3-1.** Produce a human-labeled holdout (even 30 pairs) before quoting any metric publicly; the current labels are generated from the model's own inputs ([create_topk_labels.py:15](file:///C:/Users/Venkatesh/ResearchTwin/backend/create_topk_labels.py#L15)).
**P3-2.** Document the offline numbers and their circularity next to the product claim, including the fact that the deployed hybrid has the lowest precision of the four ablations.
**P3-3.** Consider dropping `department_match` and the redundant `researchtwin_logistic.joblib` duplicate as part of P1-1/P0-1.

---

## 10. Acceptance criteria for declaring the project complete

The project may be declared **release-complete** only when **all** of the following are demonstrated with command output, not by inspection:

### A. Core function
1. From a cold production instance, 5 consecutive `POST /recommendations/researchers` requests with the baseline profile each return `200` in **< 10 s**, and each returns exactly `top_k` items with numeric `match_score`, non-empty `why_recommended`, and 8 numeric `component_scores`.
2. `top_k = 0`, `-1`, `51` each return **422** (not 500). `top_k = 1` returns exactly 1.
3. A profile with all fields empty returns a defined response (either `[]` with a message or 422) — never a 500.

### B. Model integrity
4. `researchtwin_logistic_render.joblib` loads under the **pinned** runtime (Python 3.11 + scikit-learn 1.7.2) with zero warnings, and a startup assertion verifies `bundle["features"] == FEATURES` and `len(features) == 8`.
5. No deployed feature is constant. Specifically: `department_match` is either removed from `FEATURES` or demonstrably varies with student input.
6. A ranked result for the baseline profile is reproducible: same input → same ordering across two calls on the same instance.

### C. Frontend
7. The deployed frontend URL returns **200 for anonymous users** and `researchtwin.html` loads without a redirect.
8. Browser run (real browser, production URL): fill profile → click "Run ML Match Engine" → 5 cards render with scores, summary, skill tags, SHAP bars; **0 console errors**; network shows `POST /recommendations/researchers → 200`.
9. Faculty Directory renders all researchers with a working search filter.
10. Student profile exposes `expertise` (and `publications` if used) — no hardcoded values in `getStudentProfile()`.
11. Either a readiness-roadmap section renders from the roadmap endpoint, or the substring "readiness roadmaps" no longer appears in the UI copy.
12. Backend-down path verified: stop the API, click Run → a friendly error appears (no unhandled promise rejection in console).

### D. Security
13. `DELETE/PUT/POST /researchers/*` and `POST /researchers/import` return **401/403** without an admin credential, verified with curl against production.
14. `/docs` and `/openapi.json` are disabled or protected in production.
15. No secrets in the repo (`git grep` clean) and no `.env` tracked.

### E. Engineering hygiene
16. `pytest` in `backend/` reports **≥ 1 collected test per endpoint group**, all passing, with the count stated explicitly.
17. `main` is pushed and `git status` is clean apart from intentional files; `origin/main == HEAD`.
18. `README.md` contains working setup, env-var, run, test, and deploy instructions that a new contributor can follow unaided.
19. Dead/duplicate modules and `.bak` files are removed, and there is exactly one frontend source of truth (`frontend/`).

### F. Deployment
20. `render.yaml` seeds the database idempotently and warms the embedding model at build or boot; a redeploy from scratch produces a working `/recommendations/researchers` **without any manual step**.
21. `/health` returns 503 when the DB or model is unavailable, 200 otherwise.
22. Netlify publishes `frontend/` and the site is reachable; `frontend-config.js` in the served bundle points at the production API.

**Minimum bar for the user-facing "release" claim:** A, B(4,5), C(7,8,10), D(13). Everything else is required for "complete", but these are what make the product honest.

---

## Appendix — repo state snapshot

- Branch `main`, HEAD `0f42834` "Prepare ResearchTwin production recommendation release" (2026-10-28 13:33 +0530), **ahead 1 of `origin/main` (`6c1439a`)**.
- Second branch: `backup/before-frontend-sync` (`6d3d361`).
- Working tree: **no modified tracked files**; 12 untracked items, all backups/compat artifacts:
  `backend/app/{database,main}.py.*.bak` (3), `backend/app/services/recommendation.py.*.bak` (4), `backend/app/services/semantic_matching.py.predeploy.bak`, `backend/requirements.txt.predeploy.bak`, `researchtwin.html.predeploy.bak`, `backend/models/researchtwin_logistic_compat_test.joblib`, `backend/save_model_compat_test.py`.
  (The brief mentioned "modified source files"; at audit time there were none — only untracked artifacts.)
- Local toolchain used for tests: `backend/.venv` — Python **3.14.3**, sklearn 1.9.1, pandas 3.0.5, numpy 2.5.3, shap 0.52.0, sentence-transformers 6.1.0, torch 2.14.0, pytest 9.1.1. **This differs from the pinned production stack** (Python 3.11.11, sklearn 1.7.2, pandas 2.3.3, numpy 2.2.6) — local results are indicative, not a substitute for a production-stack run.
- Temporary artifacts created outside the repo during this audit: `/tmp/rt_audit_test.sh`, `/tmp/rt_ui_test/` (unmodified frontend copy + local API override), `/tmp/*.log`, `/tmp/prod_*.json`. None affect the repository.

---

## Addendum — Phase B/C (authentication, roles, persistent profiles)

**Date:** 2026-10-28
**Status:** Implemented and verified locally. Nothing was staged, committed,
pushed, or deployed. The repo-state appendix above is a historical snapshot
from before this phase; use `git status` for the current tree.

### Implemented

| Feature | Endpoint / location | Notes |
|---|---|---|
| Student/faculty registration | `POST /auth/register` | Email normalized to lowercase; duplicate → 409 |
| Login | `POST /auth/login` | Generic 401 for wrong password and unknown email |
| Logout | `POST /auth/logout` | Revokes the presented session immediately |
| Current account | `GET /auth/me` | Requires a valid bearer token |
| Student profile read/upsert | `GET`/`PUT /students/me/profile` | Scoped to the authenticated user; `extra="forbid"` blocks ownership tampering |
| Student recommendations from saved profile | `POST /students/me/recommendations` | Loads the persisted profile; 400 until a profile is saved |
| Faculty profile read/upsert | `GET`/`PUT /faculty/me/profile` | Faculty-only |
| Liveness/readiness split | `GET /health`, `GET /ready`, `GET /readiness` | Readiness checks the DB and the model artifact path |
| Sanitized service errors | recommendation + CSV import routes | Generic client detail; details logged server-side |

### Database schema (new tables only)

| Table | Purpose | Constraints |
|---|---|---|
| `users` | Account identity and role | `email` unique; `role` in `student`/`faculty`; PBKDF2 hash |
| `auth_sessions` | Revocable opaque sessions | `token_hash` unique; `expires_at` epoch seconds; `revoked_at` nullable |
| `student_profiles` | One profile per student | `user_id` unique FK → `users.id` |
| `faculty_profiles` | One profile per faculty account | `user_id` unique FK → `users.id` |

The existing `researchers` table is unchanged. `Base.metadata.create_all`
creates only missing tables, so starting the new code against the existing
SQLite or PostgreSQL database adds these tables without altering or deleting
researcher rows. No Alembic revision is required for brand-new tables; any
future **column** change on an existing table still requires a migration.

### Authentication design

- Passwords: PBKDF2-HMAC-SHA256, 600,000 iterations, 16-byte random salt,
  stored as `pbkdf2_sha256$iterations$salt$digest`; verified with
  `hmac.compare_digest`.
- Sessions: 256-bit random bearer tokens. Only the SHA-256 digest is stored.
  Default TTL is 12 hours; override with `AUTH_SESSION_TTL_SECONDS`.
- Transport: `Authorization: Bearer <token>`. No cookies, so CSRF exposure is
  avoided; CORS continues to disable credentials.
- Role separation: student-only and faculty-only dependencies return 403 for
  the other role and 401 for missing/expired/revoked tokens.
- This is a **demo authentication system**, not institutional UMS SSO. It has
  no email verification, password reset, MFA, admin bootstrap, or login rate
  limiting yet.

### API examples

```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"student@example.edu","password":"CorrectHorseBattery9","full_name":"Demo Student","role":"student"}'

curl -X PUT http://127.0.0.1:8000/students/me/profile \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"research_areas":"Machine Learning","expertise":"Deep Learning","skills":"Python, PyTorch","projects":"Search engine","publications":"","courses":"ML","academic_details":""}'

curl -X POST http://127.0.0.1:8000/students/me/recommendations \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"top_k":5}'
```

### Verification

Canonical environment: `C:\Users\Venkatesh\researchtwin-venv311`
(Python 3.11.9, scikit-learn 1.7.2, shap 0.51.0, numpy 2.2.6, pandas 2.3.3).

```text
python -m pytest -q
133 passed, 2 warnings in 7.59s
```

- 25 new tests: 13 in `backend/tests/test_auth.py`, 12 in
  `backend/tests/test_profiles.py`.
- Live smoke on a temporary SQLite database (uvicorn on port 8771):
  `/ready` → 200 `ready`; register → 201; `/auth/me` → 200; profile upsert →
  200 with 71% completion; logout → 200; reused token → 401.
- Earlier acceptance blockers now pass: `/ready`, `/readiness`, model-path
  leakage, and import-path leakage.

### Files changed in this phase

- Modified: `backend/app/models.py`, `backend/app/schemas.py`,
  `backend/app/main.py`, `backend/app/api/students.py`,
  `backend/app/api/researchers.py`
- Added: `backend/app/services/auth.py`, `backend/app/api/deps.py`,
  `backend/app/api/auth.py`, `backend/app/api/profiles.py`,
  `backend/tests/test_auth.py`, `backend/tests/test_profiles.py`
- Updated tests: `backend/tests/test_imports_and_routes.py`,
  `backend/tests/test_recommendations_api.py`
- Updated reports: `PROJECT_COMPLETION_AUDIT.md`,
  `FINAL_ACCEPTANCE_REPORT.md`, `DATABASE_VERIFICATION.md`,
  `PRODUCTION_RELEASE_CHECKLIST.md`, `backend/TESTING.md`
- No new runtime dependency was introduced.

### Remaining gaps after this phase

1. The frontend is not wired to the new auth/profile endpoints yet; it still
   uses browser `localStorage` and the unauthenticated legacy recommendation
   route.
2. `POST /researchers/`, `PUT/DELETE /researchers/{id}`, and
   `POST /researchers/import` remain unauthenticated and must be protected
   before any deployment.
3. The legacy `POST /recommendations/researchers` route remains open for
   backward compatibility; switch the UI to `/students/me/recommendations`
   and then protect or retire it.
4. No rate limiting on login or recommendation requests.
5. No password reset, email verification, MFA, admin bootstrap, or UMS SSO.
6. Production recommendation 500 and Netlify 401 are unchanged and still
   block release.

---

## Addendum — Phase D frontend integration (2026-10-28)

Scope: connect the existing static frontend to the authenticated backend in
small, testable changes. No redesign, no API contract change, no deployment.

### Implemented

- `frontend/api-client.js` — single API client (UMD/IIFE) used by the page and
  by Node tests. Adds the bearer token to authenticated calls, parses JSON and
  non-JSON errors, flattens FastAPI validation details, applies a 15 s default
  timeout and a 90 s recommendation timeout, performs no retries, clears the
  session and notifies once on 401, and keeps 403 handling separate.
- `frontend/researchtwin.html` — login and registration screens (student or
  faculty role), session restore via `/auth/me`, role-aware navigation, sign
  out with server-side revocation, student dashboard with backend-loaded
  profile and recommendations, faculty profile dashboard, researcher directory
  with search, and loading/empty/validation/API-error states.
- Student profile writes `research_areas`, `expertise`, `skills`, `courses`,
  `projects`, `publications`, and `academic_details` to
  `PUT /students/me/profile`; completion comes from the backend response.
- Recommendations call `POST /students/me/recommendations` with `{top_k: 5}`
  and render the saved-profile response. No sample or fallback matches are
  generated when the call fails.
- Faculty profile writes `department`, `designation`, `research_areas`,
  `expertise`, `skills`, `publications`, `projects`, and `profile_url` to
  `PUT /faculty/me/profile`. The UI states that this account profile is
  separate from researcher directory records.
- The directory uses the public `GET /researchers/`, filters in the browser,
  caps nothing, and shows researcher name, department, designation, areas,
  skills, publications, and an http(s)-only profile link.
- The token lives in `sessionStorage` under `researchtwin.sessionToken`.
  Passwords are never stored client-side; password inputs are cleared after
  submit and on sign-out. Forms are cleared on logout/401 so a second user on
  the same browser cannot see the previous user's data.

### Verification

| Check | Command / method | Result |
|---|---|---|
| Frontend API client tests | `node --test tests/frontend/api-client.test.cjs` | **12 passed** |
| Backend regression | `python -m pytest -q` (3.11.9 pinned env) | **133 passed, 2 warnings in 7.89 s** |
| Inline browser script syntax | `node --check` on the extracted script | Pass |
| Browser E2E | Temp frontend copy + temp SQLite copy, local API on 8799, static server on 5510 | Pass (details below) |

Browser E2E evidence (desktop Chrome via browser-use; repository database and
model files untouched):

- Auth screen shown on first load; sidebar hidden.
- Student registration → 201, dashboard with 3 role items, profile 0%, explicit
  "save your profile first" state instead of fake matches.
- Student profile save → 100% completion, success status, records persisted.
- Recommendations from the saved profile → 5 cards with names, "91.8% model
  score", summary, matched skills (python, pytorch), gaps (opencv, tensorflow),
  and SHAP contributions. Scores are labelled model scores, not probabilities.
- Profile edit (`OpenCV, TensorFlow` added) → top score 91.8% → 95.4%, gaps
  cleared, shared skills expanded: saved changes affect the next request.
- Reload → session restored via `/auth/me`, profile and recommendations return.
- Directory → 30 records, search "speech" → 1 result, unknown query → empty
  state.
- Sign out → client token removed, old token returns 401 from `/auth/me`,
  auth screen shown.
- Wrong password → "Invalid email or password", stays on auth screen.
- Duplicate registration → "Email already registered", no session created.
- Faculty registration → only 2 role items (Faculty Profile, Directory);
  faculty profile save → 100% completion; faculty token gets 403 on
  `GET`/`PUT /students/me/profile`; student token gets 403 on
  `GET`/`PUT /faculty/me/profile`.
- Corrupted client token → next authenticated call clears the session, resets
  forms, and shows "Your session has ended…".
- Console: only expected 4xx resource logs, no uncaught JS exceptions.
- Storage: only `researchtwin.sessionToken` in sessionStorage; localStorage
  empty; no password string present.

### Not verified

- Mobile/tablet viewport: the available browser tool cannot resize the
  viewport. Responsive rules were reviewed statically (auth card, stacked
  sidebar, full-width footer, tabs) but not executed in a mobile viewport.
- Production: no deployment, no production probes beyond the earlier audit.

### Remaining gaps after Phase D

1. `POST /researchers/`, `PUT/DELETE /researchers/{id}`, and
   `POST /researchers/import` remain public and destructive.
2. Legacy `POST /recommendations/researchers` remains public; the UI no longer
   uses it.
3. No rate limiting on login, registration, or recommendations.
4. The directory endpoint returns every researcher; browser-side filtering
   will not scale. Add server-side search/pagination before the dataset grows.
5. No password reset, email verification, MFA, admin bootstrap, or UMS SSO.
6. Bearer tokens in `sessionStorage` are readable by any script on the origin
   (XSS). This is weaker than HttpOnly secure cookies and is demo-grade.
7. `auth_sessions` rows are not garbage-collected; expired/revoked rows grow
   unbounded.
8. Production recommendation 500, Netlify 401, stale deployment, and CORS
   configuration are unchanged and still block release.

### Files changed in Phase D

- Added: `frontend/api-client.js`, `tests/frontend/api-client.test.cjs`
- Modified: `frontend/researchtwin.html`
- Updated reports: `PROJECT_COMPLETION_AUDIT.md`,
  `FINAL_ACCEPTANCE_REPORT.md`, `PRODUCTION_RELEASE_CHECKLIST.md`,
  `backend/TESTING.md`
- No backend source, database, model, backup, or user data was modified in this
  phase. No commit, push, or deployment occurred.

## Addendum — Phase E API security hardening (2026-10-28)

### Verified route policy

| Operation | Policy and behavior |
|---|---|
| `GET /researchers/`, `GET /researchers/{id}`, `GET /researchers/intelligence` | Public read/search retained. |
| `POST /researchers/`, `PUT /researchers/{id}`, `DELETE /researchers/{id}` | `admin` role required; anonymous receives 401, student/faculty receive 403. No frontend caller was found; routes are retained as administrative maintenance operations. Registration accepts only student/faculty. No default admin password or public admin provisioning endpoint exists. |
| `POST /researchers/import` | `admin` role required. Bundled CSV only; extension, 2 MiB size, schema, row count (2,000), field lengths, names, experience and profile URL are validated. Rows are parsed and validated before one transaction; errors roll back and client errors are sanitized. No UI caller was found; the route is retained as an administrative maintenance operation. |
| `POST /recommendations/researchers` | Kept as a deprecated compatibility alias. Requires student auth, reads only the authenticated student's saved profile, ignores submitted profile fields, caps profile fields at 4,000 characters and `top_k` at 10, and emits a successor link. |
| `POST /students/me/recommendations` | Student role required; uses only the caller's saved profile and accepts `top_k` 1–10. This is the current frontend route. |
| `POST /recommendations/roadmap/researcher` | Public read-only operation, based on the stored researcher row; request body is subject to the 64 KiB global cap. |
| Registration/login | Public endpoints, rate-limited before password hashing/verification by IP and normalized email. Only student/faculty registration is allowed. |
| Logout/session and student/faculty profile routes | Bearer session required; token expiry and logout revocation enforced. Profile routes are role-specific and bind profile ownership to the authenticated user. Unknown `user_id`/`role` body fields are rejected. |

### Rate limiting, inputs, and secrets

- Atomic fixed-window counters are stored as HMAC-SHA256 bucket hashes in
  `rate_limit_counters`; raw IP addresses and email addresses are not stored in
  the limiter table. Limits are 5 registrations/IP+email/hour, 10 logins/IP+email
  per 15 minutes, and 8 recommendations/IP+student per 5 minutes. A request over
  its limit receives HTTP 429 and `Retry-After`.
- The database-backed upsert is shared across processes and instances only when
  they use the same PostgreSQL database. Render configuration now requires that
  dialect and returns not-ready/fails closed if the service is connected to
  SQLite. No Redis or other external limiter service was added.
- Render must have a generated random `RATE_LIMIT_HASH_SECRET` of at least 32
  bytes. `RATE_LIMIT_TRUST_CF_CONNECTING_IP=true` is set in `render.yaml`; only
  that validated header is trusted when configured, and `X-Forwarded-For` is
  ignored. Render's inbound proxy and client-IP behavior is described in
  [Render's proxy-header guidance](https://render.com/articles/host-pocketbase-on-render)
  and [Cloudflare's request-header docs](https://developers.cloudflare.com/fundamentals/reference/http-headers/).
- `MAX_REQUEST_BODY_BYTES` defaults to 65,536. Missing/short limiter secret,
  unsupported DB, or wrong DB dialect returns 503 and readiness fails.
- The current database startup uses `Base.metadata.create_all`; it adds the
  limiter table without changing researcher rows. Tests use a throwaway SQLite
  file. No project, production or user database was opened by this phase.

### Authentication and frontend token assessment

- Passwords are salted PBKDF2-HMAC-SHA256 digests (600,000 iterations); opaque
  bearer tokens are random and stored only as SHA-256 digests. Logout revokes
  sessions and expired sessions are rejected. Cross-account student profile
  isolation and student/faculty role walls are covered by tests.
- The frontend still stores only the bearer token in `sessionStorage`; passwords
  are not stored. JavaScript on the frontend origin can read that token, so an
  XSS can steal it. No frontend token-storage change was needed for this phase.
  A cookie migration needs coordinated credentialed CORS and CSRF protection;
  the current Netlify and Render origins were not reconfigured for it.

### Tests and remaining risks

- Canonical Python 3.11.9 full run from `backend/`:
  `C:\Users\Venkatesh\researchtwin-venv311\Scripts\python.exe -m pytest -q`
  → **156 passed, 2 warnings**. The warnings are Starlette's `httpx` TestClient
  deprecation and AnyIO's `BlockingPortal` alias deprecation.
- Root frontend command `node --test tests/frontend/api-client.test.cjs`
  → **13 passed, 0 failed**. This includes the retained public researcher
  directory and authenticated saved-profile recommendation call.
- An initial focused run reported 73 passed/21 failed because several old tests
  still sent anonymous legacy recommendations or included `top_k` in a strict
  profile-save body; one import assertion also reused a marker across parameterized
  cases. Tests were corrected; the focused rerun passed 94 tests,
  the final security-specific file passed 23 tests, and the final full run above
  passed.
- Live Render/Netlify state, configured secret/database values, and deployed
  route behavior remain **unverified**. The admin role has no in-app provisioning
  flow; an operator must provision it securely out of band if maintenance is
  needed. `sessionStorage` XSS exposure remains. No deployment occurred.

### Exact next phase

**Phase F — Production configuration and release verification:** confirm shared
PostgreSQL and the generated limiter secret in Render; provision an administrator
out of band only if needed; deploy through the approved release process; then
verify readiness, CORS, authentication, profile isolation, rate limits, public
researcher reads, and recommendations against the deployed API and frontend.

---

## Addendum — Phase G readiness roadmap, collaboration and progress (2026-10-31)

Scope requested: complete the remaining development tasks (§3 readiness roadmap,
§4 student workflow, §5 faculty workflow, §6 collaboration workflow, §7 roadmap
progress, §8 recommendation integration, §9 database and backend quality) inside
the existing application. Nothing was rebuilt, committed, pushed, or deployed.

### What was actually broken at the start of the phase

| Finding | Evidence |
|---|---|
| Roadmap endpoint trusted client-supplied skill lists | `api/students.py` echoed the body's `matched_skills` into the response |
| Roadmap endpoint passed an empty student skill string | `calculate_skill_gap("", researcher)` made every researcher skill a "gap" and every matched list empty — the exact defect named in the request |
| Roadmap endpoint was unauthenticated | no role dependency, no saved-profile lookup |
| No roadmap UI existed | zero `roadmap` matches anywhere under `frontend/` |
| No collaboration workflow existed | no model, route or view for student requests or faculty decisions |
| No progress persistence existed | milestones were static text; nothing survived a refresh |

### Design constraint that shaped §6 and §7

There is no migration tool — `Base.metadata.create_all` runs at import. It creates
missing tables but never adds a column to an existing one, so a new
`researchers`/`users` column would be silently absent from every existing
database. All Phase G state therefore lives in three **new** tables instead of
added columns: `faculty_researcher_links`, `collaboration_requests`,
`roadmap_progress`.

The link table exists because the login account and the directory record are
separate entities by design. Without an explicit, verifiable claim there is no
honest way to resolve "requests addressed to me", and a name match would deliver
requests to the wrong person. One faculty account links one record; one record
has one owner (both columns are unique).

### Files changed

Backend: `app/models.py` (3 tables), `app/schemas.py` (5 payloads),
`app/services/skill_gap.py` (`student_skills_provided`),
`app/services/readiness_roadmap.py` (`build_student_roadmap`, `_attach_progress`,
`milestone_bounds`), `app/api/students.py` (legacy roadmap route), new
`app/api/roadmap.py`, new `app/api/collaboration.py`, `app/api/researchers.py`
(server-side `search`, wildcard-escaped `ilike` on every filter), `app/main.py`
(two routers registered).

Frontend: `api-client.js` (8 new methods), `researchtwin.html` (roadmap panel with
milestone checkboxes and progress bar, per-card request form, student "My
Requests" view, faculty "Collaboration Requests" inbox with the record-claim
panel, two nav entries, CSS for the new blocks).

Tests: new `tests/test_roadmap_progress.py` (13 tests) and
`tests/test_collaboration.py` (17); `test_researchers_api.py` gained the
free-text/wildcard test; `test_recommendations_api.py` gained the
auth-required and client-lists-ignored tests; `test_acceptance.py` gained the
faculty-rejected-from-student-route test; `test_imports_and_routes.py` endpoint
set extended by the 7 new routes; `tests/frontend/api-client.test.cjs` gained 7
client tests.

### New API surface

```
GET  /students/me/researchers/{researcher_id}/roadmap
PUT  /students/me/researchers/{researcher_id}/roadmap/progress
POST /students/me/collaboration-requests
GET  /students/me/collaboration-requests
PUT  /faculty/me/researcher-link
GET  /faculty/me/researcher-link
GET  /faculty/me/collaboration-requests?status=pending|accepted|rejected
PUT  /faculty/me/collaboration-requests/{request_id}/decision
```

`POST /recommendations/roadmap/researcher` is retained for compatibility: it now
requires a student session, derives matched and missing skills from the saved
profile, ignores the body's skill lists, and returns `Deprecation: true` with the
successor `Link` header — the same pattern the legacy recommendation route uses.

A roadmap response now carries researcher identity, `matched_skills`,
`researcher_skills`, `student_skills_provided`, and for each gap skill the
priority, reason, milestones (each with `index`, `text`, `completed`), suggested
mini-project, completion criteria and per-item milestone counts, plus a `progress`
object with total, completed and `completion_percentage`.

### Empty-skill defect, fixed and demonstrated

A student whose saved profile lists no skills receives
`student_skills_provided: false`, an empty `skill_gaps` array and the message
"Add your technical skills to your student profile before a skill gap can be
computed for this researcher." instead of a fabricated gap for every researcher
skill. Recommendation cards were deliberately not changed: `recommendation.py`
already passed the student's real skill string, so their gap lists stay as
previously verified.

### Verification actually run

- `python -m pytest -q` under `C:\Users\Venkatesh\researchtwin-venv311`
  (Python 3.11.9): **189 passed**, 0 failed, 0 skipped. The baseline measured at
  the start of this phase was 156 passed, so this is +33 net new tests.
- `node --test tests/frontend/api-client.test.cjs`: **19 pass, 0 fail** (was 12).
- Browser E2E: `uvicorn` on 127.0.0.1:8799 with `DATABASE_URL` pointed at a
  **copy** of `backend/researchtwin.db` inside a scratch directory, static server
  on 127.0.0.1:5510, `FRONTEND_ORIGINS` restricted to that origin. The repository
  database was never opened for writing; the scratch directory was deleted
  afterwards (30 researchers copied, 2 users and 1 request/1 progress/1 link row
  created in the copy only).

| Browser step, driven through the page's own handlers | Result |
|---|---|
| Student register, save profile with skills `Python, SQL` | 86% completion, written to the database |
| Refresh recommendations | 5 cards; top "Dr. Anil Kumar 81.1% model score"; matched `python`; gaps `opencv`, `pytorch`, `tensorflow` |
| Open "Readiness roadmap" on a card | 3 gap items with priorities, reasons, 3 milestones each, mini-project, 3 completion criteria; "Roadmap 0%" |
| Tick the first `pytorch` milestone | "Roadmap 11%", "1 of 9 milestones", row struck through |
| Reload page, session restored, reopen roadmap | still 11% and still checked — progress lives on the server |
| Open a second card's roadmap | that researcher at 0% with its own gaps (`pandas`, `scikit-learn`); first card still 11% |
| Send a collaboration request from a card | 201; inline pending record |
| Student "My Requests" after the reload | 1 request, pending, message shown |
| Faculty register, open inbox while unlinked | guidance text plus 10 directory candidates each with "This is me" |
| Faculty claims "Dr. Anil Kumar" | link stored; inbox shows the request with the student's research profile and no email |
| Faculty accepts with a reply | status `accepted`, reply persisted and displayed |
| Student signs in again, opens My Requests | `accepted` plus the faculty reply |
| Anonymous `GET …/roadmap` | 401 |
| Student token on `GET` and `PUT /faculty/me/collaboration-requests…` | 403 on both |
| `GET …/researchers/999999/roadmap` | 404 "Researcher not found" |
| `PUT …/roadmap/progress` for a skill outside the roadmap | 404 "That milestone is not part of your current roadmap" |
| Blank-skill student requesting a roadmap | `student_skills_provided:false`, zero gaps, guidance message |
| Console | only the deliberate 4xx probe entries; no uncaught exceptions |

### Still not true after this phase

- Access control was verified **locally only**. Render and Netlify were not
  probed and stay unverified; the earlier production findings (HTTP 500 on the
  deployed recommendation route, stale deploy, Netlify 401) stand until an
  approved release is run.
- Researcher create/update/delete/import now require `require_admin`, but
  registration cannot create an admin. Until an operator provisions that account
  out of band, directory content can only arrive through the import the
  deployment runs — and faculty claims depend on that content existing.
- Progress rows are keyed by (student, researcher, skill, milestone index). If a
  researcher's `skills` text is edited, milestones for a removed skill are no
  longer displayed while their rows remain in the database.
- The faculty inbox shows the requester's research profile but not their email,
  so replies stay inside the application; nothing notifies the student that a
  reply arrived — they must open "My Requests".
- `researchtwin.html` has no DOM test harness; the matrix above is manual
  evidence, and a mobile viewport could not be exercised with the available
  tooling.
