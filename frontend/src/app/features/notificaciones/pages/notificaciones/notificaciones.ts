import { DatePipe } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { Router } from '@angular/router';
import { injectInfiniteQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { lastValueFrom } from 'rxjs';

import { Notificacion } from '../../../../core/api/tipos';
import { NotificacionesApi } from '../../../../core/notificaciones/notificaciones-api';
import { NotificacionesStore } from '../../../../core/notificaciones/notificaciones-store';

@Component({
  selector: 'app-notificaciones',
  imports: [DatePipe, MatButtonModule, MatIconModule],
  templateUrl: './notificaciones.html',
})
export default class Notificaciones {
  private readonly api = inject(NotificacionesApi);
  private readonly store = inject(NotificacionesStore);
  private readonly router = inject(Router);
  private readonly queryClient = inject(QueryClient);

  protected readonly consulta = injectInfiniteQuery(() => ({
    queryKey: ['notificaciones'],
    queryFn: ({ pageParam }) => lastValueFrom(this.api.pagina(pageParam)),
    initialPageParam: null as string | null,
    getNextPageParam: (p) => p.next,
  }));
  protected readonly lista = computed(
    () => this.consulta.data()?.pages.flatMap((p) => p.results) ?? [],
  );

  protected async abrir(n: Notificacion) {
    if (!n.leida) await this.store.leer(n.id);
    await this.queryClient.invalidateQueries({ queryKey: ['notificaciones'] });
    if (n.enlace) this.router.navigateByUrl(n.enlace);
  }

  protected async leerTodas() {
    await this.store.leerTodas();
    await this.queryClient.invalidateQueries({ queryKey: ['notificaciones'] });
  }
}
