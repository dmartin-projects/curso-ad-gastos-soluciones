#!/usr/bin/env bash
# infra/ci/env.sh > .env — el .env de producción para probarla en el CI (módulo 83, ejercicio 4).
# Las mismas variables que el .env del servidor (módulo 83, §8), con secretos aleatorios de usar y tirar
# y los servicios externos apuntando a los dobles de compose.ci.yaml.
set -euo pipefail
secreto() { openssl rand -hex 32; }
PG=$(secreto)
RABBIT=$(secreto)
cat <<FIN
VERSION=${VERSION:-ci}
GHCR_OWNER=${GHCR_OWNER:-ci}
DOMINIO=localhost
ACME_EMAIL=ci@example.com
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=$(secreto)
JWT_SIGNING_KEY=$(secreto)
DJANGO_ALLOWED_HOSTS=localhost
DJANGO_CSRF_TRUSTED_ORIGINS=https://localhost
FRONTEND_URL=https://localhost
SECURE_HSTS_SECONDS=60
LOG_FORMAT=json
POSTGRES_DB=gastos
POSTGRES_USER=gastos
POSTGRES_PASSWORD=$PG
DATABASE_URL=postgres://gastos:$PG@db:5432/gastos
REDIS_URL=redis://redis:6379/1
REDIS_CHANNELS_URL=redis://redis:6379/2
CELERY_RESULT_BACKEND=redis://redis:6379/0
RABBITMQ_USER=gastos
RABBITMQ_PASSWORD=$RABBIT
CELERY_BROKER_URL=amqp://gastos:$RABBIT@rabbitmq:5672//
S3_BUCKET=gastos
S3_ENDPOINT_URL=http://s3:9000
S3_REGION=us-east-1
S3_ACCESS_KEY=ci
S3_SECRET_KEY=ci
DEFAULT_FROM_EMAIL='"Gastos" <no-responder@localhost>'
SMTP_HOST=smtp
SMTP_PORT=1025
SMTP_USER=ci
SMTP_PASSWORD=ci
IA_API_KEY=ci
IA_BASE_URL=http://ia:9100/
IA_MODELO=falso
SENTRY_DSN=
FIN
