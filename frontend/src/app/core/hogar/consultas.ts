import { queryOptions } from '@tanstack/angular-query-experimental';
import { lastValueFrom } from 'rxjs';

import { HogaresApi } from './hogares-api';

/**
 * Claves de caché de TanStack Query: todo lo de un hogar cuelga de ['hogar', id, …].
 * Así se invalida con precisión: ['hogar', 3, 'movimientos'] (una lista) o ['hogar', 3] (todo el hogar).
 */
export const claves = {
  hogar: (hogarId: number) => ['hogar', hogarId] as const,
  movimientos: (hogarId: number) => ['hogar', hogarId, 'movimientos'] as const,
  categorias: (hogarId: number) => ['hogar', hogarId, 'categorias'] as const,
  cuentas: (hogarId: number) => ['hogar', hogarId, 'cuentas'] as const,
};

/**
 * Catálogos del hogar (movimientos, tickets, importaciones, presupuestos y categorías los usan): cambian poco,
 * así que se consideran frescos 5 minutos.
 */
export function opcionesCategorias(api: HogaresApi, hogarId: number) {
  return queryOptions({
    queryKey: claves.categorias(hogarId),
    queryFn: () => lastValueFrom(api.categorias(hogarId)),
    staleTime: 5 * 60_000,
  });
}

export function opcionesCuentas(api: HogaresApi, hogarId: number) {
  return queryOptions({
    queryKey: claves.cuentas(hogarId),
    queryFn: () => lastValueFrom(api.cuentas(hogarId)),
    staleTime: 5 * 60_000,
  });
}
