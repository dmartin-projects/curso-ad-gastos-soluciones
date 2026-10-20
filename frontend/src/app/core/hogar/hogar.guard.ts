import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { HogarStore } from './hogar-store';

/** La URL manda: /hogares/7/… fija el hogar activo (y un hogar ajeno o inexistente devuelve a la lista). */
export const hogarGuard: CanActivateFn = async (ruta) => {
  const store = inject(HogarStore);
  const router = inject(Router);
  const id = Number(ruta.paramMap.get('hogarId'));
  if (!store.cargado()) await store.cargar();
  if (!store.hogares().some((h) => h.id === id)) return router.createUrlTree(['/hogares']);
  store.seleccionar(id);
  return true;
};
