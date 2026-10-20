import { DEMO, SOPORTE, entrar, expect, sinViolaciones, test } from './ayuda';

test.describe('Módulo 81: ejercicios', () => {
  test('aviso de conexión: a los 10 s sin WebSocket aparece, y se va al reconectar', async ({
    page,
  }) => {
    test.setTimeout(90_000);
    let cortado = true;
    // el servidor "no responde": cada intento de WebSocket se cierra en cuanto se abre
    await page.routeWebSocket(/\/ws\//, (ws) => {
      if (cortado) ws.close({ code: 1011 });
      else ws.connectToServer();
    });
    await entrar(page);
    const aviso = page.getByRole('status').filter({ hasText: 'Sin conexión en tiempo real' });
    await expect(aviso).toBeHidden();
    await expect(aviso).toBeVisible({ timeout: 15_000 });
    cortado = false; // vuelve el servidor: el siguiente reintento (≤ 30 s) conecta
    await expect(aviso).toBeHidden({ timeout: 45_000 });
  });

  test('si el servidor cierra limpiamente (4000: cambiaron mis hogares) se reconecta con otro ticket', async ({
    page,
  }) => {
    let conexiones = 0;
    await page.routeWebSocket(/\/ws\//, (ws) => {
      conexiones++;
      ws.connectToServer();
      if (conexiones === 1) setTimeout(() => ws.close({ code: 4000, reason: 'grupos' }), 1_000);
    });
    const tickets: string[] = [];
    page.on('request', (r) => r.url().includes('/ws-ticket/') && tickets.push(r.url()));
    await entrar(page);
    await expect.poll(() => conexiones, { timeout: 10_000 }).toBe(2); // repeat(): 1 s después
    expect(tickets).toHaveLength(2); // cada conexión, su ticket de un solo uso
  });

  test('modo oscuro manual, recordado al recargar', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' });
    await entrar(page);
    const esquema = () =>
      page.evaluate(() => getComputedStyle(document.documentElement).colorScheme);
    const fondo = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    const boton = page.getByRole('button', { name: /^Tema:/ });

    await expect(boton).toHaveAccessibleName('Tema: del sistema. Cambiar');
    const claro = await fondo();
    await boton.click(); // claro
    await boton.click(); // oscuro
    await expect(boton).toHaveAccessibleName('Tema: oscuro. Cambiar');
    expect(await esquema()).toBe('dark');
    expect(await fondo()).not.toBe(claro); // Material cambia de verdad (light-dark())
    await sinViolaciones(page); // el contraste también en oscuro

    await page.reload();
    await expect(page.getByRole('button', { name: /^Tema:/ })).toHaveAccessibleName(
      'Tema: oscuro. Cambiar',
    );
    expect(await esquema()).toBe('dark');
    await page.getByRole('button', { name: /^Tema:/ }).click(); // vuelta a "sistema"
    expect(await esquema()).toBe('light dark');
  });

  test('soporte recategoriza en bloque los movimientos sin categoría de un hogar', async ({
    page,
    request,
  }) => {
    // dos gastos sin categoría, creados por la usuaria demo por la API
    const { access } = await (await request.post('/api/v1/auth/login/', { data: DEMO })).json();
    const auth = { Authorization: `Bearer ${access}` };
    const cuentas = await (
      await request.get('/api/v1/hogares/1/cuentas/', { headers: auth })
    ).json();
    for (const concepto of ['Sin cat A', 'Sin cat B']) {
      const r = await request.post('/api/v1/hogares/1/movimientos/', {
        headers: auth,
        data: { fecha: '2026-10-02', importe: '-3.00', concepto, cuenta: cuentas[0].id },
      });
      expect(r.status()).toBe(201);
    }

    await entrar(page, SOPORTE);
    await page.goto('/soporte/hogares/1');
    await expect(page.getByRole('heading', { name: /Movimientos sin categoría/ })).toBeVisible();
    await page.getByRole('checkbox', { name: 'Seleccionar Sin cat A' }).check();
    await page.getByRole('checkbox', { name: 'Seleccionar Sin cat B' }).check();
    await page.getByRole('combobox', { name: 'Categoría destino' }).selectOption({ label: 'Ocio' });
    await sinViolaciones(page);
    await page.getByRole('button', { name: 'Recategorizar (2)' }).click();
    await expect(page.getByText('2 recategorizados')).toBeVisible();
    await expect(page.getByRole('checkbox', { name: 'Seleccionar Sin cat A' })).toHaveCount(0);

    // y queda en la auditoría, a nombre del personal
    await page.goto('/soporte/auditoria');
    await expect(page.getByText(/Sin cat A/).first()).toBeVisible();
  });
});
