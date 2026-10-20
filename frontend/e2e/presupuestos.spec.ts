import { DEMO, entrar, expect, sinViolaciones, test, vigilarConsola } from './ayuda';

test('superar un presupuesto avisa en tiempo real y pinta la barra en rojo', async ({
  page,
  request,
}) => {
  test.setTimeout(60_000); // espera a Celery + WebSocket; con varios workers la máquina va cargada
  const sinErrores = vigilarConsola(page);
  // El seed pone gastos aleatorios: lo ya gastado este mes en Restaurantes se lee de la API, y el límite
  // se fija 10 € por encima (así el aviso lo provoca el gasto del test, no la creación del presupuesto)
  const { access } = await (await request.post('/api/v1/auth/login/', { data: DEMO })).json();
  const resumen = await (
    await request.get('/api/v1/hogares/1/dashboard/', {
      headers: { Authorization: `Bearer ${access}` },
    })
  ).json();
  const yaGastado = Number(
    resumen.por_categoria.find((c: { nombre: string }) => c.nombre === 'Restaurantes')?.total ?? 0,
  );
  const limite = (Math.ceil(yaGastado) + 10).toString();

  await entrar(page);
  await page.goto('/hogares/1/presupuestos');
  await expect(page.getByRole('heading', { name: /Presupuestos de/ })).toBeVisible();
  // Al conectar el WebSocket se revalidan los datos del hogar y la pantalla se repinta: si eso pilla el
  // desplegable abierto, se cierra. toPass() reintenta abrir y elegir hasta que sale.
  await expect(async () => {
    await page.getByRole('combobox', { name: 'Categoría' }).click();
    await page.getByRole('option', { name: 'Restaurantes', exact: true }).click({ timeout: 2_000 });
  }).toPass({ timeout: 20_000 });
  await page.getByLabel('Límite (€)').fill(limite);
  await page.getByRole('button', { name: 'Añadir' }).click();
  await expect(page.getByText(new RegExp(`/ ${limite},00 €`))).toBeVisible();
  await sinViolaciones(page);

  await page.getByRole('link', { name: 'Movimientos' }).click();
  await page.getByRole('button', { name: 'Nuevo' }).click();
  const dialogo = page.getByRole('dialog');
  await dialogo.getByLabel('Importe (€)').fill('18.40');
  await dialogo.getByLabel('Concepto').fill('Cena de aniversario');
  await dialogo.getByRole('combobox', { name: /Cuenta/ }).click();
  await page.getByRole('option', { name: 'Cuenta común' }).click();
  await dialogo.getByRole('radio', { name: /Restaurantes/ }).click();
  await dialogo.getByRole('button', { name: 'Guardar' }).click();

  // por el WebSocket: Celery comprueba el presupuesto y la notificación llega sin recargar
  await expect(page.getByText('Presupuesto de Restaurantes superado')).toBeVisible({
    timeout: 15_000,
  });

  await page.getByRole('link', { name: 'Resumen' }).click();
  const fila = page.locator('div.mb-3', { hasText: 'Restaurantes' });
  await expect(fila.locator('mat-progress-bar')).toHaveClass(/excedido/);
  sinErrores();
});
