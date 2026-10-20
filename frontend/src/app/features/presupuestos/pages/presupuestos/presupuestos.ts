import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { form, FormField, FormRoot, min, required } from '@angular/forms/signals';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { injectQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { firstValueFrom, lastValueFrom } from 'rxjs';

import { opcionesCategorias } from '../../../../core/hogar/consultas';
import { HogarStore } from '../../../../core/hogar/hogar-store';
import { HogaresApi } from '../../../../core/hogar/hogares-api';
import { erroresDelServidor } from '../../../../core/http/errores-formulario';
import { PresupuestosApi } from '../../services/presupuestos-api';

@Component({
  selector: 'app-presupuestos',
  imports: [
    DatePipe,
    DecimalPipe,
    FormField,
    FormRoot,
    MatCardModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatProgressBarModule,
  ],
  templateUrl: './presupuestos.html',
})
export default class Presupuestos {
  protected readonly store = inject(HogarStore);
  private readonly api = inject(PresupuestosApi);
  private readonly hogaresApi = inject(HogaresApi);
  private readonly queryClient = inject(QueryClient);
  readonly mes = input<string>(); // los enlaces de las notificaciones traen ?mes=2026-10
  protected readonly mesActual = computed(
    () => this.mes() ?? new Date().toLocaleDateString('sv-SE').slice(0, 7),
  );
  private readonly hogarId = computed(() => this.store.activoId()!);

  protected readonly presupuestos = injectQuery(() => ({
    queryKey: ['hogar', this.hogarId(), 'presupuestos', this.mesActual()],
    queryFn: () => lastValueFrom(this.api.delMes(this.hogarId(), this.mesActual())),
  }));
  private readonly categorias = injectQuery(() =>
    opcionesCategorias(this.hogaresApi, this.hogarId()),
  );
  protected readonly categoriasGasto = computed(() =>
    (this.categorias.data() ?? []).filter((c) => !c.es_ingreso && !c.padre),
  );
  protected nombre(id: number) {
    return this.categorias.data()?.find((c) => c.id === id)?.nombre ?? '…';
  }

  protected readonly modelo = signal({
    categoria: null as number | null,
    importe: null as number | null,
  });
  protected readonly f = form(
    this.modelo,
    (r) => {
      required(r.categoria);
      required(r.importe);
      min(r.importe, 1);
    },
    {
      submission: {
        action: async (f) => {
          try {
            const { categoria, importe } = this.modelo();
            await firstValueFrom(
              this.api.crear(this.hogarId(), {
                categoria,
                importe: importe!.toFixed(2),
                mes: `${this.mesActual()}-01`,
              }),
            );
            this.modelo.set({ categoria: null, importe: null });
            await this.queryClient.invalidateQueries({
              queryKey: ['hogar', this.hogarId(), 'presupuestos'],
            });
            return null;
          } catch (e) {
            return erroresDelServidor(e, f);
          }
        },
      },
    },
  );
}
