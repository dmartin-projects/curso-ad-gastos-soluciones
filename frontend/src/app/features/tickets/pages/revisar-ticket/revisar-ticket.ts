import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, effect, inject, input, numberAttribute, signal } from '@angular/core';
import { form, FormField, FormRoot, min, required } from '@angular/forms/signals';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import { injectMutation, injectQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { firstValueFrom, lastValueFrom } from 'rxjs';

import { Ticket } from '../../../../core/api/tipos';
import { opcionesCategorias } from '../../../../core/hogar/consultas';
import { HogarStore } from '../../../../core/hogar/hogar-store';
import { HogaresApi } from '../../../../core/hogar/hogares-api';
import { Avisos } from '../../../../core/http/avisos';
import { erroresDelServidor } from '../../../../core/http/errores-formulario';
import { EstadoTicket } from '../../../../shared/components/estado-ticket/estado-ticket';
import { Importe } from '../../../../shared/components/importe/importe';
import { SelectorCategoria } from '../../../../shared/components/selector-categoria/selector-categoria';
import { clavesTickets } from '../../services/consultas';
import { TicketsApi } from '../../services/tickets-api';

interface DatosIa {
  comercio?: string;
  fecha?: string | null;
  total?: string | null;
  lineas?: { descripcion: string; cantidad: string; precio_unitario: string }[];
}

@Component({
  selector: 'app-revisar-ticket',
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    FormField,
    FormRoot,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    EstadoTicket,
    Importe,
    SelectorCategoria,
  ],
  templateUrl: './revisar-ticket.html',
})
export default class RevisarTicket {
  protected readonly store = inject(HogarStore);
  private readonly api = inject(TicketsApi);
  private readonly hogaresApi = inject(HogaresApi);
  private readonly queryClient = inject(QueryClient);
  private readonly avisos = inject(Avisos);
  readonly ticketId = input.required({ transform: numberAttribute }); // :ticketId de la ruta
  private readonly hogarId = computed(() => this.store.activoId()!);

  protected readonly ticket = injectQuery(() => ({
    queryKey: clavesTickets.detalle(this.hogarId(), this.ticketId()),
    queryFn: () => lastValueFrom(this.api.detalle(this.hogarId(), this.ticketId())),
  }));
  /** URL firmada y temporal (S3/R2): se pide aparte y se considera fresca 4 minutos (caduca en 5). */
  protected readonly imagen = injectQuery(() => ({
    queryKey: ['hogar', this.hogarId(), 'tickets', this.ticketId(), 'archivo'],
    queryFn: () => lastValueFrom(this.api.urlArchivo(this.hogarId(), this.ticketId())),
    staleTime: 4 * 60_000,
  }));
  private readonly categorias = injectQuery(() =>
    opcionesCategorias(this.hogaresApi, this.hogarId()),
  );
  protected readonly gastos = computed(() =>
    (this.categorias.data() ?? []).filter((c) => !c.es_ingreso),
  );

  private readonly datosIa = computed(() => (this.ticket.data()?.datos_ia ?? {}) as DatosIa);
  protected readonly lineas = computed(() => this.datosIa().lineas ?? []);

  protected readonly modelo = signal({
    concepto: '',
    fecha: '',
    total: null as number | null,
    categoria: null as number | null,
  });

  constructor() {
    // Rellena el formulario con lo que propuso la IA (o con el gasto ya creado) cuando llega el ticket
    effect(() => {
      const t = this.ticket.data();
      if (!t) return;
      const ia = this.datosIa();
      this.modelo.set({
        concepto: t.movimiento?.concepto ?? ia.comercio ?? '',
        fecha: t.movimiento?.fecha ?? ia.fecha ?? '',
        total: t.movimiento
          ? Math.abs(Number(t.movimiento.importe))
          : ia.total
            ? Number(ia.total)
            : null,
        categoria: t.movimiento?.categoria ?? null,
      });
    });
  }

  protected readonly f = form(
    this.modelo,
    (r) => {
      required(r.concepto);
      required(r.fecha);
      required(r.total, { message: 'Indica el total' });
      min(r.total, 0.01);
    },
    {
      submission: {
        action: async (f) => {
          const m = this.modelo();
          try {
            await firstValueFrom(
              this.api.confirmar(this.hogarId(), this.ticketId(), {
                concepto: m.concepto,
                fecha: m.fecha,
                total: m.total!.toFixed(2),
                categoria: m.categoria,
              }),
            );
            this.avisos.exito('Gasto confirmado');
            await this.queryClient.invalidateQueries({
              queryKey: ['hogar', this.hogarId(), 'tickets'],
            });
            return null;
          } catch (e) {
            return erroresDelServidor(e, f);
          }
        },
      },
    },
  );

  protected readonly reprocesar = injectMutation(() => ({
    mutationFn: () => lastValueFrom(this.api.reprocesar(this.hogarId(), this.ticketId())),
    onSuccess: (t: Ticket) => {
      this.queryClient.setQueryData(clavesTickets.detalle(this.hogarId(), t.id), t);
      this.avisos.exito('Procesando de nuevo; te avisaremos al terminar');
    },
  }));
}
