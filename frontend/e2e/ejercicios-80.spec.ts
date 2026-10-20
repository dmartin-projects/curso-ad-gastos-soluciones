import { readFile } from 'node:fs/promises';

import { DEMO, entrar, expect, sinViolaciones, test, vigilarConsola } from './ayuda';

test.describe('Módulo 80: ejercicios', () => {
  test('cambiar la categoría en línea, optimista y con vuelta atrás si falla', async ({ page }) => {
    await entrar(page); // (sin vigilarConsola: el 500 provocado al final escribe un error en la consola)
    await page.goto('/hogares/1/movimientos');
    const fila = page.locator('[data-fila]').first(); // la primera fila de la lista
    const chip = fila.getByRole('button', { name: /^Categoría:/ });
    await expect(chip).toBeVisible();

    // La API tarda 1,5 s: la fila tiene que cambiar ANTES de que responda
    let soltar!: () => void;
    const respondida = new Promise<void>((r) => (soltar = r));
    await page.route('**/api/v1/hogares/1/movimientos/*/', async (ruta) => {
      if (ruta.request().method() !== 'PATCH') return ruta.fallback();
      await new Promise((r) => setTimeout(r, 1500));
      await ruta.fallback();
      soltar();
    });
    await chip.click();
    await page.getByRole('menuitem', { name: 'Educación' }).click();
    await expect(chip).toHaveAccessibleName(/Educación/, { timeout: 500 }); // optimista: sin esperar
    await respondida;
    await expect(chip).toHaveAccessibleName(/Educación/); // y se queda tras revalidar
    await page.unroute('**/api/v1/hogares/1/movimientos/*/');

    // Si la API falla, la fila vuelve a como estaba y se avisa
    await page.route('**/api/v1/hogares/1/movimientos/*/', (ruta) =>
      ruta.request().method() === 'PATCH'
        ? ruta.fulfill({ status: 500, body: '{}' })
        : ruta.fallback(),
    );
    await chip.click();
    await page.getByRole('menuitem', { name: 'Ropa' }).click();
    await expect(page.getByText('No se ha podido cambiar la categoría')).toBeVisible();
    await expect(chip).toHaveAccessibleName(/Educación/);
  });

  test('exportar a CSV lo que se ve, con sus filtros', async ({ page }) => {
    const sinErrores = vigilarConsola(page);
    await entrar(page);
    await page.goto('/hogares/1/movimientos?q=mercadona');
    const descarga = page.waitForEvent('download');
    await page.getByRole('button', { name: 'CSV' }).click();
    const archivo = await descarga;
    expect(archivo.suggestedFilename()).toBe('movimientos-1.csv'); // el de Content-Disposition
    const lineas = (await readFile(await archivo.path(), 'utf-8')).trim().split(/\r?\n/); // csv de Python: \r\n
    expect(lineas[0]).toBe('fecha;concepto;importe;cuenta;categoría;etiquetas');
    expect(lineas.length).toBeGreaterThan(1);
    expect(lineas.slice(1).every((l) => /mercadona/i.test(l))).toBe(true); // solo lo filtrado
    sinErrores();
  });

  test('atajos: "n" y "/" fuera de los campos; dentro son letras', async ({ page }) => {
    await entrar(page);
    await page.goto('/hogares/1/movimientos');
    await page.getByRole('heading', { name: 'Movimientos' }).click(); // foco fuera de los campos
    await page.keyboard.press('n');
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden();

    await sinViolaciones(page);
    await page.keyboard.press('/');
    const buscar = page.getByRole('searchbox', { name: 'Buscar' });
    await expect(buscar).toBeFocused();
    await page.keyboard.type('nómina');
    await expect(buscar).toHaveValue('nómina'); // la "n" y la "/" se escriben: no abren nada
    await expect(page.getByRole('dialog')).toBeHidden();
  });

  test('recordar el último hogar', async ({ page, request }) => {
    await entrar(page);
    // un segundo hogar: con dos, /hogares ya no salta solo
    await page.goto('/hogares?elegir=1');
    await page.getByLabel('Nuevo hogar').fill('Casa de la playa');
    await page.getByRole('button', { name: 'Crear' }).click();
    await expect(page).toHaveURL(/\/hogares\/(\d+)/);
    await expect(page.getByRole('heading', { name: /./ }).first()).toBeVisible();
    const nuevo = Number(page.url().match(/\/hogares\/(\d+)/)![1]);

    // Cada page.goto recarga la app y renueva la sesión con la cookie de refresh, que ROTA (módulo 35).
    // Esperar a que la página termine antes de la siguiente: si no, la recarga aborta la respuesta con
    // la cookie nueva, la vieja ya está en la lista negra… y se acaba en el login.
    await page.goto('/hogares/1/movimientos'); // el último visitado es el 1
    await expect(page.getByRole('heading', { name: 'Movimientos' })).toBeVisible();
    await page.goto('/hogares');
    await expect(page).toHaveURL(/\/hogares\/1\b/); // salta al recordado
    await expect(page.getByRole('heading').first()).toBeVisible();
    await page.goto('/hogares?elegir=1');
    await expect(page.getByRole('link', { name: /Casa de la playa/ })).toBeVisible(); // la lista, a demanda

    // limpieza: los demás tests esperan un solo hogar
    const { access } = await (await request.post('/api/v1/auth/login/', { data: DEMO })).json();
    const r = await request.delete(`/api/v1/hogares/${nuevo}/`, {
      headers: { Authorization: `Bearer ${access}` },
    });
    expect(r.status()).toBe(204);
  });
});
