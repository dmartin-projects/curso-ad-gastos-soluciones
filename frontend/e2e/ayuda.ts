import { expect, Page } from '@playwright/test';

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
