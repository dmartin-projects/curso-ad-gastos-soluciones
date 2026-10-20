import { DatePipe } from '@angular/common';
import { Component, inject, input, numberAttribute, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { injectMutation, injectQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { lastValueFrom } from 'rxjs';

import { Avisos } from '../../../../core/http/avisos';
import { Importe } from '../../../../shared/components/importe/importe';
import { SoporteApi } from '../../services/soporte-api';

@Component({
  selector: 'app-hogar-soporte',
  imports: [DatePipe, RouterLink, MatButtonModule, MatIconModule, MatCheckboxModule, Importe],
  templateUrl: './hogar-soporte.html',
})
export default class HogarSoporte {
  private readonly api = inject(SoporteApi);
  readonly hogarId = input.required({ transform: numberAttribute });
  private readonly queryClient = inject(QueryClient);
  private readonly avisos = inject(Avisos);
  protected readonly seleccion = signal<number[]>([]);
  protected readonly destino = signal<number | null>(null);

  protected readonly hogar = injectQuery(() => ({
    queryKey: ['soporte', 'hogar', this.hogarId()],
    queryFn: () => lastValueFrom(this.api.hogar(this.hogarId())),
  }));

  /** Módulo 81: los movimientos sin categoría de ESTE hogar (filtro sin_categoria del backoffice). */
  protected readonly sinCategoria = injectQuery(() => ({
    queryKey: ['soporte', 'hogar', this.hogarId(), 'sin-categoria'],
    queryFn: () =>
      lastValueFrom(
        this.api.movimientos({ hogar: this.hogarId(), sin_categoria: true, page_size: 100 }),
      ),
  }));

  protected readonly recategorizar = injectMutation(() => ({
    mutationFn: () => lastValueFrom(this.api.recategorizar(this.seleccion(), this.destino()!)),
    onSuccess: (r) => {
      this.avisos.exito(
        `${r.hechos} recategorizados${r.omitidos ? `, ${r.omitidos} omitidos` : ''}`,
      );
      this.seleccion.set([]);
      return this.queryClient.invalidateQueries({ queryKey: ['soporte', 'hogar', this.hogarId()] });
    },
  }));

  protected alternar(id: number) {
    this.seleccion.update((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }
}
