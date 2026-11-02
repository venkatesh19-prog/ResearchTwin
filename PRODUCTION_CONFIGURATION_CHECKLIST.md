# ResearchTwin production configuration checklist

**Source review date:** 2026-11-01; updated 2026-11-03 (Phase 18)
**Status:** Configuration files reviewed locally; live Render and Netlify settings, production database, and current deployment were not inspected or changed.

This checklist describes the repository's current source configuration. A value declared with `sync: false` in `render.yaml` still has to be configured in the Render dashboard. Never paste secret values into this file.

## Render API service

| Check | Source evidence | Required action before a future release | Status |
|---|---|---|---|
| Service root/build/start | `render.yaml`: `rootDir: backend`, `pip install -r requirements.txt`, `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | Confirm the live service uses these values and deploys the intended source revision. | File matches app layout; live setting unverified |
| Python runtime | `render.yaml` requests Python 3.11.11. | Confirm build logs report the configured runtime. Pin or record the complete resolved dependency set, including Torch/Transformers dependencies. | Declared; live runtime unverified |
| Readiness probe | `healthCheckPath: /ready`; app readiness checks database, active model path, and limiter configuration. | Require `/ready` to pass after the exact release artifact is built. `/health` alone is not sufficient. | Source configuration reviewed |
| Database | `DATABASE_URL` is `sync: false`; no PostgreSQL service is declared in this Blueprint. | Provision durable managed PostgreSQL, set `DATABASE_URL` in the dashboard, verify backups/restore and TLS, and ensure all app instances use the same database. | **BLOCKER: external DB and live URL not verified** |
| Shared rate limits | `RATE_LIMIT_REQUIRE_SHARED_DATABASE=true`; limits are 5 registrations/hour, 10 logins/15 minutes, and 8 recommendations/5 minutes. Counter state is stored in the database. | Keep the same PostgreSQL database across every worker/instance; exercise `429` and `Retry-After` through production ingress during a controlled release check. | File configured; cross-instance/live behavior unverified |
| Rate-limit HMAC secret | `RATE_LIMIT_HASH_SECRET` is `sync: false`; app requires at least 32 bytes. | Generate a high-entropy secret and store it only in the hosting secret manager. | **BLOCKER until configured and verified** |
| Client IP source | `RATE_LIMIT_TRUST_CF_CONNECTING_IP=false`. The limiter honors `CF-Connecting-IP` only if this is `true` **and** the peer is inside `RATE_LIMIT_TRUSTED_PROXY_CIDRS`; otherwise it uses the direct peer address. The start command does not pass uvicorn proxy-header options. | Keep trust disabled until the ingress behavior is proven. Resolving this requires live evidence: the peer address observed by the service for a controlled request and the provider's documented handling of `CF-Connecting-IP`. Do not guess CIDRs or trust arbitrary forwarded headers. | **BLOCKER: proxy behavior unverified** |
| Request size | `MAX_REQUEST_BODY_BYTES=65536`. | Retain an explicit body limit and verify the deployed service returns 413 over the configured cap. | Declared; live behavior unverified |
| CORS | `FRONTEND_ORIGINS` is `sync: false`; backend also always permits `http://localhost:5500` and `http://127.0.0.1:5500`. `allow_credentials` is false. | Set exact deployed frontend origin(s), remove obsolete origins if strict production policy requires it, and test preflight from the real Netlify origin. Do not use `*`. | Source reviewed; dashboard/live preflight unverified |
| Administrator provisioning | `backend/provision_admin.py` is an explicit CLI; web registration excludes admin. | Do not set `RESEARCHTWIN_ENABLE_ADMIN_PROVISIONING` on the web service. Use only the documented trusted-shell flow against a separately verified target with operator approval. | Source workflow reviewed; no real admin created |
| Model artifact | `backend/app/services/recommendation.py` loads `backend/models/researchtwin_logistic_v2_7features.joblib`; that artifact is untracked in the current Git worktree. | Ensure the exact validated seven-feature file is part of the immutable release artifact and passes `/ready` in a clean build. Review provenance/hash and never load untrusted joblib files. | **BLOCKER for source-only clean builds** |
| ML runtime/cold start | `sentence-transformers` is pinned directly but its Torch/Transformers dependency resolution is not locked as a complete set. Semantic matching may download a model at first use. | Verify build memory, runtime plan, cold start, model cache/network access, and inference response time against the intended hosting plan. | **UNVERIFIED** |
| Schema changes | Alembic is configured in `backend/` with `0001_baseline` and `0002_audit_events`; PostgreSQL readiness fails closed unless `alembic_version` is at the current head. `create_all()` runs for SQLite only. The documented stamp-then-upgrade path is covered by `backend/tests/test_migrations.py` on disposable SQLite. | Confirm the production database revision with `alembic current` during an approved change; back up, rehearse on a restored copy, apply reviewed revisions, and verify `/ready`. Production migration state is still unknown. | **BLOCKER: production revision unverified** |
| Service size/storage | `render.yaml` declares no plan, disk, database, or migration command. | Select a plan that meets measured memory/CPU needs. SQLite on ephemeral storage is not a production persistence strategy. | **UNVERIFIED** |
| Logs/secrets | Reviewed code logs exception types and route/method context; provisioning prompts hide passwords. | Use hosting secret settings and ensure passwords, bearer tokens, database URLs, and HMAC secrets never appear in logs. | Static source review only; live logs uninspected |

## Netlify frontend

| Check | Source evidence | Required action before a future release | Status |
|---|---|---|---|
| Publish directory | `netlify.toml` publishes `frontend`; no build command is required. | Confirm the live site publishes the same directory and intended revision. | File reviewed; live settings unverified |
| API base URL | `frontend/frontend-config.js` uses localhost locally and `https://researchtwin-api.onrender.com` only on the documented production Netlify host (`starlit-empanada-a323e3.netlify.app`). Other hosts leave the API unset and `api-client.js` fails closed with a configuration error. `window.RESEARCHTWIN_API_BASE` remains an explicit override. | Confirm the live hostname matches the allowlist. A Netlify environment variable does not rewrite this JavaScript automatically; change the source deliberately or set the global before the config script loads, and add any new API origin to the CSP `connect-src`. | Source reviewed; live served bundle unverified |
| Browser security headers | `frontend/_headers` configures CSP, HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy`. Netlify reads `_headers` from the publish directory; `netlify.toml` only declares the publish directory. `tests/frontend/headers.test.cjs` statically verifies the directives and that every external asset on both entry pages is permitted. | Confirm the deployed site actually returns those headers and that no dashboard edge rule replaces them. Re-run the header tests after any asset or origin change. | Configured in repository and statically tested; live response unverified |
| API origin alignment | API CORS reads `FRONTEND_ORIGINS`; credentials are disabled. | Set the exact Netlify origin on Render and verify login, authenticated calls, and preflight from the deployed browser origin. | **Live verification required** |
| Token storage | API client stores the bearer token in `sessionStorage`. | Retain awareness of XSS token exposure; plan a separately tested cookie/CSRF migration if production policy requires it. | Known residual risk |

## Pre-release sequence

1. Resolve active model artifact packaging and verify the exact artifact in a clean checkout/build.
2. Provision and validate shared PostgreSQL, backups, and restore procedures.
3. Configure `DATABASE_URL`, `RATE_LIMIT_HASH_SECRET`, `FRONTEND_ORIGINS`, and limiter settings in the hosting configuration; verify the trusted client-IP header boundary.
4. Confirm the production database revision with `alembic current`; do not rely on `create_all()`. Apply only reviewed Alembic revisions after a backup and restore rehearsal.
5. Confirm runtime resource sizing, dependency resolution, sentence-transformer download/cache behavior, and cold-start/inference time.
6. Confirm the live Netlify response headers and exact API URL/CORS alignment, including the production hostname in the frontend allowlist.
7. Run backend/frontend/browser regressions against isolated local resources, then do read-only deployment smoke checks and authorized test-account journeys after an independently approved deployment.
8. Record the deployed source revision and test evidence. No live verification is claimed by this checklist.

## Platform references

- [Render Blueprint YAML reference](https://render.com/docs/blueprint-spec)
- [Render health checks](https://render.com/docs/health-checks)
- [Netlify build configuration](https://docs.netlify.com/build/configure-builds/overview/)
