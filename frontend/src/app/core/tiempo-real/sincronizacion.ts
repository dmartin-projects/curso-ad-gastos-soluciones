import { DestroyRef, inject, Service } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router } from '@angular/router';
import { QueryClient } from '@tanstack/angular-query-experimental';

import { Importacion } from '../api/tipos';
import { NotificacionesStore } from '../notificaciones/notificaciones-store';
import { TiempoReal } from './tiempo-real';

/**
 * Traduce los mensajes del socket en cambios de estado de la app:
 * - las notificaciones van a la campana y a un aviso con botón "Ver";
 * - los eventos de hogar INVALIDAN la caché de TanStack Query: el socket solo dice "algo ha cambiado"
 *   y las pantallas abiertas vuelven a pedir sus datos a la API (la única fuente de verdad, módulo 25);
 * - el progreso de una importación se escribe directamente en la caché, sin petición.
 */
@Service()
export class Sincronizacion {
  private readonly tiempoReal = inject(TiempoReal);
  private readonly queryClient = inject(QueryClient);
  private readonly notificaciones = inject(NotificacionesStore);
  private readonly snack = inject(MatSnackBar);
  private readonly router = inject(Router);

  /** Se llama desde el Shell: vive mientras haya sesión y se corta al destruirse. */
  iniciar(destroyRef: DestroyRef) {
    this.tiempoReal.mensajes$.pipe(takeUntilDestroyed(destroyRef)).subscribe((m) => {
      switch (m.tipo) {
        case 'conectado':
          this.notificaciones.fijarNoLeidas(m.no_leidas);
          // al reconectar pudimos perdernos eventos: todo lo visible se revalida
          this.queryClient.invalidateQueries({ queryKey: ['hogar'] });
          break;
        case 'notificacion':
          this.notificaciones.recibir(m.datos);
          this.snack
            .open(m.datos.titulo, m.datos.enlace ? 'Ver' : undefined, { duration: 6000 })
            .onAction()
            .subscribe(() => this.router.navigateByUrl(m.datos.enlace));
          break;
        case 'evento':
          this.alEvento(m.hogar, m.evento, m.datos);
          break;
      }
    });
  }

  private alEvento(hogar: number, evento: string, datos: Record<string, unknown>) {
    const invalidar = (...recursos: string[]) =>
      recursos.forEach((r) =>
        this.queryClient.invalidateQueries({ queryKey: ['hogar', hogar, r] }),
      );
    switch (evento) {
      case 'movimientos_cambiados':
        invalidar('movimientos', 'dashboard', 'presupuestos');
        break;
      case 'tickets_cambiados':
        invalidar('tickets');
        break;
      case 'importaciones_cambiadas':
        invalidar('importaciones');
        break;
      case 'importacion_progreso':
        this.queryClient.setQueryData<Importacion>(
          ['hogar', hogar, 'importaciones', datos['id']],
          (actual) => (actual ? { ...actual, progreso: datos['progreso'] as number } : actual),
        );
        break;
    }
  }
}
