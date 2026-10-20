import { HttpClient } from '@angular/common/http';
import { inject, Service } from '@angular/core';

import { FilaImportacion, Importacion, Pagina } from '../../../core/api/tipos';

@Service()
export class ImportacionesApi {
  private readonly http = inject(HttpClient);
  private readonly base = (h: number) => `/api/v1/hogares/${h}/importaciones`;

  listar(hogarId: number) {
    return this.http.get<Pagina<Importacion>>(`${this.base(hogarId)}/`);
  }

  detalle(hogarId: number, id: number) {
    return this.http.get<Importacion>(`${this.base(hogarId)}/${id}/`);
  }

  filas(hogarId: number, id: number, accion: string, pagina: number) {
    return this.http.get<Pagina<FilaImportacion>>(`${this.base(hogarId)}/${id}/filas/`, {
      params: { accion, page: pagina, page_size: 50 },
    });
  }

  subir(hogarId: number, cuenta: number, archivo: File) {
    const datos = new FormData();
    datos.append('archivo', archivo);
    datos.append('cuenta', String(cuenta));
    return this.http.post<Importacion>(`${this.base(hogarId)}/`, datos);
  }

  confirmar(hogarId: number, id: number, separar: number[]) {
    return this.http.post<Importacion>(`${this.base(hogarId)}/${id}/confirmar/`, { separar });
  }

  deshacer(hogarId: number, id: number) {
    return this.http.post<Importacion>(`${this.base(hogarId)}/${id}/deshacer/`, null);
  }
}
