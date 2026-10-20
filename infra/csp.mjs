// infra/csp.mjs — genera la cabecera CSP de Caddy a partir del index.html del build (módulo 83, ejercicio 2)
// Con "autoCsp", Angular calcula el hash de cada <script> en línea de index.html (el cargador de main.js y el
// que activa la hoja de estilos tras el CSS crítico) y los pone en un <meta>. Una CSP en <meta> no basta:
// la cabecera del proxy también se aplica, y la política efectiva es la intersección de las dos.
// Uso: node infra/csp.mjs dist/gastos/browser/index.html > csp.caddy
import { readFileSync } from "node:fs";

const html = readFileSync(process.argv[2], "utf8");
const meta = html.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/);
const scriptSrc = meta?.[1].match(/script-src ([^;]+)/)?.[1];
if (!scriptSrc?.includes("'sha256-")) {
  console.error("index.html sin CSP de autoCsp: ¿falta security.autoCsp en angular.json?");
  process.exit(1);
}
const politica = [
  "default-src 'self'",
  `script-src ${scriptSrc}`, // 'strict-dynamic' + hashes: lo que cargue el cargador hereda la confianza
  "worker-src 'self'", // el service worker (sw-gastos.js) no se rige por 'strict-dynamic'
  "img-src 'self' data: blob: https:", // https: para las URLs firmadas de R2 (fotos de tickets)
  "style-src 'self' 'unsafe-inline'", // Angular Material y el CSS crítico usan estilos en línea
  "font-src 'self'",
  "connect-src 'self'", // incluye wss:// del mismo dominio
  "object-src 'none'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
].join("; ");
console.log(`header Content-Security-Policy "${politica}"`);
