import { computed, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { firstValueFrom } from 'rxjs';

import { Hogar, HogarNuevo, Rol } from '../api/tipos';
import { HogaresApi } from './hogares-api';

const CLAVE_ULTIMO = 'gastos.ultimoHogar';

/** localStorage puede no existir o lanzar (modo privado, cookies bloqueadas): nunca debe romper la app. */
const recuerdo = {
  leer: () => {
    try {
      return Number(localStorage.getItem(CLAVE_ULTIMO)) || null;
    } catch {
      return null;
    }
  },
  guardar: (id: number | null) => {
    try {
      if (id === null) localStorage.removeItem(CLAVE_ULTIMO);
      else localStorage.setItem(CLAVE_ULTIMO, String(id));
    } catch {
      /* sin almacenamiento: simplemente no se recuerda */
    }
  },
};

interface EstadoHogar {
  hogares: Hogar[];
  activoId: number | null; // lo fija el guard a partir de la URL: /hogares/:hogarId/…
  cargado: boolean;
}

/**
 * Estado de CLIENTE: qué hogares tengo y en cuál estoy. Los datos de cada hogar (movimientos, tickets…)
 * son estado de SERVIDOR y viven en la caché de TanStack Query, no aquí (módulos 52 y 54).
 */
export const HogarStore = signalStore(
  { providedIn: 'root' },
  withState<EstadoHogar>({ hogares: [], activoId: null, cargado: false }),
  withComputed(({ hogares, activoId }) => {
    const activo = computed(() => hogares().find((h) => h.id === activoId()) ?? null);
    const rol = computed(() => (activo()?.mi_rol as Rol | undefined) ?? null);
    return {
      activo,
      rol,
      puedeEditar: computed(() => rol() === 'admin' || rol() === 'miembro'),
      esAdmin: computed(() => rol() === 'admin'),
    };
  }),
  withMethods((store, api = inject(HogaresApi)) => ({
    async cargar() {
      const hogares = await firstValueFrom(api.listar());
      patchState(store, { hogares, cargado: true });
    },
    seleccionar(activoId: number) {
      patchState(store, { activoId });
      recuerdo.guardar(activoId); // módulo 80: al volver a /hogares se salta a él
    },
    /** El último hogar visitado, si sigue siendo mío (pudieron echarme o borrarlo desde otro dispositivo). */
    ultimo(): number | null {
      const id = recuerdo.leer();
      return id && store.hogares().some((h) => h.id === id) ? id : null;
    },
    async crear(datos: HogarNuevo) {
      const hogar = await firstValueFrom(api.crear(datos));
      patchState(store, (s) => ({ hogares: [...s.hogares, hogar], activoId: hogar.id }));
      return hogar;
    },
    reiniciar() {
      patchState(store, { hogares: [], activoId: null, cargado: false });
      recuerdo.guardar(null); // al cerrar sesión: el siguiente usuario de este navegador no hereda nada
    },
  })),
);
