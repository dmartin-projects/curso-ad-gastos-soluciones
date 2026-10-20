import { HttpClient } from '@angular/common/http';
import { inject, Service } from '@angular/core';
import { map } from 'rxjs';

import { Categoria, Cuenta, Hogar, HogarNuevo, Pagina } from '../api/tipos';

/** Los hogares de la persona y los catálogos de cada uno (cuentas y categorías), que usan varias features. */
@Service()
export class HogaresApi {
  private readonly http = inject(HttpClient);

  listar() {
    return this.http
      .get<Pagina<Hogar>>('/api/v1/hogares/', { params: { page_size: 100 } })
      .pipe(map((p) => p.results));
  }

  crear(datos: HogarNuevo) {
    return this.http.post<Hogar>('/api/v1/hogares/', datos);
  }

  cuentas(hogarId: number) {
    return this.http.get<Cuenta[]>(`/api/v1/hogares/${hogarId}/cuentas/`);
  }

  categorias(hogarId: number) {
    return this.http.get<Categoria[]>(`/api/v1/hogares/${hogarId}/categorias/`);
  }
}
