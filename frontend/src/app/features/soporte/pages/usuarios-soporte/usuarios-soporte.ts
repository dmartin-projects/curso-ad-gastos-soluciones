import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import {
  injectMutation,
  injectQuery,
  keepPreviousData,
  QueryClient,
} from '@tanstack/angular-query-experimental';
import { lastValueFrom } from 'rxjs';

import { UsuarioSoporte } from '../../../../core/api/tipos';
import { Avisos } from '../../../../core/http/avisos';
import { ErrorApi } from '../../../../core/http/errores';
import { Buscador } from '../../components/buscador/buscador';
import { SoporteApi } from '../../services/soporte-api';

@Component({
  selector: 'app-usuarios-soporte',
  imports: [DatePipe, MatSlideToggleModule, MatPaginatorModule, Buscador],
  templateUrl: './usuarios-soporte.html',
})
export default class UsuariosSoporte {
  private readonly api = inject(SoporteApi);
  private readonly queryClient = inject(QueryClient);
  private readonly avisos = inject(Avisos);
  protected readonly busqueda = signal('');
  protected readonly pagina = signal(1);
  protected readonly usuarios = injectQuery(() => ({
    queryKey: ['soporte', 'usuarios', this.busqueda(), this.pagina()],
    queryFn: () =>
      lastValueFrom(this.api.usuarios({ search: this.busqueda(), page: this.pagina() })),
    placeholderData: keepPreviousData,
  }));

  protected readonly activar = injectMutation(() => ({
    mutationFn: ({ usuario, activo }: { usuario: UsuarioSoporte; activo: boolean }) =>
      lastValueFrom(this.api.activar(usuario.id, activo)),
    onSuccess: (u) => this.avisos.exito(`${u.email} ${u.is_active ? 'activado' : 'desactivado'}`),
    onError: (e) => {
      if (e instanceof ErrorApi && e.tipo === 'validacion')
        this.avisos.error(Object.values(e.errores)[0]?.[0] ?? e.titulo);
    },
    onSettled: () => this.queryClient.invalidateQueries({ queryKey: ['soporte', 'usuarios'] }),
  }));

  protected paginar(e: PageEvent) {
    this.pagina.set(e.pageIndex + 1);
  }
}
