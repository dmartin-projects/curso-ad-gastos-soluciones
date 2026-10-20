import { inject } from '@angular/core';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { firstValueFrom } from 'rxjs';

import { MensajeWs } from '../tiempo-real/tiempo-real';
import { NotificacionesApi } from './notificaciones-api';

type Recibida = Extract<MensajeWs, { tipo: 'notificacion' }>['datos'];

/** La campana: contador de no leídas y las últimas recibidas por el socket. */
export const NotificacionesStore = signalStore(
  { providedIn: 'root' },
  withState({ noLeidas: 0, recientes: [] as Recibida[] }),
  withMethods((store, api = inject(NotificacionesApi)) => ({
    fijarNoLeidas(noLeidas: number) {
      patchState(store, { noLeidas });
    },
    recibir(n: Recibida) {
      patchState(store, (s) => ({
        noLeidas: s.noLeidas + 1,
        recientes: [n, ...s.recientes].slice(0, 10),
      }));
    },
    async leer(id: number) {
      patchState(store, (s) => ({
        noLeidas: Math.max(0, s.noLeidas - 1),
        recientes: s.recientes.filter((n) => n.id !== id),
      }));
      await firstValueFrom(api.leer(id));
    },
    async leerTodas() {
      patchState(store, { noLeidas: 0, recientes: [] });
      await firstValueFrom(api.leerTodas());
    },
  })),
);
