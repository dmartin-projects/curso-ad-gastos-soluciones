import { defineConfig, devices } from '@playwright/test';

/**
 * Módulo 83, ejercicio 4: el recorrido contra la PRODUCCIÓN levantada en local (compose.prod.yaml +
 * compose.ci.yaml, DOMINIO=localhost). Sin webServer: el stack ya está arriba.
 *   npx playwright test -c playwright.produccion.config.ts
 */
export default defineConfig({
  testDir: 'e2e-produccion',
  timeout: 120_000,
  workers: 1,
  reporter: process.env['CI'] ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env['PROD_URL'] ?? 'https://localhost',
    // Caddy firma el certificado de "localhost" con su propia CA local, que el navegador no conoce
    ignoreHTTPSErrors: true,
    locale: 'es-ES',
    timezoneId: 'Europe/Madrid',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: {
      ...(process.env['CHROMIUM_PATH'] ? { executablePath: process.env['CHROMIUM_PATH'] } : {}),
      args: ['--ignore-certificate-errors'], // también para el service worker (ignoreHTTPSErrors no llega)
    },
  },
});
