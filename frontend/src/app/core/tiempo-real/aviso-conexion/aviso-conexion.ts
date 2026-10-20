import { Component, inject, Signal } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { MatIconModule } from '@angular/material/icon';
import { distinctUntilChanged, map, of, startWith, switchMap, timer } from 'rxjs';

import { EstadoConexion, TiempoReal } from '../tiempo-real';

/**
 * true cuando lleva más de `ms` SIN estar conectado. No vale "más de 10 s en desconectado": mientras
 * reintenta, el estado alterna desconectado → conectando → desconectado… y el reloj nunca llegaría a 10 s.
 * Debe llamarse en un contexto de inyección (toObservable/toSignal).
 */
export function sinConexionDurante(estado: Signal<EstadoConexion>, ms = 10_000): Signal<boolean> {
  return toSignal(
    toObservable(estado).pipe(
      map((e) => e === 'conectado'),
      distinctUntilChanged(), // conectando ↔ desconectado no reinicia la cuenta
      switchMap((conectado) =>
        conectado
          ? of(false)
          : timer(ms).pipe(
              map(() => true),
              startWith(false),
            ),
      ),
    ),
    { initialValue: false },
  );
}

/** Aviso discreto: abajo, sin tapar nada, y anunciado a los lectores de pantalla (role="status"). */
@Component({
  selector: 'app-aviso-conexion',
  imports: [MatIconModule],
  templateUrl: './aviso-conexion.html',
})
export class AvisoConexion {
  protected readonly sinConexion = sinConexionDurante(inject(TiempoReal).estado);
}
