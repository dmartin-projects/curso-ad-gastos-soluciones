import { expect, test } from '@playwright/test';

import { entrar, vigilarConsola } from './ayuda';

test('importar un extracto: vista previa, confirmar y movimientos creados', async ({ page }) => {
  const sinErrores = vigilarConsola(page);
  await entrar(page);
  await page.getByRole('link', { name: 'Importar extracto' }).click();
  // las cuentas llegan de la API: el botón se habilita cuando hay una elegida
  await expect(page.getByRole('button', { name: 'Elegir archivo' })).toBeEnabled();
  await page.locator('input[type=file]').setInputFiles('e2e/fixtures/extracto.csv');

  await expect(page.getByText('Lista para revisar')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('3 de 3')).toBeVisible();
  await expect(page.getByText('LIBRERIA PARIS')).toBeVisible();

  await page.getByRole('button', { name: /Importar 3 movimientos/ }).click();
  await expect(page.getByText('Completada', { exact: false }).first()).toBeVisible({
    timeout: 15_000,
  });

  await page.getByRole('link', { name: 'Movimientos' }).click();
  await expect(page.getByRole('button', { name: /TRANSFERENCIA DE ANA/ })).toContainText(
    '150,00 €',
  );
  sinErrores();
});
