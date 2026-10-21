import { expect, test } from '@playwright/test';

/**
 * Módulo 83, ejercicio 4. Lo que solo se ve con la configuración de producción detrás de Caddy: cada
 * bloque comprueba uno de los fallos de la tabla del §9, que ni los tests unitarios ni los E2E del
 * módulo 82 (ng serve + runserver, sin CSP, channel layer en memoria) podían ver.
 */
const DEMO = { email: 'demo@example.com', password: 'demo12345-demo' };

test('producción: estilos con CSP, caché, ticket por RabbitMQ y un solo WebSocket', async ({
  page,
  request,
}) => {
  const sockets: string[] = [];
  page.on('websocket', (ws) => sockets.push(ws.url()));
  const csp: string[] = [];
  page.on('console', (m) => {
    if (m.text().includes('Content Security Policy')) csp.push(m.text());
  });

  // Fallo 1: CSS crítico + CSP. La hoja completa debe acabar en media="all" y los iconos con su fuente
  await page.goto('/login');
  await expect
    .poll(() =>
      page.evaluate(() =>
        [...document.querySelectorAll<HTMLLinkElement>('link[rel=stylesheet]')].map((l) => l.media),
      ),
    )
    .toEqual(['all']);
  await page.getByLabel('Email').fill(DEMO.email);
  await page.getByLabel('Contraseña').fill(DEMO.password);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page).not.toHaveURL(/login/);
  await expect(page.locator('mat-icon').first()).toHaveCSS('font-family', /Material Symbols/);

  // Fallo 3: caché. Un enlace profundo se revalida; lo que lleva hash, un año; un chunk viejo, 404
  const profundo = await request.get('/hogares/1/tickets');
  expect(profundo.headers()['cache-control']).toBe('no-cache');
  expect(profundo.headers()['strict-transport-security']).toContain('max-age=');
  expect(profundo.headers()['content-security-policy']).toContain("frame-ancestors 'none'");
  const main = (await profundo.text()).match(/main-[\w-]{8}\.js/)![0];
  expect((await request.get(`/${main}`)).headers()['cache-control']).toContain('immutable');
  expect((await request.get('/chunk-NOEXISTE.js')).status()).toBe(404);

  // El ticket: proxy → web → S3 (doble) → RabbitMQ → worker-ocr (Tesseract + IA doble) → WebSocket
  await page.getByRole('link', { name: 'Tickets' }).click();
  await expect(page.getByRole('button', { name: 'Hacer foto o elegir archivo' })).toBeEnabled();
  await page.locator('input[type=file]').setInputFiles('e2e/fixtures/ticket.png');
  const ticket = page.getByRole('link', { name: /Mercadona/ });
  await expect(ticket).toContainText('Listo', { timeout: 60_000 });
  await expect(ticket).toContainText('-4,85 €');
  await ticket.click();
  // la foto, con URL firmada: con firma se descarga, sin firma no
  const foto = await page.getByRole('img', { name: 'Foto del ticket' }).getAttribute('src');
  expect(foto).toContain('X-Amz-Signature='); // firma v4 (signature_version s3v4), igual que en R2
  expect((await request.get(foto!)).ok()).toBe(true);
  expect((await request.get(foto!.split('?')[0])).ok()).toBe(false);

  // Fallo 2: un WebSocket inactivo no debe cerrarse (redis-py 8 + channels_redis lo cerraba a los 5 s)
  await page.waitForTimeout(20_000);
  expect(sockets).toHaveLength(1);
  expect(csp, csp.join('\n')).toEqual([]);
});
