# ResearchTwin Backup and Recovery

## Backups on record

Backups are kept outside the repository in `C:\Users\Venkatesh\ResearchTwinBackups\` on the operator workstation. They hold personal data and must never be committed. Each one has a `.manifest.json` sidecar recording its SHA-256 and size.

| File | Source | Taken | SHA-256 (prefix) | Notes |
|---|---|---|---|---|
| `researchtwin-neon-prod-preseed-20261112T093358Z.dump` | Neon `production` | 2026-11-12 09:33 UTC | `66eedb4a84bf1c7d` | **Neon production before demo seeding.** Migrated to 0012, real data only |
| `researchtwin-prod-20261111T190259Z.dump` | Old Render PostgreSQL | 2026-11-11 19:02 UTC | `c37f979b2d67c79c` | **Final cutover backup**, taken with writes frozen; this was restored into Neon |
| `researchtwin-prod-20261111T183151Z.dump` | Old Render PostgreSQL | 2026-11-11 18:31 UTC | `457a0833060c2c8e` | Before the freeze |
| `researchtwin-prod-20261110T183936Z.dump` and two 2026-11-03 dumps | Old Render PostgreSQL | earlier | see manifests | Historical |

The **old Render database** (`researchtwin-db`) is still available for rollback, but its free plan **expires on 2026-11-21**. Keep the cutover dump after that date.

## Taking a backup

```powershell
cd backend
python scripts/database_backup.py backup --database-url "<approved URL>" --destination ..\..\ResearchTwinBackups\researchtwin-neon-prod-<UTC timestamp>.dump
python scripts/database_backup.py verify --backup ..\..\ResearchTwinBackups\researchtwin-neon-prod-<UTC timestamp>.dump
```

- **What the utility does:** runs `pg_dump --format=custom --no-owner --no-privileges` and refuses to overwrite an existing file.
- **Afterwards:** confirm `pg_restore --list` and a full `pg_restore --file=-` decompression succeed. Compare row counts with the source before relying on the file.
- **Never print the URL.** Pass it from a protected file or a variable.

## Restoring PostgreSQL (never over the live database)

1. Create a **new** Neon branch, or an empty database.
2. Confirm its endpoint through the Neon control plane, and fingerprint the connection string.
3. Restore:

   ```powershell
   pg_restore --no-owner --no-privileges --single-transaction --exit-on-error --dbname "<new target URL>" <file.dump>
   ```

4. **Check the result:**
   - compare row counts with the dump;
   - check that sequences are at or above the maximum IDs;
   - confirm `alembic_version` holds the expected revision.
5. **If the dump predates the code's head,** run `alembic upgrade head` in a fresh shell whose only database variable is the new target.
6. **Repoint the backend:** set Render's `DATABASE_URL` to the new target (direct endpoint), redeploy, and confirm `/ready` returns 200.

This exact path was executed during the 2026-11-11 cutover: Render dump, then restore into Neon `production`, then migrate `0002 → 0012`.

## Rolling back code

- **Backend:**
  1. In Render, open **Manual Deploy → Deploy a specific commit**, select the previous good commit and deploy.
  2. If a migration has run since, redeploy the code first. Downgrades drop data and are not a recovery plan.
- **Frontend:** in Netlify, open **Deploys**, choose the previous deploy and click **Publish deploy**. Auto-publishing stays locked.
- **Compatibility:**
  - the 2.0 frontend needs the 2.0 backend;
  - the 1.x backend at commit `a4a1c7b` expects schema `0002` and fails `/ready` against Neon at `0012`.

## Demo data

- **Removing it:** demo records are identifiable by their `[DEMO]` titles and by belonging to users 1–6. No removal script is provided; ask for one if you need it.
- **Restoring a clean state:** restore the `preseed` dump into a new branch.
- **Recreating the data:** rerun `backend/scripts/seed_demo_2_0.py --commit`. It is idempotent and creates nothing that already exists.

## Incident checklist

1. Freeze writes. On the free plan, suspend the Render service; Render maintenance mode is paid-only.
2. Take a fresh backup of the current database.
3. Restore into a new target, verify, migrate if needed.
4. Repoint `DATABASE_URL`, deploy, check `/ready`, `/health` and the smoke routes.
5. **Resuming a suspended service** first restarts the previous build with its earlier settings, which may point at the old database.
   - Deploy the intended commit immediately.
   - Confirm the running build by its route count (110 for 2.0), not only by `/ready`.
6. If credentials might be exposed, rotate the Neon password and `RATE_LIMIT_HASH_SECRET`.
