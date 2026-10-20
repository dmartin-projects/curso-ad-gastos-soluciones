import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, inject, input } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Router, RouterLink } from '@angular/router';
import { injectQuery, keepPreviousData } from '@tanstack/angular-query-experimental';
import type { ChartData } from 'chart.js';
import { lastValueFrom } from 'rxjs';

import { HogarStore } from '../../../../core/hogar/hogar-store';
import { Grafico } from '../../../../shared/components/grafico/grafico';
import { Importe } from '../../../../shared/components/importe/importe';
import { DashboardApi } from '../../services/dashboard-api';

const mesDe = (fecha: Date) => fecha.toLocaleDateString('sv-SE').slice(0, 7); // AAAA-MM

@Component({
  selector: 'app-dashboard',
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    Grafico,
    Importe,
  ],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css',
})
export default class Dashboard {
  private readonly api = inject(DashboardApi);
  private readonly router = inject(Router);
  private readonly store = inject(HogarStore);
  readonly mes = input<string>(); // ?mes=2026-10
  protected readonly mesActual = computed(() => this.mes() ?? mesDe(new Date()));

  /**
   * Una petición con todo (módulo 77). La caché del navegador + el ETag de la API hacen que volver a esta
   * pantalla cueste un 304 sin cuerpo; keepPreviousData evita el "parpadeo" al cambiar de mes.
   */
  protected readonly resumen = injectQuery(() => ({
    queryKey: ['hogar', this.store.activoId(), 'dashboard', this.mesActual()],
    queryFn: () => lastValueFrom(this.api.resumen(this.store.activoId()!, this.mesActual())),
    placeholderData: keepPreviousData,
  }));

  protected readonly porCategoria = computed<ChartData<'doughnut'>>(() => {
    const filas = this.resumen.data()?.por_categoria ?? [];
    return {
      labels: filas.map((f) => f.nombre),
      datasets: [
        { data: filas.map((f) => Number(f.total)), backgroundColor: filas.map((f) => f.color) },
      ],
    };
  });

  /** Dos líneas, día 1 con día 1 (módulo 77, ejercicio 1). `null` corta la línea (días que no han llegado). */
  protected readonly acumulado = computed<ChartData<'line'>>(() => {
    const dias = this.resumen.data()?.comparativa ?? [];
    const numero = (v: string | null) => (v === null ? null : Number(v));
    return {
      labels: dias.map((d) => d.dia),
      datasets: [
        { label: 'Este mes', data: dias.map((d) => numero(d.este_mes)), fill: true, tension: 0.2 },
        {
          label: 'Mes anterior',
          data: dias.map((d) => numero(d.mes_anterior)),
          borderDash: [6, 4],
          tension: 0.2,
        },
      ],
    };
  });

  protected readonly evolucion = computed<ChartData<'bar'>>(() => {
    const meses = this.resumen.data()?.evolucion ?? [];
    return {
      labels: meses.map((m) => m.mes),
      datasets: [
        { label: 'Gastos', data: meses.map((m) => Number(m.gastos)), backgroundColor: '#e57373' },
        {
          label: 'Ingresos',
          data: meses.map((m) => Number(m.ingresos)),
          backgroundColor: '#81c784',
        },
      ],
    };
  });

  protected moverMes(delta: number) {
    const [a, m] = this.mesActual().split('-').map(Number);
    this.router.navigate([], {
      queryParams: { mes: mesDe(new Date(a, m - 1 + delta, 1)) },
      replaceUrl: true,
    });
  }
}
