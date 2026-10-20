import { defineConfig, devices } from '@playwright/test';

/**
 * Módulo 82: E2E en paralelo. Cada worker tiene SU backend (puerto 8000+i, BD gastos_e2e_i) y SU
 * `ng serve` (4200+i). `e2e/ayuda.ts` apunta cada test al de su worker (testInfo.parallelIndex).
 * E2E_WORKERS=1 (por defecto) es el comportamiento de siempre.
 */
const WORKERS = Number(process.env['E2E_WORKERS'] ?? 1);
const indices = [...Array(WORKERS).keys()];

/**
 * Pruebas de punta a punta contra el backend de verdad (config.settings.e2e, módulo 82).
 * Playwright arranca los dos servidores; el del backend, siempre nuevo y con la BD recién preparada.
 */
export default defineConfig({
  testDir: 'e2e',
  fullyParallel: false, // dentro de un worker, en serie (comparten su BD)
  workers: WORKERS,
  retries: process.env['CI'] ? 1 : 0,
  reporter: process.env['CI'] ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://localhost:4200',
    locale: 'es-ES',
    timezoneId: 'Europe/Madrid',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // en el contenedor de este curso Chromium ya está instalado aquí; en tu máquina, `npx playwright install chromium`
        launchOptions: process.env['CHROMIUM_PATH']
          ? { executablePath: process.env['CHROMIUM_PATH'] }
          : {},
      },
      grepInvert: /@movil/,
    },
    {
      name: 'movil',
      use: {
        ...devices['Pixel 7'],
        launchOptions: process.env['CHROMIUM_PATH']
          ? { executablePath: process.env['CHROMIUM_PATH'] }
          : {},
      },
      grep: /@movil/,
    },
  ],
  webServer: indices.flatMap((i) => [
    {
      // --crear-bd: crea gastos_e2e_i si no existe y migra; después, datos conocidos
      command: `uv run python manage.py preparar_e2e --crear-bd && uv run python manage.py runserver ${8000 + i} --noreload`,
      cwd: '../backend',
      env: {
        DJANGO_SETTINGS_MODULE: 'config.settings.e2e',
        E2E_DB_NAME: WORKERS > 1 ? `gastos_e2e_${i}` : 'gastos_e2e',
        E2E_PUERTO: String(8000 + i),
      },
      url: `http://localhost:${8000 + i}/health/live/`,
      reuseExistingServer: false, // siempre un proceso nuevo: su caché en memoria también empieza vacía
      stdout: 'ignore' as const,
      timeout: 120_000,
    },
    {
      command: `npx ng serve --port ${4200 + i} --proxy-config e2e/proxy.e2e.mjs`,
      env: { BACKEND_PORT: String(8000 + i) },
      url: `http://localhost:${4200 + i}`,
      reuseExistingServer: !process.env['CI'],
      timeout: 180_000,
    },
  ]),
});
