// Proxy de `ng serve` para los E2E en paralelo (módulo 82): cada worker tiene su backend en BACKEND_PORT.
const destino = `http://localhost:${process.env['BACKEND_PORT'] ?? 8000}`;

export default {
  '/api': { target: destino, secure: false },
  '/media': { target: destino, secure: false },
  '/ws': { target: destino, secure: false, ws: true },
};
