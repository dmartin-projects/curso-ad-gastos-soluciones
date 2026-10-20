import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { ArchivoCompartido } from './compartir/archivo-compartido';
import { Tema } from './tema/tema';
import { sinConexionDurante } from './tiempo-real/aviso-conexion/aviso-conexion';
import { EstadoConexion } from './tiempo-real/tiempo-real';

describe('Ejercicio 2: aviso de conexión', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function preparar() {
    const estado = signal<EstadoConexion>('conectado');
    const aviso = TestBed.runInInjectionContext(() => sinConexionDurante(estado, 10_000));
    const pasar = (ms: number) => {
      TestBed.tick(); // propaga el cambio de la señal al observable (toObservable usa un effect)
      vi.advanceTimersByTime(ms);
    };
    return { estado, aviso, pasar };
  }

  it('aparece a los 10 s sin conexión y se va al reconectar', () => {
    const { estado, aviso, pasar } = preparar();
    estado.set('desconectado');
    pasar(9_999);
    expect(aviso()).toBe(false);
    pasar(1);
    expect(aviso()).toBe(true);
    estado.set('conectado');
    pasar(0);
    expect(aviso()).toBe(false);
  });

  it('los reintentos (conectando ↔ desconectado) no reinician la cuenta', () => {
    const { estado, aviso, pasar } = preparar();
    for (const e of ['desconectado', 'conectando', 'desconectado', 'conectando'] as const) {
      estado.set(e);
      pasar(3_000);
    }
    expect(aviso()).toBe(true); // 12 s sin estar conectado, aunque nunca 10 s seguidos "desconectado"
  });

  it('un corte breve no avisa', () => {
    const { estado, aviso, pasar } = preparar();
    estado.set('desconectado');
    pasar(4_000);
    estado.set('conectado');
    pasar(20_000);
    expect(aviso()).toBe(false);
  });
});

describe('Ejercicio 4: tema manual', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.style.colorScheme = '';
  });

  it('sistema → claro → oscuro → sistema, aplicado a <html> y recordado', () => {
    const tema = TestBed.inject(Tema);
    TestBed.tick();
    expect(tema.modo()).toBe('sistema');
    expect(document.documentElement.style.colorScheme).toBe('');
    tema.siguiente();
    TestBed.tick();
    expect(document.documentElement.style.colorScheme).toBe('light');
    tema.siguiente();
    TestBed.tick();
    expect(document.documentElement.style.colorScheme).toBe('dark');
    expect(localStorage.getItem('gastos.tema')).toBe('oscuro');
    tema.siguiente();
    TestBed.tick();
    expect(document.documentElement.style.colorScheme).toBe('');
    expect(localStorage.getItem('gastos.tema')).toBeNull();
  });

  it('arranca con lo guardado e ignora valores raros', () => {
    localStorage.setItem('gastos.tema', 'oscuro');
    expect(TestBed.inject(Tema).modo()).toBe('oscuro');
    TestBed.resetTestingModule();
    localStorage.setItem('gastos.tema', '<script>');
    expect(TestBed.inject(Tema).modo()).toBe('sistema');
  });
});

describe('Ejercicio 1: el archivo compartido se recoge una sola vez', () => {
  it('lo saca de la Cache Storage con su nombre y tipo, y la segunda vez ya no está', async () => {
    const guardado = new Map<string, Response>();
    const cache = {
      match: async (k: string) => guardado.get(k)?.clone(),
      delete: async (k: string) => guardado.delete(k),
    };
    vi.stubGlobal('caches', { open: async () => cache });
    guardado.set(
      '/compartido/ticket',
      // (texto, no Blob: en jsdom un Blob dentro de Response se convierte en "[object Blob]")
      new Response('%PDF-1.7', {
        headers: {
          'Content-Type': 'application/pdf',
          'X-Nombre': encodeURIComponent('factura ñ.pdf'),
        },
      }),
    );
    try {
      const servicio = TestBed.inject(ArchivoCompartido);
      const archivo = await servicio.recoger();
      expect([archivo?.name, archivo?.type, archivo?.size]).toEqual([
        'factura ñ.pdf',
        'application/pdf',
        8,
      ]);
      expect(await servicio.recoger()).toBeNull();
      expect(servicio.tomar()).toBe(archivo); // la pantalla de tickets lo toma…
      expect(servicio.tomar()).toBeNull(); // …una vez
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
