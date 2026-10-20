import { HttpClient } from '@angular/common/http';
import { inject, Service } from '@angular/core';

import { Dashboard } from '../../../core/api/tipos';

@Service()
export class DashboardApi {
  private readonly http = inject(HttpClient);

  /** Todo el resumen del mes (AAAA-MM) en una petición (módulo 77). */
  resumen(hogarId: number, mes: string) {
    return this.http.get<Dashboard>(`/api/v1/hogares/${hogarId}/dashboard/`, { params: { mes } });
  }
}
