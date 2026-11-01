# ResearchTwin repository cleanup inventory

**Review date:** 2026-11-01
**Policy:** Inventory only. No file was deleted, moved, staged, or overwritten by cleanup. Pre-existing uncommitted work, local databases, backups, and model artifacts remain untouched.

## Retain

| Item | Reason |
|---|---|
| `backend/app/`, `backend/tests/`, and `frontend/` | Canonical backend, regression suite, and SPA. |
| Root `main.py`, `index.html`, and `researchtwin.html` | Compatibility launchers; root `main.py` routes to the canonical backend. |
| `backend/app/researcher_import.py` | Compatibility wrapper is imported by a security regression test. |
| `backend/app/services/researcher_similarity.py`, `backend/model_comparison.py`, and model-analysis scripts | Research/evaluation tooling still references these; retain while research workflows are in use. |
| `backend/models/researchtwin_logistic_v2_7features.joblib` | Active serving artifact referenced by `backend/app/services/recommendation.py`. It is currently untracked, so preserve and include through an approved release process. |
| `backend/researchtwin.db`, root `researchtwin.db`, and all `.bak` files | Existing data and recovery artifacts. Never remove as routine cleanup; verify and back up separately before any future data operation. |
| `PROJECT_COMPLETION_AUDIT.md`, `FINAL_ACCEPTANCE_REPORT.md`, `FINAL_E2E_TESTING_REPORT.md`, `DATABASE_VERIFICATION.md`, and older sections of `PRODUCTION_RELEASE_CHECKLIST.md` | Historical audit evidence. Findings and test counts are time-bound; consult current source/tests for present state. |

## Update

| Item | Finding | Suggested follow-up |
|---|---|---|
| `README.md` | Previously UTF-16LE without a BOM and contained obsolete setup functions, routes, settings, providers, and test totals. | Reconciled in this phase and normalized to UTF-8 so GitHub can render it as Markdown. |
| `PRODUCTION_RELEASE_CHECKLIST.md` | Contains historical Phase D/E/G claims, including old live probes and superseded route/security assertions. | Add a dated Phase 4 status banner and current local results; preserve historical evidence rather than silently rewriting it. |
| `backend/TESTING.md` | Contains older phase-specific test totals and production-like measurements. | Keep historical sections labeled by date/phase; add the latest canonical command and result after final regression. |
| `package.json` / `package-lock.json` | Both are untracked. `package.json` has a 99 KB description containing NUL-delimited README text, and `npm test` is a placeholder that exits 1. The lockfile is only 1.7 KB. | Review metadata, align scripts with explicit Node test commands, regenerate a coherent lockfile, then verify `npm ci`. Do not overwrite these files as cleanup. |
| `.gitignore` | Does not ignore root `node_modules/`; the repository also contains untracked `node_modules/`. | Add ignore coverage only after preserving package metadata and verifying a reproducible install. |
| `frontend-config.js` at repository root | Legacy duplicate points to localhost; canonical page references `frontend/frontend-config.js`. | Archive after confirming no external script or launch workflow depends on it. |
| Model artifact set | `researchtwin_logistic.joblib` and `researchtwin_logistic_render.joblib` are tracked older bundles; `researchtwin_logistic_compat_test.joblib` is untracked and byte-identical to the Render bundle; the active seven-feature artifact is separately untracked. | Keep the active seven-feature bundle. Record hashes/feature lists and compatibility checks; archive old/test bundles only after confirming release/provenance requirements. Do not delete or substitute artifacts in this phase. |

## Archive candidates (preserve until owner review)

- Legacy root scripts and data: `recommender.py`, `nlp_extractor.py`, `generate_dataset.py`, `ablation_study.py`, `students.csv`, `sys,py`, and `test-script.js`. These are not imported by the active application paths found in this review; some support old experiments or are malformed/obsolete. Preserve until an owner confirms they are not needed.
- `backend/generate_matching_dataset.py`: historical audit evidence records that its import of `model` from `semantic_matching` is broken after lazy loading. Repair and test it before future dataset generation, or archive it after research-owner review.
- `backend/app/services/matching.py`, `researcher_features.py`, and `recommendation_explanation.py`: no active application or test references were found by repository search; confirm external scripts before moving them. `researcher_similarity.py` is retained because model-comparison tooling uses it.
- `backend/save_model_compat_test.py` and the compatibility-test model artifact: test/migration experiment, not referenced by the serving path.
- Timestamped `.bak` files and older audit reports: keep as recovery/history; if a clean source tree is later wanted, archive outside the runtime package only after separate backup review.

## Safe-to-remove status

Nothing is marked safe to delete now. `node_modules/`, `.pytest_cache/`, and `__pycache__/` are reproducible in principle, but the package manifest/lockfile are inconsistent and this task forbids destructive cleanup. First repair and validate dependency installation; then remove generated directories only with explicit owner approval. No `git clean`, reset, delete, or model/database removal was performed.
