# ResearchTwin Security

This summarises the implemented controls. The README sections "Security", "Residual risks" and "Open defect register" have the full, code-referenced detail.

## Authentication and sessions
- **Passwords:** PBKDF2-HMAC-SHA256 with 600,000 iterations and a per-user random salt. No plaintext is stored or logged.
- **Session tokens:** sign-in issues a random bearer token. The server stores only its SHA-256 digest; every request checks expiry, and logout writes `revoked_at`.
  - Verified: a token is rejected after logout (`/auth/me` returns 401).
- **Session lifetime:** an absolute 12 hours (`AUTH_SESSION_TTL_SECONDS`). There is no idle timeout and no self-service password reset; administrators reset passwords.
- **Registration:** creates only `student` or `faculty` accounts. Administrators are created with `backend/provision_admin.py`, which requires typed confirmation.

## Authorization
- **Server-side checks:** every role and ownership rule is enforced on the server. The frontend never authorizes anything.
- **Role dependencies:** `require_role(...)` guards each route; the required role per route is listed in `API_DOCUMENTATION.md`.
- **`/me` routes:** the owner always comes from the token, never from a client-supplied ID.
- **Ownership:** workspaces, teams, proposals, theses, publications, literature, applications and labs enforce membership or ownership, returning `403` or `404` otherwise. Release testing confirmed cross-account isolation for all 16 feature areas.

## Input and data handling
- **Validation:** Pydantic schemas, with `extra="forbid"` on most request models, plus enum and transition validation. Oversized bodies return `413`.
- **SQL:** queries go through the SQLAlchemy ORM with bound parameters; application code builds no SQL from strings.
- **Duplicates:** unique indexes and conflict checks prevent duplicate pending requests, applications, open collaborations and citation keys.

## Transport and browser
- **CORS:** an exact allowlist (`FRONTEND_ORIGINS` plus two localhost origins), credentials off. Verified: a foreign origin is refused.
- **Frontend headers** (`frontend/_headers`):
  - a CSP with `default-src 'self'`, `frame-ancestors 'none'`, and `connect-src` limited to the API;
  - HSTS, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.

## Rate limiting
- **Scope:** login, registration, recommendations, network-heavy research-intelligence calls and opportunity applications are rate-limited.
- **Storage:** counters live in PostgreSQL, keyed by an HMAC under `RATE_LIMIT_HASH_SECRET`. `/ready` fails if the secret is missing or shorter than 32 bytes.

## Secrets
- **Not in the repository:** credentials, `.env` files and database URLs are never committed, and `.gitignore` excludes `.env*`, `*.db` and local backup copies.
- **Verified 2026-11-12:**
  - No real secrets in tracked files. The only connection-string-shaped values are `example.com` test fixtures.
  - No `.env`, database or dump file is tracked.
- **Production secrets** live in the Render dashboard (`DATABASE_URL`, `RATE_LIMIT_HASH_SECRET`). The Neon owner password was rotated on 2026-11-11.

## Audit trail
- **What's logged:** `audit_events` records authentication and administrative actions in the same transaction as the change.
- **What's never logged:** passwords, hashes or tokens.

### Documented exception: demo-seeding attribution
On 2026-11-12 the first run of `backend/scripts/seed_demo_2_0.py` called the application's cluster-rebuild service with the admin account (user 6) as its actor. As a result:
- `audit_events` has one `research_intelligence.clusters_rebuilt` event at 09:46 UTC attributed to user 6;
- the `research_cluster_runs` row has `created_by_user_id = 6`.

No person performed that rebuild through the admin account; the seeding script did. At the project owner's direction both records stay unchanged (audit history is not rewritten). This section is their documented explanation. The seed was corrected in `00ae755`: later runs record the rebuild as a system action.

## Known risks (summary)
- **Token storage:** the bearer token lives in `sessionStorage`, and the CSP allows inline scripts, so an XSS flaw could steal an active session.
- **Client IP:** behind Render's proxy, attribution is unverified (`STB-39`). Rate-limit buckets may be shared across clients until the proxy path is confirmed and `RATE_LIMIT_TRUSTED_PROXY_CIDRS` is configured.
- **Public schema:** `/openapi.json` and `/docs` are public.
- **Data export:** the DSAR export (`/admin/users/{id}/data-export`) omits 2.0 tables (`STB-47`).
- **Faculty self-registration:** anyone can self-register as faculty; this is an open policy decision (`STB-67`).
