import { entrar, expect, sinViolaciones, test } from './ayuda';

test('en el móvil el menú lateral se abre con el botón @movil', async ({ page }) => {
  await entrar(page);
  await expect(page.getByRole('link', { name: 'Movimientos' })).toBeHidden();
  await page.getByRole('button', { name: 'Menú' }).click();
  await page.getByRole('link', { name: 'Movimientos' }).click();
  await expect(page.getByRole('heading', { name: 'Movimientos' })).toBeVisible();
  await sinViolaciones(page); // en el móvil también (tamaños táctiles, zoom)
});
