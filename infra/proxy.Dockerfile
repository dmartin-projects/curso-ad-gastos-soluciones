# syntax=docker/dockerfile:1
# infra/proxy.Dockerfile — Caddy con la SPA dentro (contexto: la raíz del proyecto)
FROM node:24-alpine AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ .
RUN npx ng build --configuration production

FROM caddy:2.10-alpine
COPY infra/Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend /app/dist/gastos/browser /srv/frontend
