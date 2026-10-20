import { DatePipe, JsonPipe, KeyValuePipe } from '@angular/common';
import { Component, inject, input, linkedSignal } from '@angular/core';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatSelectModule } from '@angular/material/select';
import { injectQuery, keepPreviousData } from '@tanstack/angular-query-experimental';
import { lastValueFrom } from 'rxjs';

import { Buscador } from '../../components/buscador/buscador';
import { SoporteApi } from '../../services/soporte-api';

const MODELOS = [
  { valor: '', texto: 'Todo' },
  { valor: 'finanzas.movimiento', texto: 'Movimientos' },
  { valor: 'tickets.ticket', texto: 'Tickets' },
  { valor: 'importaciones.importacion', texto: 'Importaciones' },
  { valor: 'usuarios.usuario', texto: 'Usuarios' },
];

@Component({
  selector: 'app-auditoria',
  imports: [
    DatePipe,
    JsonPipe,
    KeyValuePipe,
    MatExpansionModule,
    MatFormFieldModule,
    MatSelectModule,
    MatPaginatorModule,
    Buscador,
  ],
  templateUrl: './auditoria.html',
})
export default class Auditoria {
  private readonly api = inject(SoporteApi);
  protected readonly modelos = MODELOS;
  readonly busquedaInicial = input<string>(undefined, { alias: 'q' }); // ?q= desde la ficha de un hogar
  protected readonly q = linkedSignal(() => this.busquedaInicial() ?? '');
  protected readonly modelo = linkedSignal(() => '');
  protected readonly pagina = linkedSignal(() => 1);

  protected readonly registros = injectQuery(() => ({
    queryKey: ['soporte', 'auditoria', this.q(), this.modelo(), this.pagina()],
    queryFn: () =>
      lastValueFrom(
        this.api.auditoria({ search: this.q(), modelo: this.modelo(), page: this.pagina() }),
      ),
    placeholderData: keepPreviousData,
  }));

  protected paginar(e: PageEvent) {
    this.pagina.set(e.pageIndex + 1);
  }
}
