import { defineConfig, devices } from '@playwright/test';

/**
 * Pruebas de punta a punta contra el backend de verdad (config.settings.e2e, módulo 82).
 * Playwright arranca los dos servidores; el del backend, siempre nuevo y con la BD recién preparada.
 */
export default defineConfig({
  testDir: 'e2e',
  fullyParallel: false, // comparten una base de datos: en serie
  workers: 1,
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
  webServer: [
    {
      command:
        'uv run python manage.py preparar_e2e && uv run python manage.py runserver 8000 --noreload',
      cwd: '../backend',
      env: { DJANGO_SETTINGS_MODULE: 'config.settings.e2e' },
      url: 'http://localhost:8000/health/live/',
      reuseExistingServer: false, // siempre un proceso nuevo: su caché en memoria también empieza vacía
      stdout: 'ignore',
      timeout: 120_000,
    },
    {
      command: 'npx ng serve --port 4200',
      url: 'http://localhost:4200',
      reuseExistingServer: !process.env['CI'],
      timeout: 180_000,
    },
  ],
});
