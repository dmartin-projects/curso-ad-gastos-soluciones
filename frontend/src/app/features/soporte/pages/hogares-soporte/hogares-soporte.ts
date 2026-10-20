import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { injectQuery, keepPreviousData } from '@tanstack/angular-query-experimental';
import { lastValueFrom } from 'rxjs';

import { Buscador } from '../../components/buscador/buscador';
import { SoporteApi } from '../../services/soporte-api';

@Component({
  selector: 'app-hogares-soporte',
  imports: [DatePipe, RouterLink, MatTableModule, MatPaginatorModule, Buscador],
  templateUrl: './hogares-soporte.html',
})
export default class HogaresSoporte {
  private readonly api = inject(SoporteApi);
  protected readonly columnas = ['nombre', 'miembros', 'movimientos', 'creado'];
  protected readonly busqueda = signal('');
  protected readonly pagina = signal(1);
  protected readonly hogares = injectQuery(() => ({
    queryKey: ['soporte', 'hogares', this.busqueda(), this.pagina()],
    queryFn: () =>
      lastValueFrom(this.api.hogares({ search: this.busqueda(), page: this.pagina() })),
    placeholderData: keepPreviousData,
  }));

  protected paginar(e: PageEvent) {
    this.pagina.set(e.pageIndex + 1);
  }
}
