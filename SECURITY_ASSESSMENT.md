# ResearchTwin security assessment

**Review date:** 2026-11-01; remediation documentation updated 2026-11-03 (Phase 18)
**Scope:** Local source/configuration review of the current working tree. No production service, dashboard, database, or logs were accessed. Phase 18 changed the code described in this document (CSP image origin, authentication audit events, backup restore policy, frontend API configuration) and added regression tests; it did not deploy, migrate production, or verify live behavior.

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
| Rate limiting | `backend/app/services/rate_limit.py` hashes IP/account identities with HMAC and uses atomic database upserts. With shared mode enabled, it rejects non-PostgreSQL storage. `render.yaml` sets login to 10 attempts per 900 seconds and registration to 5 per 3600 seconds per IP plus normalized email. | Counters coordinate across workers only when all instances use the same PostgreSQL database. SQLite/local tests do not prove global production behavior. Rate-limited login attempts are rejected before credential checks and therefore create no audit rows. |
| Authentication audit trail | `backend/app/api/auth.py` records `auth.login_succeeded`, `auth.login_failed`, and `auth.logout`. Admin lifecycle paths already record `account.sessions_revoked`, `account.deactivate`, `account.role_change`, and `account.password_reset`. Events store user IDs, session IDs, action, and a reason code only. | No passwords, password hashes, bearer tokens, authorization headers, or raw request bodies are recorded. Failed logins are deduplicated per identity per login window; unknown emails are not stored. Success/logout write the session change and the audit row in one transaction. |
| Error logging | Reviewed API error paths log exception class names or route/method context, not exception messages, credentials, or request bodies. The provisioning CLI hides password input and does not print DB credentials. | Static source review only; no production log inspection was performed. Provisioning success prints the administrator email, so treat CLI output as account-identifying information. |

## Findings and residual risks

### High — model artifact is not part of the current tracked release source

The active recommendation service expects `backend/models/researchtwin_logistic_v2_7features.joblib`, but Git reports that file as untracked in the current working tree. A source checkout containing only tracked files will not have the active model, so readiness/recommendations will fail. The tracked `researchtwin_logistic_render.joblib` is an older, different feature bundle and is not a substitute for the active artifact. Package the validated active artifact in a future approved source/release change and verify it in a clean build. Do not retrain without a reproducible defect.

### High — bearer token is readable to same-origin JavaScript

`frontend/api-client.js` stores the session token in `sessionStorage`. This avoids persistence across browser restarts and does not store passwords, but an XSS flaw can read and exfiltrate the active token. The repository now configures browser security headers in `frontend/_headers` (a Netlify publish-directory file, separate from `netlify.toml`): a CSP that restricts scripts, frames, forms, objects, and connections; `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and HSTS. `tests/frontend/headers.test.cjs` parses that file and fails if any external asset referenced by `index.html` or `researchtwin.html` is not allowed by the matching CSP directive. This is repository configuration verified by static tests, **not** proof of what the deployed site returns. The live Netlify response headers, dashboard edge rules, and XSS behavior were not inspected. Any cookie migration must be coordinated with HttpOnly, Secure, SameSite, CSRF defenses, credentialed CORS, and frontend/backend tests. No auth migration was made.

### High — production trusted-client-IP behavior is unverified

**Status: BLOCKED BY EXTERNAL CONFIGURATION (H1-R).** Repository evidence: `render.yaml` sets `RATE_LIMIT_TRUST_CF_CONNECTING_IP=false` and leaves `RATE_LIMIT_TRUSTED_PROXY_CIDRS` dashboard-configured. `backend/app/services/rate_limit.py` honors `CF-Connecting-IP` only when the flag is exactly `true` *and* the direct peer address is inside an explicitly configured CIDR; otherwise it uses the peer address. The start command does not pass `--proxy-headers` or `--forwarded-allow-ips`, so uvicorn should report the TCP peer, not a client-supplied `X-Forwarded-For` value. Tests cover spoof rejection when trust is disabled or the CIDR list is empty.

This does **not** prove production attribution. The Render ingress peer address, whether it terminates the connection itself, and whether it overwrites or strips `CF-Connecting-IP` remain unverified. Resolving H1-R requires live evidence: the actual peer address observed by the service for a controlled request, and the provider's documented behavior for that header at that ingress. Do not enable trust, guess CIDRs, or trust arbitrary forwarded headers without that evidence. Rate limiting is not production-grade until this boundary and shared PostgreSQL are confirmed.

### Medium — production migration state and history

Alembic is configured in `backend/` with `0001_baseline` (the schema `create_all()` previously produced) and `0002_audit_events`. PostgreSQL readiness fails closed unless `alembic_version` equals the current head, and `create_all()` now runs for SQLite only. `tests/test_migrations.py` exercises the documented adoption path on disposable SQLite: build a representative legacy schema with data, `alembic stamp 0001_baseline`, `alembic upgrade head`, then compare the resulting schema with a fresh upgrade and confirm the legacy rows survive and the audit migration applies once. This is local evidence only. No production database was inspected or migrated; confirm its revision with `alembic current` during an approved change, after a backup and a restore rehearsal.

### Medium — dependency and model supply-chain reproducibility

Direct runtime requirements are mostly pinned, but the full transitive Torch/Transformers environment is not represented by a complete lockfile. The model bundle is a pickle-based joblib artifact, so only load files from a trusted, integrity-checked source. Verify dependency resolution, artifact provenance, and cold-start resource use in the target runtime before release.

### Medium — production behavior remains unverified

The Render Blueprint declares a shared-PostgreSQL requirement and readiness endpoint, but no PostgreSQL service is declared in the YAML and `DATABASE_URL`/secret values are dashboard-configured. Netlify and Render live settings and logs were not inspected. `frontend/frontend-config.js` now configures the API only for local hostnames and the exact production Netlify host, and leaves it unset for any other host; `api-client.js` validates the resolved base URL and fails closed with a configuration error. The overridden value can still be set deliberately through `window.RESEARCHTWIN_API_BASE`. Do not describe production as fixed or ready based on local tests.

### Low — CORS and browser headers

The backend always allows localhost origins in addition to `FRONTEND_ORIGINS`. The repository configures CSP and other browser security headers in `frontend/_headers`, not in `netlify.toml`; `tests/frontend/headers.test.cjs` statically verifies the directives and that every external asset on both entry pages is permitted. Live Netlify headers remain unverified. Remove unnecessary production origins or tighten headers only in separately tested changes if deployment policy requires it.

## Authentication audit operational notes (Phase 18)

`backend/app/api/auth.py` writes to the existing append-only `audit_events` table;
no new audit framework or table was added.

| Event | When | Target | Detail |
|---|---|---|---|
| `auth.login_succeeded` | Credentials verified and account active | `user` / user ID | none |
| `auth.login_failed` | Unknown email, wrong password, or inactive account | `user` / user ID, or `login_identity` / null | `{"reason": "unknown_account" \| "invalid_password" \| "inactive_account"}` |
| `auth.logout` | Authenticated logout | `auth_session` / session ID | none |

Administrator session revocation and lifecycle changes already write
`account.sessions_revoked`, `account.deactivate`, `account.role_change`, and
`account.password_reset`; those paths were not duplicated.

**Sensitive data.** Events never contain passwords, password hashes, bearer or
session tokens, authorization headers, or raw request bodies. Unknown login
emails are not stored at all: a plain hash of an email is dictionary-reversible,
and the rate limiter already keeps an HMAC'd per-email bucket for abuse control.
Known failures reference the stable internal user ID.

**Transactional behavior.** Successful login creates the session and the audit
row in the same commit; logout revokes the session and writes the audit row in
the same commit. If that commit fails, the API returns the existing database
`503` response, no session is persisted on login, and the session stays valid on
logout. A failed-login audit write is caught, the event is skipped, and the
login still returns the same `401`/`403` response. Audit failure
therefore never turns a rejected login into a success. Unknown-email and
known-email failures follow the same dummy-hash comparison and identical
response, so the audit change does not add account enumeration.

**Growth bounds.** At most one `auth.login_failed` row is written per known user
per login window (900 seconds by default), and at most one row for all unknown
identities per window. An attacker rotating source addresses cannot create
unbounded failure rows, but the deduplication also means the event count is not
a raw attempt count—use rate-limit counters for attempt volume.

**Rate-limit interaction.** Login is limited to 10 attempts per 900 seconds per
IP plus normalized email; registration is limited to 5 per 3600 seconds.
Rate-limited requests are rejected before credential verification, so they
produce no audit rows. The audit trail is not a substitute for rate-limit
monitoring, and cross-instance limits still require the shared PostgreSQL
configuration.

## Safe cookie migration prerequisites

Keep the current bearer-token flow until a complete change is tested. A cookie migration needs `HttpOnly`, `Secure`, and an appropriate `SameSite` value; anti-CSRF token/origin validation for state-changing requests; explicit credentialed CORS origins; browser `credentials` handling; logout/expiry parity; and end-to-end coverage. No frontend changes are required for this documentation-only phase.

## Production dependencies and checks

See [Production configuration checklist](PRODUCTION_CONFIGURATION_CHECKLIST.md) for Render, Netlify, PostgreSQL, rate-limit, model artifact, and release gates. No live service or data was modified.
