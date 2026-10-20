import { CdkVirtualScrollViewport, ScrollingModule } from '@angular/cdk/scrolling';
import { DatePipe } from '@angular/common';
import { booleanAttribute, Component, computed, inject, input, viewChild } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Router } from '@angular/router';
import {
  injectInfiniteQuery,
  injectMutation,
  injectQuery,
  QueryClient,
} from '@tanstack/angular-query-experimental';
import { firstValueFrom, lastValueFrom } from 'rxjs';

import { Movimiento } from '../../../../core/api/tipos';
import { claves, opcionesCategorias, opcionesCuentas } from '../../../../core/hogar/consultas';
import { HogarStore } from '../../../../core/hogar/hogar-store';
import { HogaresApi } from '../../../../core/hogar/hogares-api';
import { Avisos } from '../../../../core/http/avisos';
import { erroresDelServidor } from '../../../../core/http/errores-formulario';
import { Confirmaciones } from '../../../../shared/components/confirmar/confirmaciones';
import { Importe } from '../../../../shared/components/importe/importe';
import {
  DatosFormularioMovimiento,
  FormularioMovimiento,
} from '../../components/dialogs/formulario-movimiento/formulario-movimiento';
import { FiltrosMovimientosComponent } from '../../components/filtros-movimientos/filtros-movimientos';
import { FiltrosMovimientos } from '../../interfaces/movimientos.models';
import { MovimientosApi } from '../../services/movimientos-api';

/** "3" → 3; ausente o basura → undefined (con numberAttribute, un parámetro ausente daría NaN, módulo 50). */
const numeroOpcional = (v: unknown) =>
  v == null || v === '' || isNaN(Number(v)) ? undefined : Number(v);

@Component({
  selector: 'app-movimientos',
  imports: [
    ScrollingModule,
    DatePipe,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatProgressBarModule,
    Importe,
    FiltrosMovimientosComponent,
  ],
  templateUrl: './movimientos.html',
})
export default class Movimientos {
  protected readonly store = inject(HogarStore);
  private readonly api = inject(MovimientosApi);
  private readonly hogaresApi = inject(HogaresApi);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly queryClient = inject(QueryClient);
  private readonly avisos = inject(Avisos);
  private readonly confirmaciones = inject(Confirmaciones);
  private readonly viewport = viewChild(CdkVirtualScrollViewport);

  // ── Filtros: la URL es la fuente de verdad (?q=…&categoria=…), enlazada como inputs (withComponentInputBinding)
  readonly q = input<string>();
  readonly desde = input<string>();
  readonly hasta = input<string>();
  readonly categoria = input(undefined, { transform: numeroOpcional });
  readonly tipo = input<'gasto' | 'ingreso'>();
  readonly pendientes = input(false, { transform: booleanAttribute });

  protected readonly filtros = computed<FiltrosMovimientos>(() => ({
    q: this.q(),
    desde: this.desde(),
    hasta: this.hasta(),
    categoria: this.categoria(),
    tipo: this.tipo(),
    pendientes: this.pendientes() || undefined,
  }));

  private readonly hogarId = computed(() => this.store.activoId()!);

  protected readonly categorias = injectQuery(() =>
    opcionesCategorias(this.hogaresApi, this.hogarId()),
  );
  private readonly cuentas = injectQuery(() => opcionesCuentas(this.hogaresApi, this.hogarId()));

  /** Scroll infinito con la paginación por cursor de la API: cada página trae `next`. */
  protected readonly movimientos = injectInfiniteQuery(() => ({
    queryKey: [...claves.movimientos(this.hogarId()), this.filtros()],
    queryFn: ({ pageParam }) =>
      lastValueFrom(this.api.pagina(this.hogarId(), this.filtros(), pageParam)),
    initialPageParam: null as string | null,
    getNextPageParam: (ultima) => ultima.next,
  }));

  protected readonly filas = computed(
    () => this.movimientos.data()?.pages.flatMap((p) => p.results) ?? [],
  );
  protected readonly porId = (_: number, m: Movimiento) => m.id;

  private readonly borrado = injectMutation(() => ({
    mutationFn: (m: Movimiento) => lastValueFrom(this.api.borrar(this.hogarId(), m.id)),
    onSuccess: () => {
      this.avisos.exito('Movimiento borrado');
      return this.queryClient.invalidateQueries({ queryKey: claves.movimientos(this.hogarId()) });
    },
  }));

  protected alDesplazar() {
    const vp = this.viewport();
    if (!vp || !this.movimientos.hasNextPage() || this.movimientos.isFetchingNextPage()) return;
    if (vp.getRenderedRange().end > this.filas().length - 15) this.movimientos.fetchNextPage(); // a 15 filas del final
  }

  protected filtrar(cambio: Partial<FiltrosMovimientos>) {
    // replaceUrl: cada letra de la búsqueda no debe crear una entrada en el historial del navegador
    this.router.navigate([], {
      queryParams: cambio,
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  /** El formulario es presentacional: recibe los catálogos y CÓMO guardar; guardar (con el service) es de la page. */
  protected abrirFormulario(movimiento?: Movimiento) {
    if (movimiento && !this.store.puedeEditar()) return;
    const hogarId = this.hogarId();
    this.dialog
      .open<FormularioMovimiento, DatosFormularioMovimiento, boolean>(FormularioMovimiento, {
        data: {
          movimiento,
          cuentas: computed(() => this.cuentas.data() ?? []),
          categorias: computed(() => this.categorias.data() ?? []),
          guardar: async (cuerpo, formulario) => {
            try {
              await firstValueFrom(
                movimiento
                  ? this.api.actualizar(hogarId, movimiento.id, cuerpo)
                  : this.api.crear(hogarId, cuerpo),
              );
              return null;
            } catch (e) {
              return erroresDelServidor(e, formulario);
            }
          },
        },
        width: '32rem',
        autoFocus: 'first-tabbable',
      })
      .afterClosed()
      .subscribe((guardado) => {
        if (!guardado) return;
        this.avisos.exito(movimiento ? 'Movimiento actualizado' : 'Movimiento creado');
        this.queryClient.invalidateQueries({ queryKey: claves.movimientos(hogarId) });
      });
  }

  protected async borrar(m: Movimiento) {
    if (
      await this.confirmaciones.preguntar('Borrar movimiento', `¿Borrar «${m.concepto}»?`, 'Borrar')
    ) {
      this.borrado.mutate(m);
    }
  }
}
