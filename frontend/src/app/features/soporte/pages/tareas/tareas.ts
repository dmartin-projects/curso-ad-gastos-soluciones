import { DatePipe } from '@angular/common';
import { Component, inject } from '@angular/core';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { injectMutation, injectQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { lastValueFrom } from 'rxjs';

import { SoporteApi } from '../../services/soporte-api';

@Component({
  selector: 'app-tareas',
  imports: [DatePipe, MatSlideToggleModule],
  templateUrl: './tareas.html',
})
export default class Tareas {
  private readonly api = inject(SoporteApi);
  private readonly queryClient = inject(QueryClient);
  protected readonly tareas = injectQuery(() => ({
    queryKey: ['soporte', 'tareas'],
    queryFn: () => lastValueFrom(this.api.tareas()),
  }));
  protected readonly cambiar = injectMutation(() => ({
    mutationFn: ({ id, activa }: { id: number; activa: boolean }) =>
      lastValueFrom(this.api.pausar(id, activa)),
    onSettled: () => this.queryClient.invalidateQueries({ queryKey: ['soporte', 'tareas'] }),
  }));
}
