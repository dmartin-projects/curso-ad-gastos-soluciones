#!/usr/bin/env bash
# infra/rotar-web.sh — cambia las réplicas de "web" sin cortar peticiones (módulo 83, ejercicio 3)
# 1) arranca tantas réplicas NUEVAS como viejas haya (con la imagen de VERSION), 2) espera a que estén
# healthy, 3) para las viejas (SIGTERM: terminan lo que tienen en curso). Caddy (dynamic a + lb_try_duration)
# deja de enviarles tráfico en cuanto no responden y reintenta en otra réplica.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE="docker compose -f compose.prod.yaml ${COMPOSE_EXTRA:-}"

mapfile -t viejas < <($COMPOSE ps -q web)
n=${#viejas[@]}
if ((n == 0)); then # primer despliegue: no hay nada que rotar
  $COMPOSE up -d --no-deps --wait web
  exit 0
fi
echo "→ $n réplicas viejas; arrancando $n nuevas"
$COMPOSE up -d --no-deps --no-recreate --scale "web=$((n * 2))" web

for c in $($COMPOSE ps -q web); do
  [[ " ${viejas[*]} " == *" $c "* ]] && continue
  for _ in $(seq 1 60); do # hasta 2 min por réplica
    [[ "$(docker inspect -f '{{.State.Health.Status}}' "$c")" == healthy ]] && break
    sleep 2
  done
  [[ "$(docker inspect -f '{{.State.Health.Status}}' "$c")" == healthy ]] || {
    echo "✗ $c no llega a healthy: se retiran las nuevas y se quedan las viejas"
    mapfile -t nuevas < <($COMPOSE ps -q web | grep -vxF -f <(printf '%s\n' "${viejas[@]}"))
    docker stop "${nuevas[@]}" >/dev/null && docker rm "${nuevas[@]}" >/dev/null
    exit 1
  }
done
echo "→ nuevas healthy; parando las viejas"
docker stop -t 30 "${viejas[@]}" >/dev/null # SIGTERM y hasta 30 s para terminar lo que tengan en curso
docker rm "${viejas[@]}" >/dev/null
echo "✓ $($COMPOSE ps -q web | wc -l) réplicas, todas nuevas"
