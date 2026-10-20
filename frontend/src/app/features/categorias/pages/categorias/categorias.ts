import {
  CdkDrag,
  CdkDragDrop,
  CdkDragHandle,
  CdkDragPlaceholder,
  CdkDropList,
  moveItemInArray,
} from '@angular/cdk/drag-drop';
import { Component, computed, inject, signal } from '@angular/core';
import { form, FormField, FormRoot, maxLength, pattern, required } from '@angular/forms/signals';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { injectMutation, injectQuery, QueryClient } from '@tanstack/angular-query-experimental';
import { firstValueFrom, lastValueFrom } from 'rxjs';

import { Categoria } from '../../../../core/api/tipos';
import { HogarStore } from '../../../../core/hogar/hogar-store';
import { Avisos } from '../../../../core/http/avisos';
import { erroresDelServidor } from '../../../../core/http/errores-formulario';
import { claves, opcionesCategorias } from '../../../../core/hogar/consultas';
import { HogaresApi } from '../../../../core/hogar/hogares-api';
import { CategoriasApi } from '../../services/categorias-api';

@Component({
  selector: 'app-categorias',
  imports: [
    CdkDropList,
    CdkDrag,
    CdkDragHandle,
    CdkDragPlaceholder,
    FormField,
    FormRoot,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatCheckboxModule,
  ],
  templateUrl: './categorias.html',
})
export default class Categorias {
  protected readonly store = inject(HogarStore);
  private readonly hogaresApi = inject(HogaresApi);
  private readonly api = inject(CategoriasApi);
  private readonly queryClient = inject(QueryClient);
  private readonly avisos = inject(Avisos);
  private readonly hogarId = computed(() => this.store.activoId()!);

  protected readonly categorias = injectQuery(() =>
    opcionesCategorias(this.hogaresApi, this.hogarId()),
  );
  protected readonly principales = computed(() =>
    (this.categorias.data() ?? [])
      .filter((c) => !c.padre)
      .sort((a, b) => (a.orden ?? 0) - (b.orden ?? 0)),
  );
  protected hijasDe(id: number) {
    return (this.categorias.data() ?? [])
      .filter((c) => c.padre === id)
      .map((c) => c.nombre)
      .join(', ');
  }

  /**
   * Actualización optimista (módulo 52): la lista cambia al soltar, sin esperar a la API.
   * Si la API falla, se vuelve al orden anterior.
   */
  private readonly reordenar = injectMutation(() => ({
    mutationFn: (ids: number[]) => lastValueFrom(this.api.reordenar(this.hogarId(), ids)),
    onMutate: async (ids: number[]) => {
      const clave = claves.categorias(this.hogarId());
      await this.queryClient.cancelQueries({ queryKey: clave }); // que una recarga en curso no pise el cambio
      const anterior = this.queryClient.getQueryData<Categoria[]>(clave);
      this.queryClient.setQueryData<Categoria[]>(clave, (actuales) =>
        actuales?.map((c) => (ids.includes(c.id) ? { ...c, orden: ids.indexOf(c.id) } : c)),
      );
      return { anterior };
    },
    onError: (_e, _ids, contexto) => {
      this.queryClient.setQueryData(claves.categorias(this.hogarId()), contexto?.anterior);
      this.avisos.error('No se pudo guardar el nuevo orden');
    },
    onSettled: () =>
      this.queryClient.invalidateQueries({ queryKey: claves.categorias(this.hogarId()) }),
  }));

  protected soltar(e: CdkDragDrop<Categoria[]>) {
    if (e.previousIndex === e.currentIndex) return;
    const ordenadas = [...this.principales()];
    moveItemInArray(ordenadas, e.previousIndex, e.currentIndex);
    this.reordenar.mutate(ordenadas.map((c) => c.id));
  }

  // ── Alta ──
  protected readonly modelo = signal({
    nombre: '',
    color: '#607d8b',
    padre: null as number | null,
    es_ingreso: false,
  });
  protected readonly f = form(
    this.modelo,
    (r) => {
      required(r.nombre, { message: 'Ponle un nombre' });
      maxLength(r.nombre, 60);
      pattern(r.color, /^#[0-9a-fA-F]{6}$/);
    },
    {
      submission: {
        action: async (f) => {
          try {
            await firstValueFrom(this.api.crear(this.hogarId(), this.modelo()));
            this.modelo.set({ nombre: '', color: '#607d8b', padre: null, es_ingreso: false });
            await this.queryClient.invalidateQueries({
              queryKey: claves.categorias(this.hogarId()),
            });
            return null;
          } catch (e) {
            return erroresDelServidor(e, f);
          }
        },
      },
    },
  );
}
