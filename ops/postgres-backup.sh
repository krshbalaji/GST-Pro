#!/usr/bin/env bash
set -euo pipefail

: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"

BACKUP_DIR="${BACKUP_DIR:-./ops/backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/${POSTGRES_DB}_${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"

echo "Creating PostgreSQL backup: ${BACKUP_FILE}"
docker compose exec -T db pg_dump \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  -Fc > "${BACKUP_FILE}"

test -s "${BACKUP_FILE}"
echo "Backup completed: ${BACKUP_FILE}"
