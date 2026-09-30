#!/usr/bin/env bash
set -euo pipefail

: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"

BACKUP_FILE="${1:?Usage: ./ops/postgres-restore.sh <backup-file>}"
if [[ ! -s "${BACKUP_FILE}" ]]; then
  echo "Backup file not found or empty: ${BACKUP_FILE}" >&2
  exit 1
fi

if [[ "${CONFIRM_RESTORE:-}" != "YES" ]]; then
  echo "Restore is destructive for the target database."
  echo "Set CONFIRM_RESTORE=YES only after confirming the target database is disposable/recoverable."
  exit 2
fi

echo "Restoring ${BACKUP_FILE} into PostgreSQL database ${POSTGRES_DB}..."
docker compose exec -T db pg_restore \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  --clean --if-exists --no-owner \
  < "${BACKUP_FILE}"

echo "Restore completed. Run the application regression/health checks before treating the restored database as serviceable."
