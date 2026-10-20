#!/usr/bin/env bash
# infra/desplegar.sh — se ejecuta EN el servidor: VERSION=v1.4.0 ./infra/desplegar.sh (módulos 66 y 83)
set -euo pipefail
cd "$(dirname "$0")/.."                         # /opt/gastos
NUEVA="${VERSION:?Indica la versión: VERSION=v1.4.0 $0}"   # antes de leer .env, que también define VERSION
set -a                                         # exporta lo que se lea de .env: DOMINIO, GHCR_OWNER…
# shellcheck source=/dev/null
. ./.env
set +a
export VERSION="${NUEVA#v}"                    # v1.4.0 → 1.4.0 (la etiqueta de la imagen)
COMPOSE="docker compose -f compose.prod.yaml ${COMPOSE_EXTRA:-}"
SERVICIOS="worker worker-ocr beat tasks-worker" # web y proxy van aparte (ejercicio 3)
export COMPOSE_EXTRA

echo "▶ Desplegando $VERSION"
ANTERIOR=$(cat .version-actual 2>/dev/null || echo latest)

$COMPOSE pull --quiet
$COMPOSE up -d db redis rabbitmq
$COMPOSE run --rm migrate                      # con el código NUEVO, mientras sirve el viejo
# Si la web nueva no llega a "healthy", up falla (el proxy espera a web: service_healthy) y, con
# set -e, el script terminaría AQUÍ, sin volver atrás. Por eso || : decide la comprobación de abajo.
# La web, réplica a réplica: las nuevas entran antes de que salgan las viejas (sin peticiones cortadas)
./infra/rotar-web.sh || echo "⚠️  la web nueva no llegó a healthy"
# --no-deps: sin él, compose vuelve a ejecutar migrate (su imagen cambió) con el proxy YA parado: ~12 s sin servicio
# shellcheck disable=SC2086
$COMPOSE up -d --no-deps --remove-orphans $SERVICIOS || echo "⚠️  docker compose up terminó con error"
# El proxy, solo y al final: es el único corte (~2 s, el cambio de contenedor en los puertos 80/443)
$COMPOSE up -d --no-deps proxy || echo "⚠️  el proxy no arrancó"

echo "▶ Comprobando salud…"
for _ in $(seq 1 30); do
  if curl -fsS "https://${DOMINIO}/health/ready/" >/dev/null; then
    echo "$VERSION" > .version-actual
    # y en .env: cualquier "docker compose …" que se lance después a mano (run, up -d) usará ESTA
    # versión y no la que hubiera en .env (latest, que tras una vuelta atrás puede ser la rota)
    sed -i "s/^VERSION=.*/VERSION=$VERSION/" .env
    docker image prune -f >/dev/null
    echo "✅ $VERSION desplegada"
    exit 0
  fi
  sleep 2
done

echo "❌ La versión $VERSION no responde: volviendo a $ANTERIOR"
# shellcheck disable=SC2086
VERSION=$ANTERIOR ./infra/rotar-web.sh
# shellcheck disable=SC2086
VERSION=$ANTERIOR $COMPOSE up -d --no-deps $SERVICIOS proxy
sed -i "s/^VERSION=.*/VERSION=$ANTERIOR/" .env
exit 1
