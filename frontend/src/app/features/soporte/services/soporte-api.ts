import { HttpClient } from '@angular/common/http';
import { inject, Service } from '@angular/core';

import {
  HogarDetalleSoporte,
  HogarSoporte,
  ImportacionSoporte,
  MovimientoSoporte,
  Pagina,
  RegistroAuditoria,
  ResultadoLote,
  ResumenSoporte,
  TareaProgramada,
  TicketSoporte,
  UsuarioSoporte,
} from '../../../core/api/tipos';

const B = '/api/v1/backoffice';
type Params = Record<string, string | number | boolean>;

/** El backoffice (módulo 79). Toda la seguridad está en la API: esto solo la consume. */
@Service()
export class SoporteApi {
  private readonly http = inject(HttpClient);

  resumen() {
    return this.http.get<ResumenSoporte>(`${B}/resumen/`);
  }
  tickets(params: Params) {
    return this.http.get<Pagina<TicketSoporte>>(`${B}/tickets/`, { params });
  }
  reprocesar(ids: number[]) {
    return this.http.post<ResultadoLote>(`${B}/tickets/reprocesar/`, { ids });
  }
  importaciones(params: Params) {
    return this.http.get<Pagina<ImportacionSoporte>>(`${B}/importaciones/`, { params });
  }
  deshacer(id: number) {
    return this.http.post<ImportacionSoporte>(`${B}/importaciones/${id}/deshacer/`, null);
  }
  hogares(params: Params) {
    return this.http.get<Pagina<HogarSoporte>>(`${B}/hogares/`, { params });
  }
  hogar(id: number) {
    return this.http.get<HogarDetalleSoporte>(`${B}/hogares/${id}/`);
  }
  movimientos(params: Params) {
    return this.http.get<Pagina<MovimientoSoporte>>(`${B}/movimientos/`, { params });
  }
  recategorizar(ids: number[], categoria: number) {
    return this.http.post<ResultadoLote>(`${B}/movimientos/recategorizar/`, { ids, categoria });
  }
  usuarios(params: Params) {
    return this.http.get<Pagina<UsuarioSoporte>>(`${B}/usuarios/`, { params });
  }
  activar(id: number, activo: boolean) {
    return this.http.patch<UsuarioSoporte>(`${B}/usuarios/${id}/`, { is_active: activo });
  }
  auditoria(params: Params) {
    return this.http.get<Pagina<RegistroAuditoria>>(`${B}/auditoria/`, { params });
  }
  tareas() {
    return this.http.get<TareaProgramada[]>(`${B}/tareas/`);
  }
  pausar(id: number, activa: boolean) {
    return this.http.patch<TareaProgramada>(`${B}/tareas/${id}/`, { enabled: activa });
  }
}
