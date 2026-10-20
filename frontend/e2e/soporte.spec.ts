import { expect, test } from '@playwright/test';

import { entrar, SOPORTE } from './ayuda';

test('un usuario normal no ve ni puede abrir el backoffice', async ({ page }) => {
  await entrar(page);
  await page.getByRole('button', { name: 'Mi cuenta' }).click();
  await expect(page.getByRole('menuitem', { name: 'Soporte' })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.goto('/soporte');
  await expect(page).not.toHaveURL(/soporte/);
});

test('el personal de soporte ve el panel y la auditoría', async ({ page }) => {
  await entrar(page, SOPORTE);
  await page.getByRole('button', { name: 'Mi cuenta' }).click();
  await page.getByRole('menuitem', { name: 'Soporte' }).click();
  await expect(page.getByText('Tickets atascados')).toBeVisible();
  await page.getByRole('tab', { name: 'Hogares' }).click();
  await expect(page.getByRole('link', { name: 'Casa demo' })).toBeVisible();
  await page.getByRole('tab', { name: 'Auditoría' }).click();
  await expect(page.getByRole('combobox', { name: 'Tipo' })).toBeVisible();
});
