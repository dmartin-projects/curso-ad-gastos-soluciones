import { test as base, expect, Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/**
 * El `test` de todos los specs: igual que el de Playwright, pero con la baseURL del worker
 * (http://localhost:4200, 4201…). Así `page.goto('/…')` y `request` van a SU servidor (módulo 82).
 */
export const test = base.extend({
  // eslint-disable-next-line no-empty-pattern
  baseURL: async ({}, usar, info) => usar(`http://localhost:${4200 + info.parallelIndex}`),
});
export { expect };

export const DEMO = { email: 'demo@example.com', password: 'demo12345-demo' };
export const SOPORTE = { email: 'soporte@example.com', password: 'soporte12345' };

/**
 * Login por la interfaz en cada test. No sirve guardar la sesión con `storageState`: el refresh token ROTA
 * en cada uso (ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION, módulo 35) y la cookie guardada quedaría
 * en la lista negra tras el primer test.
 */
export async function entrar(page: Page, usuario = DEMO) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(usuario.email);
  await page.getByLabel('Contraseña').fill(usuario.password);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page).not.toHaveURL(/login/);
}

/** Falla el test si la página escribe errores en la consola (salvo el 401 esperado del primer refresh). */
export function vigilarConsola(page: Page) {
  const errores: string[] = [];
  page.on('pageerror', (e) => errores.push(e.message));
  page.on('console', (m) => {
    if (m.type() === 'error' && !m.text().includes('401')) errores.push(m.text());
  });
  return () => expect(errores, errores.join('\n')).toEqual([]);
}

/**
 * Módulo 82: accesibilidad automática con axe-core. Falla con los problemas GRAVES (serious/critical)
 * de WCAG 2.1 A/AA en lo que se ve ahora mismo. No sustituye a probar con teclado y lector de pantalla:
 * axe detecta en torno a un tercio de los problemas reales.
 */
export async function sinViolaciones(page: Page) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  const graves = violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map(
      (v) =>
        `${v.id} (${v.impact}): ${v.help} → ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`,
    );
  expect(graves, graves.join('\n')).toEqual([]);
}
