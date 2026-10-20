import { HttpClient } from '@angular/common/http';
import { inject, Service } from '@angular/core';
import { map } from 'rxjs';

import { Informe } from '../../../core/api/tipos';
import { archivoDe } from '../../../core/http/archivos';

@Service()
export class InformesApi {
  private readonly http = inject(HttpClient);
  private readonly base = (hogarId: number) => `/api/v1/hogares/${hogarId}/informes/`;

  listar(hogarId: number) {
    return this.http.get<Informe[]>(this.base(hogarId));
  }

  generar(hogarId: number, datos: { mes: string; enviar: boolean; tipo: 'mensual' | 'anual' }) {
    return this.http.post(this.base(hogarId), datos);
  }

  /** Por la API (con el JWT y sus permisos), no con un enlace <a href>, que no puede llevar la cabecera Authorization. */
  pdf(hogarId: number, periodo: string) {
    return this.http
      .get(`${this.base(hogarId)}${periodo}/pdf/`, { responseType: 'blob', observe: 'response' })
      .pipe(map((r) => archivoDe(r, `gastos-${periodo}.pdf`)));
  }

  /** El enlace del pie del email (módulo 78): pública, sin sesión; el token firmado dice quién se da de baja. */
  baja(token: string) {
    return this.http.post(`/api/v1/informes/baja/${token}/`, null);
  }
}
