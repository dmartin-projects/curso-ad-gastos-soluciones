import { CurrencyPipe } from '@angular/common';
import { Component, computed, input } from '@angular/core';

/** Importe con signo y color: rojo los gastos, verde los ingresos. Acepta el texto decimal de la API ("-45.30"). */
@Component({
  selector: 'app-importe',
  imports: [CurrencyPipe],
  templateUrl: './importe.html',
  host: {
    class: 'tabular-nums whitespace-nowrap',
    '[class.text-gasto]': 'numero() < 0',
    '[class.text-ingreso]': 'numero() > 0',
  },
})
export class Importe {
  readonly valor = input.required<string | number>();
  protected readonly numero = computed(() => Number(this.valor()));
}
