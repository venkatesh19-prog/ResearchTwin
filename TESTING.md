# ResearchTwin Testing

All results below were observed on 2026-11-12 against commit `00ae755`, except where a different target is named.

## Commands

| Suite | Command | Result |
|---|---|---|
| Backend (pytest) | `cd backend` then `python -m pytest -q` | **531 passed** |
| Frontend (Node test runner) | `npm test` | **132 passed** |
| Browser end-to-end (Playwright) | `npm run test:e2e` (see below) | **PASS**, 13 journeys |

### Backend environment
Run pytest with the pinned dependencies:

```powershell
python -m venv .venv311
.\.venv311\Scripts\python -m pip install -r backend\requirements.txt -c backend\constraints.txt
cd backend
..\.venv311\Scripts\python -m pytest -q
```

That's Python 3.11 with `requirements.txt` and `constraints.txt`, the same set Render installs.
- **A different environment gives different results.** On Python 3.14 without `onnxruntime` and with a different scikit-learn, 7 readiness and model-bundle tests fail.
- **Don't leave `DATABASE_URL` set.** The suite builds its own SQLite databases; an inherited `DATABASE_URL` or `RESEARCHTWIN_ENV_FILE` would point it elsewhere.

### End-to-end environment
`tests/e2e/researchtwin.phase3.e2e.cjs` drives Chromium against a local backend (`127.0.0.1:8000`) and the static frontend (`127.0.0.1:5500`). The database must be an isolated SQLite file.

Set these environment variables:

| Variable | Value |
|---|---|
| `RT_PHASE3_DATABASE_URL` | `sqlite:///<temp>.db`, the same file the backend uses |
| `RT_PHASE3_PYTHON` | the pinned Python 3.11 interpreter |
| `RT_PHASE3_ADMIN_EMAIL`, `RT_PHASE3_ADMIN_PASSWORD` | an administrator that exists only in that temporary database |
| `RT_PHASE3_ARTIFACT_DIR` (optional) | where to keep screenshots and traces |

**Journeys covered:**
- admin provisioning, authorization and duplicate-safe researcher import;
- invalid registration input;
- student registration, login, session restore and profile editing;
- network-failure handling;
- seven-feature recommendations with explanations (10 ranked results);
- directory details;
- roadmap generation with concurrent milestone locking and persisted completion;
- collaboration requests and duplicate rejection;
- faculty link, inbox and decisions;
- the admin account lifecycle, faculty links, audit log and export, with students denied the admin API;
- expired-session rejection;
- logout revocation for student and faculty.

**Last run:** 0 unexpected console errors, 0 page errors. Four expected failures were provoked deliberately: one network failure, a `409`, a `403` and a `401`.

## Release acceptance checks (2026-11-12)

These go beyond the committed suites. They used scripts kept outside the repository, run against production and against a replica. None used real passwords or wrote to production.

| Check | Target | Method | Result |
|---|---|---|---|
| Per-role data and ownership | **Production** (Neon) | Real FastAPI routes called in-process as users 1–6, inside a transaction that is always rolled back | Every role sees exactly its seeded records; workspace detail, roadmap (4 of 6 milestones), recommendations (5), analytics, clusters (19), network (30), knowledge graph (295 elements) |
| Write workflows and access control, all 16 areas | Local replica (production backup + the same seed) | Create, update and delete where allowed; wrong-role, cross-account and invalid-input refusals | 104 of 105 checks pass. The miss is the verification-submission rate limiter correctly returning `429` after repeated runs. |
| Every sidebar view per role | Local replica in Chromium | Sign in as each demo role and open every view | 102 views across 6 roles: 0 console errors, 0 failed API calls |
| Data integrity | **Production** (read-only SQL) | Foreign keys, duplicates, ownership rules, role groups, `[DEMO]` labelling, user 7 isolation | All clean |
| Before/after snapshot | **Production** | Hashes of `users`, all user-7 rows, and pre-existing sessions and audit rows | Unchanged |
| Health, CORS, CSP | **Production** (HTTPS) | `/health`, `/ready`, a foreign-origin CORS probe, response headers | Healthy; foreign origin refused; CSP has `frame-ancestors 'none'` |
| Sidebar layout | Live HTML, laptop and mobile | Playwright on the exact deployed `researchtwin.html` | Menu scrolls, Insights reachable, Sign out visible and revoking |

## Production acceptance (project owner)

**Status: PASSED** (2026-11-12). The project owner signed in to the live application with real student, faculty and admin accounts and completed the checklist below. They reported that all three roles passed the live sign-in and workflow verification.

| Role | Live sign-in | Workflow checklist | Result |
|---|---|---|---|
| Student | Passed | Passed | PASS |
| Faculty | Passed | Passed | PASS |
| Admin | Passed | Passed | PASS |

Only the owner's overall pass for each role is recorded. Details of individual steps beyond the checklist were not reported and aren't claimed here.

### Checklist used

Production sign-in needs real account passwords, which were never used by automated testing. The owner ran this checklist at https://starlit-empanada-a323e3.netlify.app/researchtwin.html:

1. **As a student** (Riya Kulkarni or Aditya Nambiar):
   - **ML Recommendations:** request recommendations.
   - **Workspaces:** open the workspace and check its tasks, milestones and comments.
   - **Opportunities, My Applications and Thesis Tracking:** check each shows that student's records.
2. **As a faculty member** (Dr. Priya Sharma, Dr. Aisha Khan or Dr. Rohan Gupta):
   - **Collaboration Requests:** check the incoming requests.
   - **Research Labs, Inter-university Collaborations and Publications:** check each shows the account's records.
   - **Researcher Verification:** check it shows "pending".
3. **As the admin:**
   - **Account Management:** shows 7 users.
   - **Groups:** shows exactly `students` (3) and `faculty` (3).
   - **Researcher Verification:** 2 pending.
   - **Analytics and Research Intelligence:** both populated.
4. **Sign out**, then sign in again with each role.

If a view looks empty, compare it with the expected counts in `RELEASE_NOTES.md`.
