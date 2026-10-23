import { APIRequestContext } from '@playwright/test';

import { entrar, expect, sinViolaciones, test, vigilarConsola } from './ayuda';

/** El enlace del último correo a `para`, leído del backend E2E de este worker (correos en memoria: config/urls_e2e.py). */
async function enlaceDelCorreo(request: APIRequestContext, para: string, asunto: string) {
  const backend = `http://localhost:${8000 + test.info().parallelIndex}`;
  const r = await request.get(`${backend}/e2e/correos`, { params: { para } });
  const { correos } = (await r.json()) as { correos: { asunto: string; cuerpo: string }[] };
  const ultimo = correos.at(-1);
  expect(ultimo?.asunto).toBe(asunto);
  const enlace = new URL(ultimo!.cuerpo.match(/https?:\/\/\S+/)![0]);
  return enlace.pathname + enlace.search; // /completar-registro?uid=…&token=…
}

test('crear una cuenta: el email, el enlace del correo, la contraseña y entrar', async ({
  page,
  request,
}) => {
  const sinErrores = vigilarConsola(page);
  const email = `nueva-${Date.now()}@example.com`; // con reintentos (CI), cada intento con un email sin usar
  const password = 'una-clave-bien-larga';

  await page.goto('/login');
  await page.getByRole('link', { name: 'Crear cuenta' }).click();
  await expect(page).toHaveURL(/\/registro$/); // antes de escribir: el login también tiene «Email»
  await page.getByLabel('Email').fill(email);
  await sinViolaciones(page);
  await page.getByRole('button', { name: 'Crear cuenta' }).click();
  await expect(page.getByRole('status')).toHaveText(
    'Revisa tu email: te hemos enviado un enlace para continuar.',
  );

  await page.goto(await enlaceDelCorreo(request, email, 'Completa tu registro'));
  await page.getByLabel('Contraseña nueva').fill(password);
  await page.getByLabel('Repite la contraseña').fill(password);
  await sinViolaciones(page);
  await page.getByRole('button', { name: 'Activar la cuenta' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText('Cuenta activada. Ya puedes entrar.')).toBeVisible();
  await sinViolaciones(page);

  await entrar(page, { email, password });
  await expect(page.getByRole('heading', { name: 'Mis hogares' })).toBeVisible(); // aún sin hogares
  sinErrores();
});
