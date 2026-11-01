# ResearchTwin browser verification

This standalone Playwright journey runs against a local frontend and API using
an isolated SQLite database. It intentionally refuses a non-SQLite database or
a database URL outside the operating system temporary directory. Do not point
it at `backend/researchtwin.db` or any shared database.

Prerequisites: Node.js, the repository's existing Playwright dependency and
Chromium, and the canonical Python 3.11 environment with backend requirements.

1. Choose a new temporary directory and set its database URL explicitly:

   ```powershell
   $phase3Dir = Join-Path $env:TEMP ('ResearchTwin-Phase3-' + [guid]::NewGuid().ToString('N'))
   New-Item -ItemType Directory -Path $phase3Dir | Out-Null
   $env:DATABASE_URL = 'sqlite:///' + ($phase3Dir.Replace('\', '/') + '/application.sqlite')
   $env:RATE_LIMIT_HASH_SECRET = [guid]::NewGuid().ToString('N')
   $env:RATE_LIMIT_REQUIRE_SHARED_DATABASE = 'false'
   $env:RATE_LIMIT_TRUST_CF_CONNECTING_IP = 'false'
   # Higher limits prevent this multi-journey browser run from exhausting
   # the shared local test IP bucket. Backend tests cover the production limits.
   $env:RATE_LIMIT_REGISTER_MAX = '100'
   $env:RATE_LIMIT_LOGIN_MAX = '100'
   $env:RATE_LIMIT_RECOMMENDATION_MAX = '100'
   $env:FRONTEND_ORIGINS = 'http://127.0.0.1:5500'
   ```

2. From `backend`, start the API. This first startup creates the schema in the
   isolated database:

   ```powershell
   C:\Users\Venkatesh\researchtwin-venv311\Scripts\uvicorn.exe app.main:app --reload --port 8000
   ```

3. From another terminal, set the same `DATABASE_URL`, enable the CLI, and
   provision the test administrator. Use a test-only password of at least 16
   characters. The CLI prompts for the password without echoing it:

   ```powershell
   $env:DATABASE_URL = 'sqlite:///C:/.../ResearchTwin-Phase3-.../application.sqlite'
   $env:RESEARCHTWIN_ENABLE_ADMIN_PROVISIONING = 'YES'
   C:\Users\Venkatesh\researchtwin-venv311\Scripts\python.exe .\provision_admin.py
   ```

4. From the repository root, start the documented static frontend server:

   ```powershell
   npx serve frontend --listen 5500 --no-clipboard
   ```

5. In a third terminal, set the E2E variables and run the browser journey:

   ```powershell
   $env:RT_PHASE3_DATABASE_URL = $env:DATABASE_URL
   $env:RT_PHASE3_ADMIN_EMAIL = '<temporary admin email>'
   $env:RT_PHASE3_ADMIN_PASSWORD = '<temporary admin password>'
   $env:RT_PHASE3_PYTHON = 'C:\Users\Venkatesh\researchtwin-venv311\Scripts\python.exe'
   $env:RT_PHASE3_ARTIFACT_DIR = Join-Path $phase3Dir 'artifacts'
   node tests/e2e/researchtwin.phase3.e2e.cjs
   ```

The test registers temporary student and faculty users, imports bundled
researchers as the temporary admin, checks role denials and duplicate import,
and exercises the UI journeys. If a browser assertion fails, it saves a full
page screenshot and Playwright trace in `RT_PHASE3_ARTIFACT_DIR`.

The current `README.md` installation section contains stale setup instructions
(`init_db()` and an obsolete import route); use this tested procedure until
those instructions are reconciled.
