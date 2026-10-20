import { DatePipe } from '@angular/common';
import { Component, computed, DestroyRef, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { Router, RouterLink } from '@angular/router';
import { injectQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { lastValueFrom } from 'rxjs';

import { Ticket } from '../../../../core/api/tipos';
import { ArchivoCompartido } from '../../../../core/compartir/archivo-compartido';
import { opcionesCuentas } from '../../../../core/hogar/consultas';
import { HogarStore } from '../../../../core/hogar/hogar-store';
import { HogaresApi } from '../../../../core/hogar/hogares-api';
import { ErrorApi } from '../../../../core/http/errores';
import { EstadoTicket } from '../../../../shared/components/estado-ticket/estado-ticket';
import { Importe } from '../../../../shared/components/importe/importe';
import { SubirTicket } from '../../components/subir-ticket/subir-ticket';
import { TicketParaSubir } from '../../interfaces/tickets.models';
import { clavesTickets } from '../../services/consultas';
import { TicketsApi } from '../../services/tickets-api';

@Component({
  selector: 'app-tickets',
  imports: [
    DatePipe,
    RouterLink,
    MatButtonModule,
    MatChipsModule,
    MatIconModule,
    EstadoTicket,
    Importe,
    SubirTicket,
  ],
  templateUrl: './tickets.html',
})
export default class Tickets {
  /** Si se llega desde "compartir" (módulo 81), la foto compartida espera confirmación. */
  protected readonly compartido = inject(ArchivoCompartido).tomar();
  protected readonly store = inject(HogarStore);
  private readonly api = inject(TicketsApi);
  private readonly hogaresApi = inject(HogaresApi);
  private readonly queryClient = inject(QueryClient);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly estado = input<string>(); // ?estado=revisar
  protected readonly hogarId = computed(() => this.store.activoId()!);

  protected readonly cuentas = injectQuery(() => opcionesCuentas(this.hogaresApi, this.hogarId()));
  /** Se actualiza sola: el evento "tickets_cambiados" del socket invalida ['hogar', h, 'tickets'] (Sincronizacion). */
  protected readonly tickets = injectQuery(() => ({
    queryKey: clavesTickets.lista(this.hogarId(), this.estado()),
    queryFn: () => lastValueFrom(this.api.listar(this.hogarId(), this.estado())),
  }));

  protected comercio(t: Ticket) {
    const datos = t.datos_ia as { comercio?: string } | null;
    return (
      datos?.comercio ||
      (t.estado === 'pendiente' || t.estado === 'procesando' ? 'Procesando ticket…' : 'Ticket')
    );
  }

  protected filtrar(estado: string) {
    this.router.navigate([], { queryParams: { estado: estado || null }, replaceUrl: true });
  }

  // ── Subir un ticket: SubirTicket pide, la page sube con su service y le pasa el progreso y el error
  protected readonly progreso = signal<number | null>(null);
  protected readonly errorSubida = signal<string | null>(null);

  protected subir({ cuenta, archivo }: TicketParaSubir) {
    this.errorSubida.set(null);
    this.progreso.set(0);
    this.api
      .subir(this.hogarId(), cuenta, archivo)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (ev) => {
          if (ev.tipo === 'progreso') return this.progreso.set(ev.porcentaje);
          this.progreso.set(null);
          this.queryClient.invalidateQueries({ queryKey: ['hogar', this.hogarId(), 'tickets'] });
        },
        error: (e: unknown) => {
          this.progreso.set(null);
          this.errorSubida.set(
            e instanceof ErrorApi
              ? (Object.values(e.errores)[0]?.[0] ?? e.titulo)
              : 'No se pudo subir.',
          );
        },
      });
  }
}
