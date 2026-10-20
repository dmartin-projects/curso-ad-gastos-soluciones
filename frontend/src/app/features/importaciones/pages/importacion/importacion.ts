import { DatePipe } from '@angular/common';
import { Component, computed, inject, input, numberAttribute, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { RouterLink } from '@angular/router';
import { injectMutation, injectQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { lastValueFrom } from 'rxjs';

import { Importacion } from '../../../../core/api/tipos';
import { HogarStore } from '../../../../core/hogar/hogar-store';
import { Confirmaciones } from '../../../../shared/components/confirmar/confirmaciones';
import { Importe } from '../../../../shared/components/importe/importe';
import { ESTADOS_IMPORTACION } from '../../interfaces/importaciones.models';
import { ImportacionesApi } from '../../services/importaciones-api';

const PESTANAS = [
  { accion: 'crear', texto: 'Nuevos' },
  { accion: 'conciliar', texto: 'Ya apuntados' },
  { accion: 'duplicada', texto: 'Duplicados' },
];

@Component({
  selector: 'app-importacion',
  imports: [
    DatePipe,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatTabsModule,
    MatCheckboxModule,
    MatPaginatorModule,
    MatProgressBarModule,
    Importe,
  ],
  templateUrl: './importacion.html',
})
export default class ImportacionDetalle {
  protected readonly store = inject(HogarStore);
  private readonly api = inject(ImportacionesApi);
  private readonly queryClient = inject(QueryClient);
  private readonly confirmaciones = inject(Confirmaciones);
  readonly importacionId = input.required({ transform: numberAttribute });
  protected readonly estados = ESTADOS_IMPORTACION;
  protected readonly pestanas = PESTANAS;
  private readonly hogarId = computed(() => this.store.activoId()!);
  private readonly clave = computed(() => [
    'hogar',
    this.hogarId(),
    'importaciones',
    this.importacionId(),
  ]);

  /** Mientras está en marcha, además del socket, se consulta cada 5 s por si el socket no está disponible. */
  protected readonly importacion = injectQuery(() => ({
    queryKey: this.clave(),
    queryFn: () => lastValueFrom(this.api.detalle(this.hogarId(), this.importacionId())),
    refetchInterval: (q: { state: { data?: Importacion } }) =>
      ['pendiente', 'analizando', 'importando'].includes(q.state.data?.estado ?? '')
        ? 5_000
        : false,
  }));
  protected readonly resumen = computed(
    () =>
      this.importacion.data()?.resumen as
        | { desde: string; hasta: string; gastos: string; ingresos: string; a_importar: number }
        | undefined,
  );

  protected readonly avisos = computed(
    () => (this.importacion.data()?.avisos ?? []) as { linea: number; mensaje: string }[],
  );

  protected readonly pestana = signal('crear');
  protected readonly pagina = signal(1);
  protected readonly filas = injectQuery(() => ({
    queryKey: [...this.clave(), 'filas', this.pestana(), this.pagina()],
    queryFn: () =>
      lastValueFrom(
        this.api.filas(this.hogarId(), this.importacionId(), this.pestana(), this.pagina()),
      ),
    enabled: ['vista_previa', 'completada'].includes(this.importacion.data()?.estado ?? ''),
  }));

  protected readonly separar = signal(new Set<number>());

  protected cambiarPestana(i: number) {
    this.pestana.set(PESTANAS[i].accion);
    this.pagina.set(1);
  }

  protected paginar(e: PageEvent) {
    this.pagina.set(e.pageIndex + 1);
  }

  protected alternar(id: number) {
    this.separar.update((s) => {
      const nuevo = new Set(s); // un Set nuevo: la signal solo avisa si cambia la referencia
      if (nuevo.has(id)) nuevo.delete(id);
      else nuevo.add(id);
      return nuevo;
    });
  }

  protected readonly confirmar = injectMutation(() => ({
    mutationFn: () =>
      lastValueFrom(this.api.confirmar(this.hogarId(), this.importacionId(), [...this.separar()])),
    onSuccess: (imp) => this.queryClient.setQueryData(this.clave(), imp),
  }));

  protected async deshacer() {
    const ok = await this.confirmaciones.preguntar(
      'Deshacer importación',
      'Se borrarán los movimientos que creó esta importación. Los gastos conciliados vuelven a como estaban.',
      'Deshacer',
    );
    if (!ok) return;
    const imp = await lastValueFrom(this.api.deshacer(this.hogarId(), this.importacionId()));
    this.queryClient.setQueryData(this.clave(), imp);
    this.queryClient.invalidateQueries({ queryKey: ['hogar', this.hogarId(), 'movimientos'] });
  }
}
