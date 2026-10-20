import { entrar, expect, sinViolaciones, test, vigilarConsola } from './ayuda';

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
  await sinViolaciones(page); // la vista previa

  await page.getByRole('button', { name: /Importar 3 movimientos/ }).click();
  await expect(page.getByText('Completada', { exact: false }).first()).toBeVisible({
    timeout: 15_000,
  });

  await page.getByRole('link', { name: 'Movimientos' }).click();
  // Buscarlo: la lista es virtual (solo hay en el DOM las filas visibles) y el seed pone fechas
  // aleatorias, así que el 6 de octubre puede quedar fuera de la pantalla según el día
  await page.getByRole('searchbox', { name: 'Buscar' }).fill('transferencia de ana');
  await expect(page.locator('[data-fila]', { hasText: 'TRANSFERENCIA DE ANA' })).toContainText(
    '150,00 €',
  );
  sinErrores();
});
