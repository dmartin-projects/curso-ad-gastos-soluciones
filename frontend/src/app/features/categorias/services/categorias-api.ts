import { HttpClient } from '@angular/common/http';
import { inject, Service } from '@angular/core';

import { Categoria, CategoriaNueva } from '../../../core/api/tipos';

/** Crear y ordenar categorías. La lista (un catálogo que usan varias features) la da HogaresApi. */
@Service()
export class CategoriasApi {
  private readonly http = inject(HttpClient);

  crear(hogarId: number, datos: CategoriaNueva) {
    return this.http.post<Categoria>(`/api/v1/hogares/${hogarId}/categorias/`, datos);
  }

  reordenar(hogarId: number, ids: number[]) {
    return this.http.post<void>(`/api/v1/hogares/${hogarId}/categorias/reordenar/`, { ids });
  }
}
