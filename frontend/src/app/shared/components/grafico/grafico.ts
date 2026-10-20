import {
  afterNextRender,
  Component,
  DestroyRef,
  effect,
  ElementRef,
  inject,
  input,
  LOCALE_ID,
  viewChild,
} from '@angular/core';
import type { Chart, ChartConfiguration, ChartData, ChartOptions, ChartType } from 'chart.js';

/** Envoltorio mínimo de Chart.js (módulo 61). Chart.js se descarga solo cuando se pinta el primer gráfico. */
@Component({
  selector: 'app-grafico',
  templateUrl: './grafico.html',
  host: { class: 'block relative' },
})
export class Grafico {
  readonly tipo = input<ChartType>('bar');
  readonly datos = input.required<ChartData<ChartType>>();
  readonly opciones = input<ChartOptions<ChartType>>({});
  readonly etiqueta = input('Gráfico');

  private readonly lienzo = viewChild.required<ElementRef<HTMLCanvasElement>>('lienzo');
  private grafico?: Chart;
  private readonly locale = inject(LOCALE_ID);

  constructor() {
    afterNextRender(async () => {
      const { Chart, registerables } = await import('chart.js');
      Chart.register(...registerables);
      Chart.defaults.locale = this.locale; // 2.500 y no 2,500 en los ejes
      const config: ChartConfiguration = {
        type: this.tipo(),
        data: this.datos(),
        options: { responsive: true, maintainAspectRatio: false, ...this.opciones() },
      };
      this.grafico = new Chart(this.lienzo().nativeElement, config);
    });
    effect(() => {
      const datos = this.datos();
      if (this.grafico) {
        this.grafico.data = datos;
        this.grafico.update();
      }
    });
    inject(DestroyRef).onDestroy(() => this.grafico?.destroy());
  }
}
