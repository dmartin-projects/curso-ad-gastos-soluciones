import { entrar, expect, sinViolaciones, test, vigilarConsola } from './ayuda';

test('crear un gasto y encontrarlo con la búsqueda', async ({ page }) => {
  const sinErrores = vigilarConsola(page);
  await entrar(page);
  await page.getByRole('link', { name: 'Movimientos' }).click();

  await sinViolaciones(page); // la lista
  await page.getByRole('button', { name: 'Nuevo' }).click();
  const dialogo = page.getByRole('dialog');
  await expect(dialogo.getByLabel('Concepto')).toBeVisible();
  await sinViolaciones(page); // el diálogo abierto (foco atrapado, etiquetas)
  await dialogo.getByLabel('Importe (€)').fill('18.40');
  await dialogo.getByLabel('Concepto').fill('Cena cumpleaños');
  await dialogo.getByRole('combobox', { name: /Cuenta/ }).click();
  await page.getByRole('option', { name: 'Cuenta común' }).click();
  await dialogo.getByRole('radio', { name: /Restaurantes/ }).click();
  await dialogo.getByRole('button', { name: 'Guardar' }).click();
  await expect(dialogo).toBeHidden();

  await page.getByRole('searchbox', { name: 'Buscar' }).fill('cumpleaños');
  await expect(page).toHaveURL(/q=cumplea/); // el filtro vive en la URL
  const fila = page.locator('[data-fila]', { hasText: 'Cena cumpleaños' }); // la fila (no es un botón: módulo 82)
  await expect(fila).toContainText('-18,40 €');
  await expect(fila).toContainText('Restaurantes');
  sinErrores();
});

test('los errores de validación se ven sin llamar a la API', async ({ page }) => {
  await entrar(page);
  await page.goto('/hogares/1/movimientos');
  await page.getByRole('button', { name: 'Nuevo' }).click();
  let peticiones = 0;
  page.on(
    'request',
    (r) => r.method() === 'POST' && r.url().includes('/movimientos/') && peticiones++,
  );
  await page.getByRole('dialog').getByRole('button', { name: 'Guardar' }).click();
  await expect(page.getByText('Indica el importe')).toBeVisible();
  expect(peticiones).toBe(0);
});
