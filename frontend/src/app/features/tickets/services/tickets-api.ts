import { HttpClient, HttpEventType } from '@angular/common/http';
import { inject, Service } from '@angular/core';
import { filter, map, Observable } from 'rxjs';

import { ConfirmarTicket, Pagina, Ticket } from '../../../core/api/tipos';
import { EventoSubida } from '../interfaces/tickets.models';

@Service()
export class TicketsApi {
  private readonly http = inject(HttpClient);
  private readonly base = (h: number) => `/api/v1/hogares/${h}/tickets`;

  listar(hogarId: number, estado?: string) {
    return this.http.get<Pagina<Ticket>>(`${this.base(hogarId)}/`, {
      params: estado ? { estado } : {},
    });
  }

  detalle(hogarId: number, id: number) {
    return this.http.get<Ticket>(`${this.base(hogarId)}/${id}/`);
  }

  /**
   * Multipart con eventos de progreso (necesita withXhr en provideHttpClient, módulo 51). Los HttpEvent se quedan
   * aquí: quien sube recibe el porcentaje y, al final, el ticket.
   */
  subir(hogarId: number, cuenta: number, archivo: File): Observable<EventoSubida> {
    const datos = new FormData();
    datos.append('archivo', archivo);
    datos.append('cuenta', String(cuenta));
    // sin Content-Type a mano: con FormData lo pone el navegador, con su "boundary"
    return this.http
      .post<Ticket>(`${this.base(hogarId)}/`, datos, { reportProgress: true, observe: 'events' })
      .pipe(
        map((ev): EventoSubida | null => {
          if (ev.type === HttpEventType.UploadProgress && ev.total)
            return { tipo: 'progreso', porcentaje: Math.round((100 * ev.loaded) / ev.total) };
          if (ev.type === HttpEventType.Response) return { tipo: 'subido', ticket: ev.body! };
          return null;
        }),
        filter((ev): ev is EventoSubida => ev !== null),
      );
  }

  urlArchivo(hogarId: number, id: number) {
    return this.http.get<{ url: string }>(`${this.base(hogarId)}/${id}/archivo/`);
  }

  confirmar(hogarId: number, id: number, datos: ConfirmarTicket) {
    return this.http.post<Ticket>(`${this.base(hogarId)}/${id}/confirmar/`, datos);
  }

  reprocesar(hogarId: number, id: number, repetirOcr = false) {
    return this.http.post<Ticket>(`${this.base(hogarId)}/${id}/reprocesar/`, {
      repetir_ocr: repetirOcr,
    });
  }

  borrar(hogarId: number, id: number) {
    return this.http.delete<void>(`${this.base(hogarId)}/${id}/`);
  }
}
