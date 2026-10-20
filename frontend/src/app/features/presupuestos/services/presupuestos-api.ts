import { HttpClient } from '@angular/common/http';
import { inject, Service } from '@angular/core';

import { Presupuesto } from '../../../core/api/tipos';

@Service()
export class PresupuestosApi {
  private readonly http = inject(HttpClient);
  private readonly base = (hogarId: number) => `/api/v1/hogares/${hogarId}/presupuestos/`;

  /** Los del mes (AAAA-MM), con lo gastado en cada uno. */
  delMes(hogarId: number, mes: string) {
    return this.http.get<Presupuesto[]>(this.base(hogarId), { params: { mes } });
  }

  crear(hogarId: number, datos: { categoria: number | null; importe: string; mes: string }) {
    return this.http.post<Presupuesto>(this.base(hogarId), datos);
  }
}
