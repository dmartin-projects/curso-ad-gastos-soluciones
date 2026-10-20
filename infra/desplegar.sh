#!/usr/bin/env bash
# infra/desplegar.sh — se ejecuta EN el servidor: VERSION=v1.4.0 ./infra/desplegar.sh (módulos 66 y 83)
set -euo pipefail
cd /opt/gastos
NUEVA="${VERSION:?Indica la versión: VERSION=v1.4.0 $0}"   # antes de leer .env, que también define VERSION
set -a                                         # exporta lo que se lea de .env: DOMINIO, GHCR_OWNER…
# shellcheck source=/dev/null
. ./.env
set +a
export VERSION="${NUEVA#v}"                    # v1.4.0 → 1.4.0 (la etiqueta de la imagen)
COMPOSE="docker compose -f compose.prod.yaml"
SERVICIOS="web worker worker-ocr beat tasks-worker proxy"

echo "▶ Desplegando $VERSION"
ANTERIOR=$(cat .version-actual 2>/dev/null || echo latest)

$COMPOSE pull --quiet
$COMPOSE up -d db redis rabbitmq
$COMPOSE run --rm migrate                      # con el código NUEVO, mientras sirve el viejo
# Si la web nueva no llega a "healthy", up falla (el proxy espera a web: service_healthy) y, con
# set -e, el script terminaría AQUÍ, sin volver atrás. Por eso || : decide la comprobación de abajo.
# shellcheck disable=SC2086
$COMPOSE up -d --remove-orphans $SERVICIOS || echo "⚠️  docker compose up terminó con error"

echo "▶ Comprobando salud…"
for _ in $(seq 1 30); do
  if curl -fsS "https://${DOMINIO}/health/ready/" >/dev/null; then
    echo "$VERSION" > .version-actual
    docker image prune -f >/dev/null
    echo "✅ $VERSION desplegada"
    exit 0
  fi
  sleep 2
done

echo "❌ La versión $VERSION no responde: volviendo a $ANTERIOR"
# shellcheck disable=SC2086
VERSION=$ANTERIOR $COMPOSE up -d $SERVICIOS
exit 1
