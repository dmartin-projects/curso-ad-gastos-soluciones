#!/usr/bin/env bash
# infra/backup.sh — cron diario en el servidor (módulo 67): copia de PostgreSQL a R2
set -euo pipefail
cd /opt/gastos
FECHA=$(date +%F-%H%M)
ARCHIVO="/tmp/gastos-${FECHA}.dump"
trap 'rm -f "$ARCHIVO"' EXIT

docker compose -f compose.prod.yaml exec -T db \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner > "$ARCHIVO"

rclone copy "$ARCHIVO" r2:gastos-backups/postgres/     # otro bucket que el de los archivos, con su propia clave
rclone delete --min-age 30d r2:gastos-backups/postgres/

if [ -n "${HEALTHCHECK_BACKUP_UUID:-}" ]; then           # "la copia se hizo" (healthchecks.io, módulo 68)
  curl -fsS -m 10 --retry 3 "https://hc-ping.com/${HEALTHCHECK_BACKUP_UUID}" >/dev/null
fi
