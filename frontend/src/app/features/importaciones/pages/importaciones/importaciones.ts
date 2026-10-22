import { DatePipe } from '@angular/common';
import { Component, computed, inject, linkedSignal, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Router, RouterLink } from '@angular/router';
import { injectMutation, injectQuery } from '@tanstack/angular-query-experimental';
import { lastValueFrom } from 'rxjs';

import { opcionesCuentas } from '../../../../core/hogar/consultas';
import { HogarStore } from '../../../../core/hogar/hogar-store';
import { HogaresApi } from '../../../../core/hogar/hogares-api';
import { ErrorApi } from '../../../../core/http/errores';
import { ESTADOS_IMPORTACION } from '../../interfaces/importaciones.models';
import { ImportacionesApi } from '../../services/importaciones-api';

@Component({
  selector: 'app-importaciones',
  imports: [
    DatePipe,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
  ],
  templateUrl: './importaciones.html',
})
export default class Importaciones {
  protected readonly store = inject(HogarStore);
  private readonly api = inject(ImportacionesApi);
  private readonly hogaresApi = inject(HogaresApi);
  private readonly router = inject(Router);
  protected readonly estados = ESTADOS_IMPORTACION;
  private readonly hogarId = computed(() => this.store.activoId()!);

  protected readonly cuentas = injectQuery(() => opcionesCuentas(this.hogaresApi, this.hogarId()));
  protected readonly cuenta = linkedSignal<number | null>(
    () => this.cuentas.data()?.[0]?.id ?? null,
  );
  protected readonly importaciones = injectQuery(() => ({
    queryKey: ['hogar', this.hogarId(), 'importaciones', 'lista'],
    queryFn: () => lastValueFrom(this.api.listar(this.hogarId())),
  }));
  protected readonly error = signal<string | null>(null);

  protected elegir(input: HTMLInputElement) {
    const archivo = input.files?.[0];
    input.value = ''; // permite volver a elegir el mismo archivo
    if (!archivo) return;
    // las cuentas llegan de la API: si el archivo se elige antes, aún no hay cuenta y no se puede subir
    if (!this.cuenta()) return this.error.set('Elige primero la cuenta.');
    this.subir.mutate(archivo);
  }

  protected readonly subir = injectMutation(() => ({
    mutationFn: (archivo: File) =>
      lastValueFrom(this.api.subir(this.hogarId(), this.cuenta()!, archivo)),
    onMutate: () => this.error.set(null),
    // 202: el análisis sigue en el servidor; vamos a la pantalla de la importación, que se irá actualizando
    onSuccess: (imp) => this.router.navigate(['/hogares', this.hogarId(), 'importaciones', imp.id]),
    onError: (e) =>
      this.error.set(
        e instanceof ErrorApi
          ? (Object.values(e.errores)[0]?.[0] ?? e.titulo)
          : 'No se pudo subir.',
      ),
  }));
}
