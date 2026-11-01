# Database verification — ResearchTwin

Verified: 2026-10-28
Scope: database configuration, files, schema, initialization, sessions, migrations,
production persistence, failure behavior, and recommendation ID integrity.
Method: read-only inspection of the real databases, non-destructive tests against
throwaway SQLite files, and one temporary copy of the real dataset. No production
data was written, migrated, seeded, or deleted.

## 1. Verified database files and configuration

| File | Size | Rows | Role |
|---|---|---|---|
| `backend/researchtwin.db` | 24,576 B | **30** (ids 1–30) | The database the local app actually opens |
| `researchtwin.db` (project root) | 12,288 B | **0** | Unused artifact from the old cwd-relative default; do not operate on it |

Both files: table `researchers` only, `PRAGMA integrity_check = ok`,
`journal_mode = delete`, index `ix_researchers_id`. No WAL/SHM files exist.

Configuration precedence (one source at a time):

1. `DATABASE_URL` environment variable, normalized by
   [resolve_database_url](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/database.py#L11):
   blank → default; `postgres://` / `postgresql://` → `postgresql+psycopg://`;
   anything else unchanged.
2. Default when unset: SQLite at
   `backend/researchtwin.db`, resolved relative to the package
   ([database.py:6](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/database.py#L6)).
3. Tests: `backend/tests/conftest.py` sets `DATABASE_URL` to a throwaway file in
   `%TEMP%\researchtwin-tests-*` **before** importing the app.

There are no `.env`, `.env.*`, or committed database URLs in the repository, and
`*.db` is gitignored at the root and under `backend/`. `psycopg[binary]` is pinned
in `requirements.txt`, so the PostgreSQL URL rewrite has a working driver.

Test and audit artifacts outside the repo: `%TEMP%\researchtwin-tests-*` (created
per pytest run by `conftest.py`, 17 directories present; only seeded fixture rows),
plus two throwaway copies created for this audit (`rt-db-audit-copy.db`,
`rt-db-import-audit.db`).

## 2. Which database the running local application opens

Verified by starting `uvicorn app.main:app` with `DATABASE_URL` unset:

```
engine URL: sqlite:///C:/Users/Venkatesh/ResearchTwin/backend/researchtwin.db
GET /health            -> 200 {"status":"healthy"}
GET /researchers/      -> 200, 30 rows, ids 1–30, 0 null/blank names
```

MD5 of both database files was captured before and after the live run and
re-verified with `md5sum -c` — **both unchanged**. Reads do not modify the files.

## 3. Production database configuration (no credentials read or printed)

`render.yaml` declares a single web service with:

- `rootDir: backend`, `startCommand: uvicorn app.main:app`, `healthCheckPath: /health`
- `DATABASE_URL: sync: false` — the value lives only in the Render dashboard and
  is **not recoverable from the repository**
- `FRONTEND_ORIGINS: sync: false`
- **no `disk:` mount** — the container filesystem is ephemeral

Consequences:

- If `DATABASE_URL` points at PostgreSQL, data is durable and the URL rewrite is correct.
- If `DATABASE_URL` is unset, the app creates an empty SQLite file inside the
  container on each boot. The DB is gitignored, so it is not in the repo/image;
  an empty DB yields `200` with `recommendations: []` until someone imports, and
  all rows disappear on the next deploy/restart.
- The deployed API did not answer `/health` within 20 s (`HTTP 000`) during this
  audit, so the live engine and row count could not be confirmed from outside.
  Production DB identity remains **unverified pending dashboard access**.

## 4. Schema and record counts

`researchers` ([models.py:6](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/models.py#L6)):

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | primary key, indexed |
| `name` | VARCHAR(100) | NOT NULL |
| `department` | VARCHAR(150) | nullable |
| `designation` | VARCHAR(100) | nullable |
| `experience` | INTEGER | nullable |
| `research_areas`, `expertise`, `skills`, `publications`, `projects` | TEXT | nullable |
| `profile_url` | VARCHAR(300) | nullable |

Observed data (read-only): 30 rows, ids 1–30 contiguous, 0 null/blank names, no
duplicate names, `integrity_check = ok`. There are **no unique constraints, no
foreign keys, and no indexes other than `ix_researchers_id`**. Duplicate names are
therefore legal at the schema level.

## 5. Initialization does not erase records

Initialization is `Base.metadata.create_all(bind=engine)` at import time
([main.py:24](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L24)).
`create_all` issues only `CREATE TABLE`/`CREATE INDEX` for missing objects.

- Test `test_create_all_is_idempotent_and_preserves_existing_rows` inserts a row,
  runs `create_all` again, and confirms the row is still present. **Pass.**
- Live run left both database files byte-identical (section 2).
- No `drop_all`, truncate, reset, or seed-on-boot code exists in `backend/app`.

Fail-fast caveat: because initialization runs at import, an unreachable database
prevents the app from starting at all (verified in
`test_create_all_fails_fast_when_database_file_cannot_be_opened`). `/health`
cannot report `unhealthy` in that state because the process never serves.

## 6. Sessions and error handling

- `get_db` yields a `SessionLocal` and always closes it in `finally`
  ([database.py:45](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/database.py#L45)).
  Closing rolls back any uncommitted transaction. Verified for normal exhaustion
  and for a handler raising mid-request (new test).
- Sessions use `autocommit=False`, `autoflush=False`, `pool_pre_ping=True`.
- Write paths commit explicitly (`POST/PUT/DELETE /researchers`, CSV import);
  the import endpoint rolls back on failure
  ([researchers.py:215](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/researchers.py#L215)).
- **Fixed:** a database failure during a request previously surfaced as a bare
  `500 Internal Server Error`, and `/health` reported `healthy` without touching
  the database. Added a `SQLAlchemyError` → `503 {"detail":"Database unavailable"}`
  handler and a `SELECT 1` probe in `/health` that returns
  `503 {"status":"unhealthy"}` ([main.py:56](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L56),
  [main.py:87](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py#L87)).
  Errors are logged by exception type and route only — no DSN, SQL, or parameters.

## 7. Migrations

There is **no migration workflow**: no Alembic, no migration directory, no schema
version table. Schema changes are applied only by `create_all`, which does not
alter existing tables. A future column/index change therefore requires a manual
migration or a rebuilt database.

Current risk is low (single table, no schema changes pending), but any change to
`models.py` will not reach the production database automatically.

## 8. Data and production risks

| # | Risk | Evidence | Severity |
|---|---|---|---|
| D1 | Import is not idempotent: importing the same CSV twice doubled rows to 60 (30 duplicates) | temp-DB measurement | High |
| D2 | Write/import/delete endpoints are unauthenticated (`POST/PUT/DELETE /researchers`, `POST /researchers/import`, public) | [researchers.py:23](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/api/researchers.py#L23) | High |
| D3 | If production runs SQLite (no `DATABASE_URL`), data is on ephemeral storage and is lost on deploy/restart | `render.yaml` has no `disk:`; DBs gitignored | High |
| D4 | Production database identity/row count cannot be confirmed from the repo or externally | `DATABASE_URL: sync: false`; deployed API unreachable | Medium |
| D5 | Root `researchtwin.db` is empty and looks like the app DB; operating on it would silently lose changes | 0 rows, not opened by the app | Medium |
| D6 | No unique constraint on `name`; duplicates are permitted and imports append | schema inspection; D1 | Medium |
| D7 | No backup/restore or seed-at-deploy procedure; a fresh instance has 0 researchers unless the DB is pre-populated | no seed step; `create_all` only | Medium |
| D8 | Database outage at startup crashes the process before `/health` can report it | fail-fast test | Low |
| D9 | SQLite `journal_mode=delete`, default 5 s busy timeout; concurrent writes (e.g., import during traffic) can raise lock errors (now surfaced as 503) | pragma + SQLAlchemy defaults | Low |
| D10 | Test runs leave throwaway DB directories in `%TEMP%` (17 present) | `conftest.py` `mkdtemp` | Low |

## 9. Test results

Environment A: existing `backend\.venv` (Python 3.14, scikit-learn 1.9.1).
Environment B: isolated `C:\Users\Venkatesh\researchtwin-venv311` (Python 3.11, pinned scikit-learn 1.7.2).

| Run | Result |
|---|---|
| `tests/test_database_reliability.py` (RED, before fix) | 3 failed (health 200; list/recommend 500), 5 passed |
| same file after fix | **8 passed** |
| Full suite, Environment A | **82 passed, 2 skipped** (pinned-only model tests skip under 1.9.1) |
| Full suite, Environment B | **84 passed** (includes pinned model tests) |
| Idempotent init / fail-fast / session rollback | pass |
| Empty database endpoint | `200`, `recommendations: []` |
| DB unavailable: `/health`, `/researchers/`, `/recommendations/researchers` | `503` with documented bodies |
| Recommendation IDs on the real 30-row dataset (temporary copy) | ids `[1, 18, 30, 20, 26]`; all exist, names/departments match; unique; 8 explanation features each; scores 0.865/0.5624/0.5485/0.4657/0.4629 |
| File integrity after live run | `md5sum -c` OK for both databases |

## 10. Reproduce

All commands from `backend/`.

```bash
# new database reliability tests
.venv/Scripts/python.exe -m pytest tests/test_database_reliability.py -v

# full suites
.venv/Scripts/python.exe -m pytest -q
C:/Users/Venkatesh/researchtwin-venv311/Scripts/python.exe -m pytest -q

# which DB the app opens (no secret printed)
.venv/Scripts/python.exe -c "from app.database import engine; print(engine.url.render_as_string(hide_password=True))"

# read-only inspection of both databases
.venv/Scripts/python.exe - <<'PY'
import sqlite3, os
for p in ["researchtwin.db", "../researchtwin.db"]:
    con = sqlite3.connect("file:" + os.path.abspath(p).replace("\\","/") + "?mode=ro", uri=True)
    print(p, con.execute("select count(*) from researchers").fetchone()[0], con.execute("pragma integrity_check").fetchone()[0])
    con.close()
PY

# duplicate-import risk, throwaway DB only
.venv/Scripts/python.exe - <<'PY'
import os, tempfile
p = os.path.join(tempfile.gettempdir(), "rt-import-demo.db")
if os.path.exists(p): os.remove(p)
os.environ["DATABASE_URL"] = "sqlite:///" + p.replace("\\", "/")
import app.main
from app.database import SessionLocal
from app.models import Researcher
from app.services.researcher_import import import_researchers
s = SessionLocal()
try:
    print(import_researchers("data/researchers.csv", s), import_researchers("data/researchers.csv", s))
    print("rows:", s.query(Researcher).count(), "distinct:", s.query(Researcher.name).distinct().count())
finally:
    s.close()
PY
```

Expected duplicate-import output: `30 30`, `rows: 60 distinct: 30`.

## 11. Changed files

| File | Change |
|---|---|
| [backend/app/main.py](file:///C:/Users/Venkatesh/ResearchTwin/backend/app/main.py) | DB-error → 503 handler; `/health` now probes the database and returns 503 when unavailable |
| [backend/tests/test_database_reliability.py](file:///C:/Users/Venkatesh/ResearchTwin/backend/tests/test_database_reliability.py) | 8 non-destructive tests (init idempotency, fail-fast, rollback/close, 503 behavior, empty DB, ID/explanation integrity) |
| [backend/TESTING.md](file:///C:/Users/Venkatesh/ResearchTwin/backend/TESTING.md) | New test file and database failure status rows |
| `DATABASE_VERIFICATION.md` | This report |

No production data was touched. No files were staged, committed, pushed, or
deployed. No database was deleted, migrated, seeded, or overwritten.

## 12. Remaining tasks (approval-gated)

1. Confirm in the Render dashboard whether `DATABASE_URL` points at PostgreSQL
   and record the database's storage class; keep the value out of the repo.
2. Add a persistent disk or guarantee PostgreSQL before relying on production data
   across deploys.
3. Make the import idempotent (unique constraint on a stable natural key, or
   upsert-by-name) and remove or authenticate `POST /researchers/import`.
4. Add authentication/authorization to researcher write endpoints.
5. Introduce Alembic (or an explicit migration script) and a version table before
   the next schema change.
6. Add a documented backup/restore procedure and an idempotent seed step for new
   environments.
7. Decide whether startup should fail fast (current) or start degraded and let
   `/health` report `unhealthy`.
8. Update `conftest.py` to remove its throwaway DB directory on exit, or document
   cleanup of `%TEMP%\researchtwin-tests-*`.

---

## Addendum — authentication/profile tables (2026-10-28)

Four new tables are created by `Base.metadata.create_all` at application import:

| Table | Columns (summary) | Constraints |
|---|---|---|
| `users` | `id, email, full_name, role, password_hash, is_active, created_at` | `email` unique |
| `auth_sessions` | `id, user_id, token_hash, created_at, expires_at, revoked_at` | `token_hash` unique; `user_id` FK |
| `student_profiles` | `id, user_id, research_areas, expertise, skills, projects, publications, courses, academic_details, updated_at` | `user_id` unique FK |
| `faculty_profiles` | `id, user_id, department, designation, research_areas, expertise, skills, publications, projects, profile_url, updated_at` | `user_id` unique FK |

Non-destructive properties verified by the suite:

- `create_all` remains idempotent and preserves existing `researchers` rows
  (`test_create_all_is_idempotent_and_preserves_existing_rows`).
- No existing table is altered, dropped, or reseeded.
- Auth/profile tests run against the throwaway `%TEMP%` database; they never
  open `backend/researchtwin.db`.
- Session tokens are stored only as SHA-256 digests; password hashes are
  PBKDF2-HMAC-SHA256 with per-user salts.

Migration position: **no migration is needed to add these brand-new tables** —
starting the updated app against an existing database creates them. The project
still has no Alembic setup, so any future change to an existing column or
constraint must add one before it is applied to real data.

To inspect the new schema after starting the app locally:

```bash
python -c "import sqlite3; c=sqlite3.connect('researchtwin.db'); print([r[0] for r in c.execute(\"select name from sqlite_master where type='table' order by name\")])"
```

## Addendum — Phase D (2026-10-28)

Phase D changed no schema, migration, seed data, or database code. The browser
end-to-end run used a copy of `backend/researchtwin.db` in `%TEMP%`; the
repository database kept its original 24,576-byte size and 2026-09-17 timestamp,
and `researchers` still held 30 rows. On the copy, `create_all` added the four
new tables, and the flows persisted:

- 2 `users` (one student, one faculty)
- 1 `student_profiles` row with the edited skills
- 1 `faculty_profiles` row with department and designation
- `auth_sessions` rows with `revoked_at` set after sign-out

No production database was contacted, and nothing was staged, committed,
pushed, or deployed.

## Addendum — Phase G roadmap and collaboration tables (2026-10-31)

Phase G added three tables. Nothing was renamed, altered, dropped, reseeded or
deleted in an existing table, and no migration tool was run — there still is no
Alembic setup, so `Base.metadata.create_all(bind=engine)` remains the only
initialization path. It creates missing tables and leaves existing ones
untouched.

| Table | Columns | Constraints |
| --- | --- | --- |
| `faculty_researcher_links` | `id, faculty_user_id, researcher_id, created_at` | Both FKs `ondelete="CASCADE"`; each column individually `unique`, so one faculty owns at most one directory record and one record has at most one owner |
| `collaboration_requests` | `id, student_user_id, researcher_id, message, status, faculty_response, reviewed_at, created_at, updated_at` | FKs to `users.id` and `researchers.id` with `ondelete="CASCADE"`; `status` defaults to `pending` and is indexed |
| `roadmap_progress` | `id, user_id, researcher_id, skill, milestone_index, is_completed, updated_at` | FKs with `ondelete="CASCADE"`; `UniqueConstraint(user_id, researcher_id, skill, milestone_index)` named `uq_roadmap_progress_milestone` makes milestone writes idempotent upserts instead of duplicate rows |

Non-destructive behaviour confirmed by the Phase G tests:

- `test_create_all_is_idempotent_and_preserves_existing_rows` still passes, so
  starting the updated app against an existing database adds these three tables
  without touching `researchers`.
- No migration is required to add them; a deployed instance creates them on
  first start against its own database.
- Ownership is enforced in queries, not inferred from client parameters:
  `collaboration_requests` rows are always filtered by the authenticated
  `student_user_id`, and a faculty decision is rejected with `403` unless the
  request's `researcher_id` matches that faculty member's own
  `faculty_researcher_links` row.
- `roadmap_progress.skill` is stored from the server-recomputed roadmap, not
  from the client payload, so a client cannot persist progress for a skill or
  milestone index that is not currently in the student's roadmap.

Verification for this phase ran against a throwaway copy of
`backend/researchtwin.db` in a temporary directory (the browser journey) and
against `%TEMP%` fixtures (the pytest suite). The repository database was never
opened for writing. A known trade-off carried forward: `roadmap_progress` rows
are keyed by the `(skill, milestone_index)` pair, so if a researcher's `skills`
text is edited later, previously completed milestones for a removed or reordered
skill become orphans that no longer render. They are inert, not incorrect, but
no retention job exists for them.

Nothing was staged, committed, pushed, or deployed in Phase G.
