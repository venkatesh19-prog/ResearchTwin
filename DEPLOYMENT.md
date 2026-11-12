# ResearchTwin Deployment

Production runs on three managed services. No credentials appear in this repository: connection strings and secrets live only in provider dashboards and in operator-held files outside the repo.

## Current production (verified 2026-11-12)

| Part | Service | Identifier | Version |
|---|---|---|---|
| Frontend | Netlify site `starlit-empanada-a323e3` | https://starlit-empanada-a323e3.netlify.app (app at `/researchtwin.html`) | commit `b4891e5` |
| Backend | Render web service `researchtwin-api` (`srv-dbcm5cfb9u1s73c5gqr0`, Singapore, free plan) | https://researchtwin-api.onrender.com | commit `9d3a5f5` |
| Database | Neon project `super-hill-93410289`, branch `production` (`br-little-waterfall-bdtwjbbf`), endpoint `ep-floral-thunder-bddca63h`, database `neondb` | — | Alembic `0012_search_history` |
| Source | GitHub `venkatesh19-prog/ResearchTwin`, branch `main` | — | `00ae755` |

`00ae755` adds three things on top of the deployed backend:
- the seed and repair scripts, which never run at deploy time;
- one changed error message in `backend/app/api/admin.py`;
- a test.

There are no frontend changes after `b4891e5`.

**Deploy controls**
- **Render:** auto-deploy is **Off**.
- **Netlify:** auto-publishing is **Locked**. Netlify still builds each push, but you publish by hand.

## Backend — Render

`render.yaml` declares the service:

| Setting | Value |
|---|---|
| Root directory | `backend` |
| Runtime | Python `3.11.11` (`PYTHON_VERSION`) |
| Build | `pip install -r requirements.txt -c constraints.txt && python scripts/fetch_embedding_model.py` |
| Start | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1` |
| Health check | `/ready` |

**Environment variables** (values are set in the dashboard, never in the repo):

| Name | Purpose |
|---|---|
| `DATABASE_URL` | Neon **direct** (unpooled) connection string with `sslmode=require` |
| `FRONTEND_ORIGINS` | Exact CORS origin: `https://starlit-empanada-a323e3.netlify.app` |
| `RATE_LIMIT_HASH_SECRET` | 32 or more random bytes; `/ready` fails without it |
| `RATE_LIMIT_REQUIRE_SHARED_DATABASE` | `true` (limiter requires PostgreSQL) |
| `RATE_LIMIT_TRUST_CF_CONNECTING_IP` | `false` until the proxy path is verified |
| `PYTHON_VERSION` | `3.11.11` |

**Optional:**
- `AUTH_SESSION_TTL_SECONDS` (default 12 hours);
- `RATE_LIMIT_*` maximums and windows (the code defaults match `render.yaml`);
- `MAX_REQUEST_BODY_BYTES` (default 65536);
- `RECOMMENDATION_MAX_CONCURRENCY` (default 2);
- `RATE_LIMIT_TRUSTED_PROXY_CIDRS` (empty);
- `FUNDING_GRANTS_GOV_ENABLED` (unset, which means off).

**Deploying a backend commit:**
1. Push the commit to `main`.
2. In Render, choose **Manual Deploy → Deploy a specific commit** and select it.
3. Watch the deploy log until "Your service is live". Render keeps the previous build if `/ready` never returns 200.
4. Check `GET /health`, `GET /ready` and `GET /openapi.json`. The route count should match the commit (110 for `9d3a5f5`).

**Free-plan behaviour**
- The instance sleeps when idle, so the first request after a pause can take about 50 seconds.
- Builds take 2–16 minutes.

## Frontend — Netlify

| Setting | Value |
|---|---|
| Repository / branch | `venkatesh19-prog/ResearchTwin`, `main` |
| Base directory / build command | `/` / none |
| Publish directory | `frontend` (`netlify.toml`) |
| Security headers | `frontend/_headers` (CSP, HSTS, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`) |

`frontend/frontend-config.js` maps the production hostname to the Render API. A different hostname fails closed until that file and the CSP `connect-src` are updated.

**Publishing a frontend commit** (with auto-publishing locked):
1. Push the commit; Netlify builds it.
2. Open **Deploys** and pick the `main@<commit>` deploy.
3. Click **Publish deploy**. The lock stays in place.
4. Check that `/researchtwin.html` loads and that its JS files match the commit.

## Database — Neon

**Connection rules**
- Use the **direct** endpoint (`ep-floral-thunder-bddca63h`, not `-pooler`) for the app, migrations and restores.
- Outbound TCP 5432 must be open. Some networks, for example with Cloudflare WARP active, block it.

**Before any migration, restore or seed**, confirm the target:
1. The connection string's SHA-256 prefix matches the approved fingerprint.
2. The server reports the expected `neon.endpoint_id`.
3. The Neon control plane lists that endpoint under branch `production`.

See the README section "Confirm the database target first".

**Migrations:** run from `backend/` in a fresh shell whose only database variable is the approved URL. Then check `alembic current` = `0012_search_history` and that `alembic check` is clean. Do not point `RESEARCHTWIN_ENV_FILE` at the workstation's `.env.local`.

## Demo data scripts (manual only)

| Script | Purpose | Safeguards |
|---|---|---|
| `backend/scripts/seed_demo_2_0.py` | Idempotent `[DEMO]` data for users 1–6 | Dry run unless `--commit`; refuses unless the target fingerprint, endpoint, schema and the six account roles match; users table fingerprinted before and after |
| `backend/scripts/repair_demo_seed.py` | Removed the 3 invalid demo groups and made the Westvale demo lab public (applied 2026-11-12) | Same target checks; refuses if memberships differ from what was seeded |

Neither script is referenced by `render.yaml`, `netlify.toml` or the application. They never run during a build or deploy.

## Rollback

See `BACKUP_AND_RECOVERY.md`. In short:
- **Code:** redeploy the previous commit on Render, or publish the previous deploy on Netlify.
- **Data:** restore a verified backup into a **new** Neon branch, then repoint `DATABASE_URL`.
