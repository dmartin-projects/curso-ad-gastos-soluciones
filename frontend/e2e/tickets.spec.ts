import { entrar, expect, sinViolaciones, test, vigilarConsola } from './ayuda';

test('subir la foto de un ticket: OCR + IA y el gasto aparece solo, sin recargar', async ({
  page,
}) => {
  const sinErrores = vigilarConsola(page);
  await entrar(page);
  await page.getByRole('link', { name: 'Tickets' }).click();

  // las cuentas llegan de la API: el botón se habilita cuando hay una elegida
  await expect(page.getByRole('button', { name: 'Hacer foto o elegir archivo' })).toBeEnabled();
  await page.locator('input[type=file]').setInputFiles('e2e/fixtures/ticket.png');

  // OCR real (Tesseract) + IA simulada en el backend E2E; el estado llega por WebSocket
  const ticket = page.getByRole('link', { name: /Mercadona/ });
  await expect(ticket).toContainText('Listo', { timeout: 30_000 });
  await expect(ticket).toContainText('-4,85 €');
  // y la notificación llega por el WebSocket (los tests comparten BD: no se cuenta, se busca el aviso)
  await expect(page.getByText('Ticket de Mercadona procesado')).toBeVisible();
  await sinViolaciones(page);

  await ticket.click();
  await expect(page.getByRole('img', { name: 'Foto del ticket' })).toBeVisible();
  await sinViolaciones(page);
  sinErrores();
});
