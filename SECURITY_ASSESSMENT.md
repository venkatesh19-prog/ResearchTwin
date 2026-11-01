# ResearchTwin security assessment

**Review date:** 2026-11-01
**Scope:** Local source/configuration review of the current working tree. No production service, dashboard, database, or logs were accessed. No code or authentication behavior was changed in this assessment.

## Verified controls

| Area | Source evidence | Assessment |
|---|---|---|
| Password storage | `backend/app/services/auth.py` uses PBKDF2-HMAC-SHA256, 600,000 iterations, and a per-user random salt. | No plaintext password storage found in the authentication path reviewed. Password input is not logged by the API code reviewed. |
| Bearer sessions | Tokens are 32 random bytes encoded for transport; only SHA-256 token hashes are stored. Expiry is checked on each authenticated request; logout writes `revoked_at`. Default TTL is 12 hours; positive `AUTH_SESSION_TTL_SECONDS` can override it. | Expiry and revocation are enforced by source. Choose an explicit bounded production TTL policy; invalid values fall back to 12 hours. |
| Ownership and roles | Profile endpoints use `/me` routes and authenticated user identity; role dependencies guard student/faculty/admin operations. Researcher writes/import and faculty-link assignment require admin. | The code does not rely on a client-supplied student ID for profile ownership. Keep backend authorization as the authority. |
| Administrator creation | `backend/provision_admin.py` requires explicit environment opt-in, an explicit target database URL, typed confirmation, and a hidden password prompt; it refuses to change an existing account's role. Public registration is student/faculty only. | No public admin-registration route or default password was found. No administrator was created as part of this review. |
| SQL/data access | Directory and profile logic uses SQLAlchemy ORM/query parameters. Researcher import reads a fixed bundled CSV path and is admin-only. | No raw SQL injection issue was identified in reviewed paths. Keep future input-bound SQL parameterized. |
| Request validation | Pydantic request schemas and configurable request-body middleware cap (65,536 bytes by default) are present. | Keep the body cap and schema validation enabled in production. |
| CORS | `backend/app/main.py` uses an origin allowlist from `FRONTEND_ORIGINS` plus two fixed localhost origins, with `allow_credentials=False`. | Exact production origins still need live verification; localhost origins are always present in the source allowlist. |
| Rate limiting | `backend/app/services/rate_limit.py` hashes IP/account identities with HMAC and uses atomic database upserts. With shared mode enabled, it rejects non-PostgreSQL storage. | Counters coordinate across workers only when all instances use the same PostgreSQL database. SQLite/local tests do not prove global production behavior. |
| Error logging | Reviewed API error paths log exception class names or route/method context, not exception messages, credentials, or request bodies. The provisioning CLI hides password input and does not print DB credentials. | Static source review only; no production log inspection was performed. Provisioning success prints the administrator email, so treat CLI output as account-identifying information. |

## Findings and residual risks

### High — model artifact is not part of the current tracked release source

The active recommendation service expects `backend/models/researchtwin_logistic_v2_7features.joblib`, but Git reports that file as untracked in the current working tree. A source checkout containing only tracked files will not have the active model, so readiness/recommendations will fail. The tracked `researchtwin_logistic_render.joblib` is an older, different feature bundle and is not a substitute for the active artifact. Package the validated active artifact in a future approved source/release change and verify it in a clean build. Do not retrain without a reproducible defect.

### High — bearer token is readable to same-origin JavaScript

`frontend/api-client.js` stores the session token in `sessionStorage`. This avoids persistence across browser restarts and does not store passwords, but an XSS flaw can read and exfiltrate the active token. `netlify.toml` currently has no response headers/CSP. Review a compatible CSP and output escaping; any cookie migration must be coordinated with HttpOnly, Secure, SameSite, CSRF defenses, credentialed CORS, and frontend/backend tests. No auth migration was made.

### High — production trusted-client-IP behavior is unverified

`render.yaml` sets `RATE_LIMIT_TRUST_CF_CONNECTING_IP=true`. The limiter validates that the header contains an IP address, but syntactic validation does not prove the ingress supplied it. Verify that the actual proxy overwrites or protects `CF-Connecting-IP`; otherwise disable trust and use the verified peer address. Rate limiting is not production-grade until this trust boundary and shared PostgreSQL are confirmed.

### High — database schema has no migration history

The app invokes `Base.metadata.create_all()` during application import/start. The repository has no Alembic dependency, configuration, or revisions. This creates missing tables but does not safely alter existing tables. Before the next schema change on persistent data, add a reviewed Alembic baseline and revision process, test against a copy, back up, apply as a controlled one-off step, and rehearse restore. No migration was run.

### Medium — dependency and model supply-chain reproducibility

Direct runtime requirements are mostly pinned, but the full transitive Torch/Transformers environment is not represented by a complete lockfile. The model bundle is a pickle-based joblib artifact, so only load files from a trusted, integrity-checked source. Verify dependency resolution, artifact provenance, and cold-start resource use in the target runtime before release.

### Medium — production behavior remains unverified

The Render Blueprint declares a shared-PostgreSQL requirement and readiness endpoint, but no PostgreSQL service is declared in the YAML and `DATABASE_URL`/secret values are dashboard-configured. Netlify and Render live settings and logs were not inspected. The frontend defaults to the Render API URL. Do not describe production as fixed or ready based on local tests.

### Low — CORS and browser headers

The backend always allows localhost origins in addition to `FRONTEND_ORIGINS`; the Netlify config only declares a publish directory and no CSP/security headers. Remove unnecessary production origins or add vetted response headers in a separately tested change if required by deployment policy.

## Safe cookie migration prerequisites

Keep the current bearer-token flow until a complete change is tested. A cookie migration needs `HttpOnly`, `Secure`, and an appropriate `SameSite` value; anti-CSRF token/origin validation for state-changing requests; explicit credentialed CORS origins; browser `credentials` handling; logout/expiry parity; and end-to-end coverage. No frontend changes are required for this documentation-only phase.

## Production dependencies and checks

See [Production configuration checklist](PRODUCTION_CONFIGURATION_CHECKLIST.md) for Render, Netlify, PostgreSQL, rate-limit, model artifact, and release gates. No live service or data was modified.
