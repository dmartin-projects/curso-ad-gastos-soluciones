import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { Categoria, Hogar, Movimiento } from '../../core/api/tipos';
import { HogarStore } from '../../core/hogar/hogar-store';
import { esCampoDeTexto } from '../../shared/utils/atajos';
import { conCategoria, PaginasMovimientos } from './services/consultas';

const mov = (id: number, categoria: number | null = null) =>
  ({
    id,
    concepto: `M${id}`,
    categoria,
    categoria_nombre: null,
    categoria_color: null,
  }) as Movimiento;

describe('Ejercicio 1: actualización optimista sobre las páginas', () => {
  const datos: PaginasMovimientos = {
    pages: [
      { results: [mov(1), mov(2)], next: 'x', previous: null },
      { results: [mov(3)], next: null, previous: 'x' },
    ],
    pageParams: [null, 'x'],
  };
  const ocio = { id: 9, nombre: 'Ocio', color: '#8e24aa' } as Categoria;

  it('cambia solo esa fila, en la página que sea, sin mutar el original', () => {
    const nuevo = conCategoria(datos, 3, ocio)!;
    expect(nuevo.pages[1].results[0]).toMatchObject({
      categoria: 9,
      categoria_nombre: 'Ocio',
      categoria_color: '#8e24aa',
    });
    expect(nuevo.pages[0]).toEqual(datos.pages[0]); // mismas filas…
    expect(nuevo).not.toBe(datos); // …pero objetos nuevos: TanStack detecta el cambio por referencia
    expect(datos.pages[1].results[0].categoria).toBeNull(); // el original, intacto (para deshacer)
    expect(nuevo.pageParams).toBe(datos.pageParams);
  });

  it('quitar la categoría y una caché vacía', () => {
    const con = conCategoria(datos, 1, ocio);
    expect(conCategoria(con, 1, null)!.pages[0].results[0]).toMatchObject({
      categoria: null,
      categoria_nombre: null,
    });
    expect(conCategoria(undefined, 1, ocio)).toBeUndefined();
  });
});

describe('Ejercicio 3: recordar el último hogar', () => {
  const hogares = [{ id: 3 }, { id: 7 }] as Hogar[];
  let store: InstanceType<typeof HogarStore>;

  beforeEach(async () => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    store = TestBed.inject(HogarStore);
    const cargando = store.cargar();
    TestBed.inject(HttpTestingController)
      .expectOne((r) => r.url === '/api/v1/hogares/')
      .flush({ count: 2, next: null, previous: null, results: hogares });
    await cargando;
  });

  it('recuerda el que se selecciona y lo olvida al cerrar sesión', () => {
    expect(store.ultimo()).toBeNull();
    store.seleccionar(7);
    expect(store.ultimo()).toBe(7);
    store.reiniciar();
    expect(localStorage.getItem('gastos.ultimoHogar')).toBeNull();
  });

  it('ignora un hogar que ya no es mío', () => {
    localStorage.setItem('gastos.ultimoHogar', '99');
    expect(store.ultimo()).toBeNull();
  });

  it('sin localStorage (modo privado) no rompe', () => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new DOMException('QuotaExceededError');
    };
    try {
      expect(() => store.seleccionar(3)).not.toThrow();
    } finally {
      Storage.prototype.setItem = original;
    }
  });
});

describe('Ejercicio 4: cuándo NO es un atajo', () => {
  const el = (html: string) => {
    const div = document.createElement('div');
    div.innerHTML = html;
    return div.firstElementChild;
  };

  it.each([
    ['<input type="text">', true],
    ['<input type="search">', true],
    ['<input>', true],
    ['<textarea></textarea>', true],
    ['<select></select>', true],
    ['<div contenteditable="true"></div>', true],
    ['<div role="combobox"></div>', true],
    ['<input type="checkbox">', false],
    ['<button>Nuevo</button>', false],
    ['<div tabindex="0" role="button"></div>', false],
  ])('%s → %s', (html, esperado) => {
    const nodo = el(html)!;
    document.body.append(nodo); // isContentEditable solo funciona en el documento
    expect(esCampoDeTexto(nodo)).toBe(esperado);
    nodo.remove();
  });

  it('el documento (sin foco en nada) sí admite atajos', () => {
    expect(esCampoDeTexto(document.body)).toBe(false);
    expect(esCampoDeTexto(null)).toBe(false);
  });
});
