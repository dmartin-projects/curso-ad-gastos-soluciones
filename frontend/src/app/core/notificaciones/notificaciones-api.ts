import { HttpClient } from '@angular/common/http';
import { inject, Service } from '@angular/core';

import { Notificacion, PaginaCursor } from '../api/tipos';
import { rutaRelativa } from '../api/url';

@Service()
export class NotificacionesApi {
  private readonly http = inject(HttpClient);

  pagina(siguiente: string | null, soloNoLeidas = false) {
    if (siguiente) return this.http.get<PaginaCursor<Notificacion>>(rutaRelativa(siguiente));
    return this.http.get<PaginaCursor<Notificacion>>('/api/v1/notificaciones/', {
      params: soloNoLeidas ? { leida: false } : {},
    });
  }

  noLeidas() {
    return this.http.get<{ no_leidas: number }>('/api/v1/notificaciones/no-leidas/');
  }

  leer(id: number) {
    return this.http.post<void>(`/api/v1/notificaciones/${id}/leer/`, null);
  }

  leerTodas() {
    return this.http.post<{ actualizadas: number }>('/api/v1/notificaciones/leer-todas/', {});
  }
}
