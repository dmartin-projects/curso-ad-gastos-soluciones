import { DOCUMENT, effect, inject, Service, signal } from '@angular/core';

export type ModoTema = 'sistema' | 'claro' | 'oscuro';
const CLAVE = 'gastos.tema';
const ORDEN: ModoTema[] = ['sistema', 'claro', 'oscuro'];
const COLOR_SCHEME: Record<ModoTema, string> = { sistema: '', claro: 'light', oscuro: 'dark' };

function leer(): ModoTema {
  try {
    const v = localStorage.getItem(CLAVE) as ModoTema | null;
    return v && ORDEN.includes(v) ? v : 'sistema';
  } catch {
    return 'sistema';
  }
}

/**
 * Modo claro/oscuro manual (módulo 81). El tema de Material usa light-dark(): basta con fijar
 * `color-scheme` en <html>. "sistema" quita el estilo en línea y manda el `light dark` de styles.scss.
 */
@Service()
export class Tema {
  private readonly html = inject(DOCUMENT).documentElement;
  readonly modo = signal<ModoTema>(leer());

  constructor() {
    effect(() => {
      const modo = this.modo();
      this.html.style.colorScheme = COLOR_SCHEME[modo];
      try {
        if (modo === 'sistema') localStorage.removeItem(CLAVE);
        else localStorage.setItem(CLAVE, modo);
      } catch {
        /* sin almacenamiento: dura lo que la pestaña */
      }
    });
  }

  siguiente() {
    this.modo.update((m) => ORDEN[(ORDEN.indexOf(m) + 1) % ORDEN.length]);
  }
}
