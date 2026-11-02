# Disaster recovery and data protection

ResearchTwin stores accounts, profiles, collaboration history, roadmap progress,
sessions, and the audit trail. This document defines how that data is backed up,
verified, restored, retained, and exported. It assumes **no managed backup is
provided by the free hosting tier** until the account dashboard proves
otherwise, and it uses no paid infrastructure.

## Scope and targets

| Item | Value |
| --- | --- |
| Backup tool | `backend/scripts/database_backup.py` |
| Covered data | SQLite file or PostgreSQL database configured by `DATABASE_URL` |
| Not covered | Application secrets (`DATABASE_URL`, `RATE_LIMIT_HASH_SECRET`), model artifacts, uploaded files (none exist) |
| Recovery point objective (free tier) | 24 hours |
| Recovery time objective | 4 hours for a tested restore path |
| Restore drills | Quarterly, on an isolated database |

Secrets are configured separately and must never be stored inside a backup
archive or committed to Git.

## Backup schedule

| Cadence | Retention | Location |
| --- | --- | --- |
| Daily (operator-run or scheduled task) | 14 days | Host outside the web service, access-controlled |
| Weekly | 8 weeks | Off-host, encrypted archive |
| Before any migration or schema change | Until the change is verified, then 30 days | Off-host |
| Quarterly restore drill output | Delete after verification | Disposable local path |

Render Free does not guarantee durable database backups. Verify the database
provider's backup and expiry status in its dashboard every month. PostgreSQL
Free instances on Render expire; the currently tracked expiry is **2026-11-21**
and must be re-confirmed before relying on it.

### Encrypting an archive

Use an OS-provided tool with a passphrase held outside the repository, for
example `7z a -p -mhe=on backup.7z backup.db*` on Windows or
`age -p -o backup.age backup.db*` where available. Never place the passphrase in
a script, shell history, or this document.

## Backups

Run from `backend/` with the project virtual environment.

SQLite (consistent while the application is running):

```bash
python scripts/database_backup.py backup \
  --source researchtwin-demo.db \
  --destination ../backups/researchtwin-2026-11-03.db
```

PostgreSQL (requires `pg_dump`; the URL is taken from the argument, never printed):

```bash
DATABASE_URL='postgresql://...' python scripts/database_backup.py backup \
  --database-url "$DATABASE_URL" \
  --destination ../backups/researchtwin-2026-11-03.dump
```

Each backup writes a `<backup>.manifest.json` sidecar containing the SHA-256
checksum and file size. SQLite manifests also record table row counts, the
Alembic revision when present, and active/expired session counts. PostgreSQL
manifests contain only the checksum, size, database name, and whether
`pg_restore --list` validated the archive; they do not contain row counts or a
schema revision. The tool refuses to overwrite an existing file.

A backup without a manifest can still be checked read-only with `verify`, but
`restore` rejects it by default because there is no recorded checksum, row
count, or revision to compare against. This is a deliberate compatibility
boundary: older SQLite backups that predate manifests remain recoverable, but
only through an explicit, reviewed opt-in after the verification output is
inspected (see [SQLite restore](#sqlite-restore-tool-supported)).

## Verification

Verification is read-only and never needs the source database:

```bash
python scripts/database_backup.py verify --backup ../backups/researchtwin-2026-11-03.db
```

The command fails when the checksum does not match the manifest, when SQLite
`integrity_check` is not `ok`, or when row counts drift from the manifest.
`pg_restore --list` validates PostgreSQL archives when the client tools are
installed.

## Restore procedure

1. Stop application writes or put the service in maintenance mode.
2. Take a fresh backup of the current database before touching it.
3. Select the newest backup whose `verify` step succeeds.
4. Restore to a **new** database, never over the live one.
5. Compare the restored snapshot with the backup manifest.
6. If the backup predates the current schema, run `alembic upgrade head`
   against the restored copy and re-verify.
7. Repoint `DATABASE_URL` only after the restored copy passes verification, or
   follow the provider's console restore flow.
8. Record the incident, backup used, timestamps, and verification output.

### SQLite restore (tool-supported)

```bash
python scripts/database_backup.py restore \
  --backup ../backups/researchtwin-2026-11-03.db \
  --target ../restore-drill-2026-11-03.db
```

The command accepts SQLite backups only. It rejects PostgreSQL archives and
non-SQLite files before creating the target, refuses an existing target, and
removes its own partial target if the copy or verification fails. Restore
requires the manifest by default.

**Legacy manifest-less backups.** A SQLite backup created by an earlier tool
version without a manifest follows the same compatibility path:

```bash
# 1. Read-only check; reports "manifest": null and still runs integrity_check.
python scripts/database_backup.py verify --backup ../backups/legacy.db

# 2. Deliberate opt-in only after reviewing that output and confirming the file
#    came from a trusted location.
python scripts/database_backup.py restore \
  --backup ../backups/legacy.db \
  --target ../restore-drill-legacy.db \
  --allow-manifestless
```

Manifest-less restore still refuses an existing target, still validates the
SQLite file signature before creating the target, and still removes a partial
target on failure. It simply cannot compare checksums or row counts against a
manifest, so record the verification output in the restore log and compare row
counts manually. No migration converts old backups; the opt-in is the
compatibility path.

### PostgreSQL restore (manual-only, unverified)

The backup tool does not implement PostgreSQL restore and its `restore`
subcommand rejects PostgreSQL archives. PostgreSQL recovery is a reviewed
manual operation:

```bash
pg_restore --no-owner --no-privileges --dbname=<new target> <file>
```

This path has **not** been drilled against a disposable PostgreSQL database in
this repository. Treat it as unverified until an approved restore drill is
completed. Never run it against production without explicit approval, a fresh
backup, and a tested rollback path.

### PostgreSQL capacity queries (read-only)

```sql
SELECT pg_size_pretty(pg_database_size(current_database()));
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;
SELECT count(*) FROM pg_stat_activity;
```

For SQLite, capacity and retention indicators come from:

```bash
python scripts/database_backup.py status --source researchtwin-demo.db
```

The output includes file size, freelist pages, per-table row counts, active and
expired sessions, and the audit-event date range. Review it monthly. Treat 80%
of available storage, a rising freelist, or more than 30 days of expired
sessions as a cleanup signal.

## Retention rules

These are proposed defaults and need institutional approval before enforcement.

| Data | Default retention |
| --- | --- |
| Audit events | 3 years |
| Collaboration requests and responses | 3 years after last update |
| Roadmap progress | Life of the account |
| Expired or revoked sessions | Purge candidates after 30 days |
| Rate-limit counters | Purge candidates after 7 days |
| Deactivated accounts | Review after 2 years; delete only with approval |
| Backups | Per the schedule above, then securely delete |

Deletion is manual and reviewed; there is no destructive retention job in the
application. Purge only from a verified backup, and never purge audit events
covered by a legal hold or open investigation.

## Account deletion policy

1. An administrator deactivates the account through
   `PUT /admin/users/{id}/active`. This revokes every session immediately and
   writes an `account.deactivate` audit event.
2. The account remains visible to administrators for audit and support.
3. A verified erasure request is handled as a reviewed offline operation: take a
   backup, export the account first, delete or anonymize the account rows, keep
   audit events with the actor reference nulled, and record the decision.
4. Do not hard-delete an account that owns collaboration history needed for
   accountability. Prefer deactivation plus anonymization.
5. Legal holds and institutional retention requirements override deletion
   requests until released.

## Personal-data export

Administrators can export one account with:

```http
GET /admin/users/{user_id}/data-export
Authorization: Bearer <admin token>
```

The response includes account metadata, the student or faculty profile, the
faculty-researcher link, the account's collaboration requests, requests in the
faculty inbox, roadmap progress, session counts, and the account's audit events.
Password hashes and session token hashes are never included. Each export writes
an `account.data_export` audit event.

## Incident checklist

1. Stop writes and preserve logs.
2. Confirm scope: data loss, corruption, credential compromise, or provider
   failure.
3. If credentials may be exposed, rotate `DATABASE_URL`,
   `RATE_LIMIT_HASH_SECRET`, and affected passwords after restoring service.
4. Restore the newest verified backup to a new database and verify row counts.
5. Run migrations only when the restored schema is older than the code.
6. Repoint the service, verify `/ready` and a read-only API call, then reopen
   writes.
7. Document the timeline, evidence, and follow-up actions.
