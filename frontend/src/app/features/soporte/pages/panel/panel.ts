import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { injectMutation, injectQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { lastValueFrom } from 'rxjs';

import { Avisos } from '../../../../core/http/avisos';
import { Confirmaciones } from '../../../../shared/components/confirmar/confirmaciones';
import { EstadoTicket } from '../../../../shared/components/estado-ticket/estado-ticket';
import { SoporteApi } from '../../services/soporte-api';

type Filtro = 'atascado' | 'error' | 'revisar';

@Component({
  selector: 'app-panel-soporte',
  imports: [
    DatePipe,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatCheckboxModule,
    MatChipsModule,
    EstadoTicket,
  ],
  templateUrl: './panel.html',
})
export default class Panel {
  private readonly api = inject(SoporteApi);
  private readonly queryClient = inject(QueryClient);
  private readonly avisos = inject(Avisos);
  private readonly confirmaciones = inject(Confirmaciones);
  protected readonly filtro = signal<Filtro>('atascado');
  protected readonly seleccion = signal<number[]>([]);

  protected readonly resumen = injectQuery(() => ({
    queryKey: ['soporte', 'resumen'],
    queryFn: () => lastValueFrom(this.api.resumen()),
    refetchInterval: 30_000, // un panel de guardia se refresca solo
  }));
  protected readonly tickets = injectQuery(() => ({
    queryKey: ['soporte', 'tickets', this.filtro()],
    queryFn: () =>
      lastValueFrom(
        this.api.tickets(
          this.filtro() === 'atascado' ? { atascado: true } : { estado: this.filtro() },
        ),
      ),
  }));
  protected readonly importaciones = injectQuery(() => ({
    queryKey: ['soporte', 'importaciones', 'error'],
    queryFn: () => lastValueFrom(this.api.importaciones({ estado: 'error' })),
  }));

  protected alternar(id: number) {
    this.seleccion.update((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  protected readonly reprocesar = injectMutation(() => ({
    mutationFn: (ids: number[]) => lastValueFrom(this.api.reprocesar(ids)),
    onSuccess: (r) => {
      this.avisos.exito(`${r.hechos} reprocesados${r.omitidos ? `, ${r.omitidos} omitidos` : ''}`);
      this.seleccion.set([]);
      return this.queryClient.invalidateQueries({ queryKey: ['soporte'] });
    },
  }));

  protected async deshacer(id: number) {
    if (
      !(await this.confirmaciones.preguntar(
        'Deshacer importación',
        'Se borrará lo que llegó a importar.',
        'Deshacer',
      ))
    )
      return;
    await lastValueFrom(this.api.deshacer(id));
    await this.queryClient.invalidateQueries({ queryKey: ['soporte'] });
  }
}
