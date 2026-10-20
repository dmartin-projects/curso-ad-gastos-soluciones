import { HttpClient } from '@angular/common/http';
import { inject, Service, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import {
  defer,
  EMPTY,
  finalize,
  ignoreElements,
  interval,
  map,
  merge,
  Observable,
  repeat,
  retry,
  share,
  switchMap,
  tap,
  timer,
} from 'rxjs';
import { webSocket } from 'rxjs/webSocket';

import { Notificacion } from '../api/tipos';
import { AuthStore } from '../auth/auth-store';

/** Mensajes que envía el consumer de Channels (módulo 76). */
export type MensajeWs =
  | { tipo: 'conectado'; no_leidas: number }
  | { tipo: 'pong' }
  | {
      tipo: 'notificacion';
      datos: Pick<
        Notificacion,
        'id' | 'tipo' | 'titulo' | 'mensaje' | 'enlace' | 'hogar' | 'creado'
      >;
    }
  | { tipo: 'evento'; evento: string; hogar: number; datos: Record<string, unknown> };

export type EstadoConexion = 'desconectado' | 'conectando' | 'conectado';

const urlBase = () => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;

/**
 * Una única conexión WebSocket para toda la app, solo mientras hay sesión:
 * - se autentica con un ticket de un solo uso (el JWT nunca va en la URL, módulo 76);
 * - si el servidor la cierra limpiamente (4000: cambiaron mis hogares; 4401: ticket caducado) reconecta con otro ticket;
 * - si se cae, reintenta con espera creciente (1 s, 2 s, 4 s… hasta 30 s);
 * - manda un "ping" cada 25 s para que ningún proxy la cierre por inactividad.
 */
@Service()
export class TiempoReal {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthStore);

  private readonly _estado = signal<EstadoConexion>('desconectado');
  readonly estado = this._estado.asReadonly();

  private readonly conexion$: Observable<MensajeWs> = defer(() => {
    this._estado.set('conectando');
    return this.http.post<{ ticket: string }>('/api/v1/notificaciones/ws-ticket/', null);
  }).pipe(
    switchMap(({ ticket }) => {
      const socket = webSocket<MensajeWs | { accion: 'ping' }>({
        url: `${urlBase()}/notificaciones/?ticket=${ticket}`,
        openObserver: { next: () => this._estado.set('conectado') },
        closeObserver: { next: () => this._estado.set('desconectado') },
      });
      const latido = interval(25_000).pipe(
        tap(() => socket.next({ accion: 'ping' })),
        ignoreElements(),
      );
      return merge(socket, latido) as Observable<MensajeWs>;
    }),
    repeat({ delay: () => timer(1_000) }),
    retry({
      delay: (_e, intento) => timer(Math.min(30_000, 1_000 * 2 ** (intento - 1))),
      resetOnSuccess: true,
    }),
    finalize(() => this._estado.set('desconectado')),
  );

  /** Compartido (`share`): da igual cuántos componentes se suscriban, hay un solo socket. */
  readonly mensajes$: Observable<MensajeWs> = toObservable(this.auth.autenticado).pipe(
    switchMap((conSesion) => (conSesion ? this.conexion$ : EMPTY)),
    share(),
  );

  /** Atajo: solo los eventos de un tipo. */
  eventos(nombre: string) {
    return this.mensajes$.pipe(
      map((m) => (m.tipo === 'evento' && m.evento === nombre ? m : null)),
      switchMap((m) => (m ? [m] : [])),
    );
  }
}
