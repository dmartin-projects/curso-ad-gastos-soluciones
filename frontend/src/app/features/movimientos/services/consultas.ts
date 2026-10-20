import { InfiniteData } from '@tanstack/angular-query-experimental';

import { Categoria, Movimiento, PaginaCursor } from '../../../core/api/tipos';

/** Lo que guarda la cache de la lista de movimientos (injectInfiniteQuery): las páginas cargadas. */
export type PaginasMovimientos = InfiniteData<PaginaCursor<Movimiento>, string | null>;

/**
 * Copia de las páginas con la categoría de UN movimiento cambiada (inmutable: TanStack compara referencias).
 * Para la actualización optimista de la lista (módulo 80): la fila cambia antes de que responda la API.
 */
export function conCategoria(
  datos: PaginasMovimientos | undefined,
  id: number,
  categoria: Categoria | null,
): PaginasMovimientos | undefined {
  if (!datos) return datos;
  return {
    ...datos,
    pages: datos.pages.map((pagina) => ({
      ...pagina,
      results: pagina.results.map((m) =>
        m.id === id
          ? {
              ...m,
              categoria: categoria?.id ?? null,
              categoria_nombre: categoria?.nombre ?? null,
              categoria_color: categoria?.color ?? null,
            }
          : m,
      ),
    })),
  };
}
