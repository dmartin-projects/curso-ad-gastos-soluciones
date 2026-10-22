# syntax=docker/dockerfile:1
# infra/proxy.Dockerfile — Caddy con la SPA dentro (contexto: la raíz del proyecto)
FROM node:24-alpine AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ .
RUN npx ng build --configuration production
# La CSP de la cabecera, con los hashes que autoCsp ha calculado para ESTE index.html (módulo 83)
COPY infra/csp.mjs /tmp/csp.mjs
RUN node /tmp/csp.mjs dist/gastos/browser/index.html > /tmp/csp.caddy

FROM caddy:2.10-alpine
COPY infra/Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend /tmp/csp.caddy /etc/caddy/csp.caddy
COPY --from=frontend /app/dist/gastos/browser /srv/frontend
