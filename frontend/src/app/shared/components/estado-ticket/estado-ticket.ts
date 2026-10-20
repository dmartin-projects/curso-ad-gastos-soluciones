import { Component, computed, input } from '@angular/core';

const ESTADOS: Record<string, { texto: string; clase: string }> = {
  pendiente: { texto: 'En cola', clase: 'bg-neutral-200 text-neutral-800' },
  procesando: { texto: 'Leyendo…', clase: 'bg-sky-100 text-sky-900 animate-pulse' },
  revisar: { texto: 'Revisar', clase: 'bg-amber-100 text-amber-900' },
  procesado: { texto: 'Listo', clase: 'bg-emerald-100 text-emerald-900' },
  error: { texto: 'Error', clase: 'bg-red-100 text-red-900' },
};

@Component({
  selector: 'app-estado-ticket',
  templateUrl: './estado-ticket.html',
})
export class EstadoTicket {
  readonly estado = input.required<string>();
  protected readonly info = computed(
    () => ESTADOS[this.estado()] ?? { texto: this.estado(), clase: '' },
  );
}
