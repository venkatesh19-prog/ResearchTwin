# ResearchTwin 2.0 — Final Handover

**Release:** `v2.0.0` (tag on commit `9a47c52`) · **Date:** 2026-11-12 · **Status:** accepted in production

Each section is a summary; the linked documents have the detail.

## 1. Overview and architecture

ResearchTwin is a researcher–student collaboration platform:
- students get ranked, explained researcher matches and skill-gap roadmaps;
- students and faculty collaborate through requests, workspaces, teams, opportunities and research-output tracking;
- administrators manage accounts, verification and institutions.

| Layer | Technology |
|---|---|
| Frontend | Static HTML and vanilla JavaScript (`frontend/`), no build step |
| Backend | FastAPI, SQLAlchemy 2, Alembic, psycopg 3 (`backend/`), Python 3.11 |
| ML | Logistic model on 7 similarity features, ONNX MiniLM embeddings, SHAP explanations |
| Database | PostgreSQL (Neon) in production; SQLite locally and in tests |

The server enforces every role and ownership rule; the browser never authorizes anything. Details: `ARCHITECTURE.md`, `API_DOCUMENTATION.md` (152 operations), `DATABASE.md` (43 tables, 12 migrations).

## 2. Feature areas (all PASS)

| # | Area | # | Area |
|---|---|---|---|
| 1 | Admin groups and role management | 9 | Literature library |
| 2 | Researcher verification | 10 | Research proposals |
| 3 | Workspaces | 11 | Thesis management |
| 4 | Teams and collaborator recommendations | 12 | Publications |
| 5 | Opportunities and eligibility | 13 | Research labs |
| 6 | Applications | 14 | Institutions |
| 7 | Research intelligence | 15 | Inter-university collaborations |
| 8 | Analytics | 16 | Search history |

Roles, routes and behaviour: `FEATURES.md`. Instructions per role: `USER_GUIDE.md`.

## 3. Deployment

| Part | Where | Version |
|---|---|---|
| Frontend | Netlify site `starlit-empanada-a323e3`, https://starlit-empanada-a323e3.netlify.app/researchtwin.html | `b4891e5` |
| Backend | Render service `researchtwin-api`, https://researchtwin-api.onrender.com | `9d3a5f5` |
| Database | Neon project `super-hill-93410289`, branch `production`, endpoint `ep-floral-thunder-bddca63h`, database `neondb` | Alembic `0012_search_history` |
| Source | GitHub `venkatesh19-prog/ResearchTwin`, `main` | `9a47c52` |

- **Deploy controls:** Render auto-deploy is **Off** and Netlify auto-publishing is **Locked**. Releases are deployed by hand.
- **Secrets:** stored only in the Render dashboard and in operator-held files outside the repository.
- **Not yet deployed:** commits after `9d3a5f5` add only documentation, the manual demo scripts and one error-message fix (`9487f2d`).

Procedures: `DEPLOYMENT.md`.

## 4. Test results

| Suite | Result |
|---|---|
| Backend `pytest` (pinned Python 3.11 environment) | 531 passed |
| Frontend `npm test` | 132 passed |
| Browser end-to-end `npm run test:e2e` | PASS, 13 journeys |
| Per-role API checks on production (read-only) | All roles see exactly their own data |
| Write and access-control journeys (replica of production) | 104 of 105 checks; the miss is a correct rate-limit refusal |
| Browser view sweep (replica of production) | 102 views across 6 roles, 0 errors |
| Production data integrity | Clean |

Details and commands: `TESTING.md`.

## 5. Role-based acceptance (production)

| Role | Live sign-in and workflow checklist |
|---|---|
| Student | PASS |
| Faculty | PASS |
| Admin | PASS |

Completed by the project owner on 2026-11-12 (`TESTING.md`).

## 6. Setup and demonstration

**Local setup** (README "Quick start"):
1. Create a Python 3.11 virtual environment.
2. Run `pip install -r backend/requirements.txt -c backend/constraints.txt`.
3. Run `python backend/scripts/fetch_embedding_model.py`.
4. Start the backend: `uvicorn app.main:app --port 8000` from `backend/`. It uses local SQLite by default.
5. Serve `frontend/` on `http://127.0.0.1:5500`.
6. Create an admin with `backend/provision_admin.py`.

**Demonstration:** use the production demo accounts, whose passwords are held by the project owner. The suggested walkthrough is in `USER_GUIDE.md` → Demo accounts:
1. **Student:** recommendations, then the workspace, then opportunities and applications, then thesis and proposal.
2. **Faculty:** collaboration requests, then labs and inter-university collaborations, then publications and verification.
3. **Admin:** accounts, groups, verifications, analytics and research intelligence.

All demo content is fictional and marked `[DEMO]`. The real user account (id 7) holds no demo data.

## 7. Known limitations

- **Recommendation quality:** training labels are heuristic (`STB-68`). The quality score measures agreement with those labels, not real-world acceptance.
- **Client IP:** attribution behind Render's proxy is unverified (`STB-39`), so rate-limit buckets may be shared.
- **Data export:** the DSAR export omits 2.0 tables (`STB-47`).
- **Session policy:** absolute 12-hour sessions, no self-service password reset (`STB-66`).
- **Token storage:** the bearer token lives in `sessionStorage`, with a CSP that allows inline scripts.
- **Free hosting:** idle sleep (first request about 50 s) and builds of several minutes.
- **Audit attribution exception:** one demo-seeding audit event and the demo cluster run are attributed to the admin account. Kept unchanged by decision (`SECURITY.md`).
- **Open repository items:**
  - uncommitted `@neon/*` additions in `package.json` and `package-lock.json`;
  - untracked `neon.ts`, `test-script.js` and `backend/save_model_compat_test.py`;
  - tracked legacy root files and `supervised project/`, which are not deployed.
  
  All are left in place for the owner to decide.

## 8. Backup and rollback

- **Backups** (outside the repo, in `C:\Users\Venkatesh\ResearchTwinBackups\`, each with a SHA-256 manifest):
  - `researchtwin-neon-prod-preseed-20261112T093358Z.dump`: Neon production before demo data;
  - `researchtwin-prod-20261111T190259Z.dump`: final frozen Render cutover backup.
- **Old Render database:** still available for rollback until its plan expires on **2026-11-21**.
- **Rolling back code:**
  - **Render:** Manual Deploy → Deploy a specific commit.
  - **Netlify:** publish the previous deploy.
- **Rolling back data:** restore a verified dump into a **new** Neon branch, verify, then repoint `DATABASE_URL`. Never restore over the live database.

Full procedures: `BACKUP_AND_RECOVERY.md`.

## Document index

`README.md` · `ARCHITECTURE.md` · `FEATURES.md` · `API_DOCUMENTATION.md` · `DATABASE.md` · `DEPLOYMENT.md` · `TESTING.md` · `SECURITY.md` · `BACKUP_AND_RECOVERY.md` · `USER_GUIDE.md` · `RELEASE_NOTES.md` · `FINAL_HANDOVER.md`
