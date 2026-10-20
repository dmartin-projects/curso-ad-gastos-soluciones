import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Service } from '@angular/core';
import { map } from 'rxjs';

import { Movimiento, MovimientoNuevo, PaginaCursor } from '../../../core/api/tipos';
import { rutaRelativa } from '../../../core/api/url';
import { archivoDe } from '../../../core/http/archivos';
import { FiltrosMovimientos } from '../interfaces/movimientos.models';

@Service()
export class MovimientosApi {
  private readonly http = inject(HttpClient);

  private base(hogarId: number) {
    return `/api/v1/hogares/${hogarId}`;
  }

  /** Los filtros de la pantalla → los parámetros de la API (los mismos para listar y para exportar). */
  private params(filtros: FiltrosMovimientos) {
    let params = new HttpParams();
    if (filtros.q) params = params.set('search', filtros.q);
    if (filtros.desde) params = params.set('fecha_after', filtros.desde);
    if (filtros.hasta) params = params.set('fecha_before', filtros.hasta);
    if (filtros.categoria) params = params.set('categoria', filtros.categoria);
    if (filtros.tipo) params = params.set('tipo', filtros.tipo);
    if (filtros.pendientes) params = params.set('revisado', false);
    return params;
  }

  /** Primera página (con filtros) o la siguiente (la URL `next` ya lleva el cursor y los filtros). */
  pagina(hogarId: number, filtros: FiltrosMovimientos, siguiente: string | null) {
    if (siguiente) return this.http.get<PaginaCursor<Movimiento>>(rutaRelativa(siguiente));
    return this.http.get<PaginaCursor<Movimiento>>(`${this.base(hogarId)}/movimientos/`, {
      params: this.params(filtros),
    });
  }

  cambiarCategoria(hogarId: number, id: number, categoria: number | null) {
    return this.http.patch<Movimiento>(`${this.base(hogarId)}/movimientos/${id}/`, { categoria });
  }

  crear(hogarId: number, datos: MovimientoNuevo) {
    return this.http.post<Movimiento>(`${this.base(hogarId)}/movimientos/`, datos);
  }

  actualizar(hogarId: number, id: number, datos: MovimientoNuevo) {
    return this.http.put<Movimiento>(`${this.base(hogarId)}/movimientos/${id}/`, datos);
  }

  borrar(hogarId: number, id: number) {
    return this.http.delete<void>(`${this.base(hogarId)}/movimientos/${id}/`);
  }

  /** Lo que se ve en pantalla (con sus filtros), en CSV, con el nombre que manda Content-Disposition. */
  exportarCsv(hogarId: number, filtros: FiltrosMovimientos) {
    return this.http
      .get(`${this.base(hogarId)}/movimientos/exportar/`, {
        params: this.params(filtros),
        responseType: 'blob',
        observe: 'response',
      })
      .pipe(map((r) => archivoDe(r, 'movimientos.csv')));
  }
}
