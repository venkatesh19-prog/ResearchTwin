# ResearchTwin 2.0 — Release Notes

**Release date:** 2026-11-12
**Production:** backend `9d3a5f5` (Render), frontend `b4891e5` (Netlify), database Neon at Alembic `0012_search_history`.
**Source:** GitHub `main` at `00ae755`.

## What's new in 2.0

Sixteen feature areas on top of 1.x recommendations, profiles, directory, roadmaps and collaboration requests:

1. Admin groups and role management
2. Researcher verification
3. Collaboration workspaces
4. Research teams and collaborator recommendations
5. Research opportunities and eligibility
6. Applications
7. Research intelligence
8. Analytics
9. Literature library
10. Research proposals
11. Thesis management
12. Publications
13. Research labs
14. Institutions
15. Inter-university collaborations
16. Search history

See `FEATURES.md` for details.

## Commits in this release

| Commit | Summary |
|---|---|
| `9d3a5f5` | ResearchTwin 2.0 platform integration: backend routes, migrations `0004`–`0012`, 2.0 frontend views |
| `b4891e5` | Sidebar navigation scrolls on its own, so Insights pages and Sign out are always reachable |
| `99f862c` | Idempotent `[DEMO]` data seed for the six demo accounts (manual script) |
| `9487f2d` | Clearer refusal message when adding an account to the wrong role group |
| `e29cd43` | Seed keeps demo data within app rules; one-off `repair_demo_seed.py` |
| `00ae755` | Seed records its cluster rebuild as a system action |

`9487f2d` is the only change to running code not yet deployed. It's an error-message wording fix and needs no urgent deploy.

## Infrastructure changes

- **Database moved to Neon:** production moved from the expiring Render PostgreSQL to Neon PostgreSQL 18 on 2026-11-11.
  - The Render data was frozen, backed up, restored into Neon `production`, and migrated `0002 → 0012`.
  - Row counts and the schema were verified after each step.
- **Neon credentials:** the owner password was rotated; Render uses the direct endpoint.
- **Deploy controls:** Render auto-deploy is Off and Netlify auto-publishing is Locked. Releases are published by hand.

## Demo data

**Seeded 2026-11-12.** Fictional content marked `[DEMO]`, attached only to demo users 1–6 (`*.researchtwin.example`). The real user (id 7) is untouched. Production now holds:

| Content | Count |
|---|---|
| Collaboration requests | 5 (2 accepted, 1 rejected, 2 pending) |
| Workspaces | 2, with 6 tasks, 4 milestones and 4 comments |
| Teams | 3, with 6 members and 3 invitations |
| Opportunities | 6 (4 research, 2 funding), with 4 applications |
| Literature entries | 13 |
| Proposals | 2, with 7 sections, 2 collaborators, 4 citations and 2 versions |
| Theses | 2, with 6 milestones and 13 events |
| Publications | 4, with 9 status events and 3 revisions |
| Institutions | 2 (5 memberships) |
| Labs | 3 (5 members) |
| Inter-university collaborations | 2 (1 active, 1 proposed) |
| Pending verification requests | 2 |
| Faculty-researcher links | 3 |
| Search-history entries | 11 |
| Roadmap milestones | 8 |
| Research-cluster run | 1 (30 assignments) |

Two student profile `publications` fields that were empty were filled.

**Corrections applied the same day** with `repair_demo_seed.py`:
- removed 3 non-role demo groups and their 7 memberships;
- made the Westvale demo lab public.

**Audit attribution exception:** one audit event and the cluster run are attributed to the admin account because of the first seed run. See `SECURITY.md`.

## Verification

- **Test suites:** backend 531 passed, frontend 132 passed, end-to-end PASS (13 journeys).
- **Release acceptance:** see `TESTING.md`. All 16 areas verified on production (read-only) and through write and browser journeys on a replica of production.

## Known limitations

These carry over and are documented with code references in the README's "Open defect register" and "Residual risks".
- **Recommendation quality:** training labels are heuristic (`STB-68`). NDCG@5 ≈ 0.973 measures agreement with those labels, not real-world acceptance.
- **Client IP:** attribution behind Render's proxy is unverified (`STB-39`), so rate-limit buckets may be shared.
- **Data export:** the DSAR export omits 2.0 tables (`STB-47`).
- **Session policy:** absolute 12-hour sessions with no self-service password reset (`STB-66`).
- **Free hosting:** the instance sleeps when idle, and builds take minutes.
- **Admin console:** a few low or medium edge cases (`STB-41`–`STB-52`).
- **Frontend tooling:** `package.json` and `package-lock.json` have uncommitted additions of `@neon/config` and `@neon/env`, which the project doesn't use. The project owner should decide whether to keep them.
