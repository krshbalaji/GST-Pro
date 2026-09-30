# PostgreSQL Backup & Restore Runbook

This runbook provides the first operational backup/restore checkpoint for GST Pro.

## Scope

- PostgreSQL is the system-of-record database.
- Backups use PostgreSQL custom (`-Fc`) format.
- Restore is an explicit, destructive operation against the selected target database.
- The scripts do not change GST/business logic or application data models.

## Backup

Set the same database variables used by docker compose:

~~~bash
export POSTGRES_USER=gstpro
export POSTGRES_DB=gstpro
export POSTGRES_PASSWORD='...'
bash ops/postgres-backup.sh
~~~

The resulting dump is written under `ops/backups/` unless `BACKUP_DIR` is overridden.

For production, store completed dumps outside the application host/container and protect them with appropriate access controls and encryption. Do not commit backup files to Git.

## Restore

Use a disposable/recovery PostgreSQL target first.

~~~bash
export POSTGRES_USER=gstpro
export POSTGRES_DB=gstpro
export CONFIRM_RESTORE=YES
bash ops/postgres-restore.sh ./ops/backups/gstpro_YYYYMMDDTHHMMSSZ.dump
~~~

The restore script uses `pg_restore --clean --if-exists --no-owner`. This is intentionally destructive to objects represented by the dump, so the explicit `CONFIRM_RESTORE=YES` guard is required.

After restore:

1. Confirm PostgreSQL is healthy.
2. Run the GST Pro readiness endpoint.
3. Run the focused production regression suite.
4. Verify tenant, GSTIN, invoice, audit, and refresh-token records expected for the recovery point.
5. Record the restore result and elapsed time as part of the DR test evidence.

## Important production limitation

Adding scripts does **not** prove disaster recovery. A production release still needs an actual backup/restore exercise, an off-host backup destination, retention policy, encryption/key management, RPO/RTO targets, and periodic restore testing.

The next validation checkpoint should execute a real dump and restore against a disposable PostgreSQL instance and capture the evidence.

## CI

Do not put real backup data or production credentials into GitHub Actions. CI should validate the scripts without exposing production data.
