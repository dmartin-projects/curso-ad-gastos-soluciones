import { Component, DestroyRef, ElementRef, inject, input, output, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { debounceTime, distinctUntilChanged, Subject } from 'rxjs';

import { Categoria, FiltrosMovimientos } from '../../interfaces/movimientos.models';

/** Presentacional: recibe los filtros (de la URL) y emite los cambios. No sabe nada del router. */
@Component({
  selector: 'app-filtros-movimientos',
  imports: [
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonToggleModule,
    MatChipsModule,
    MatIconModule,
  ],
  templateUrl: './filtros-movimientos.html',
})
export class FiltrosMovimientosComponent {
  readonly valor = input.required<FiltrosMovimientos>();
  readonly categorias = input<Categoria[]>([]);
  readonly cambio = output<Partial<FiltrosMovimientos>>();
  private readonly busquedaInput =
    viewChild.required<ElementRef<HTMLInputElement>>('busquedaInput');

  /** Para el atajo "/" (módulo 80): el padre pide el foco sin conocer el DOM de este componente. */
  enfocarBusqueda() {
    this.busquedaInput().nativeElement.focus();
    this.busquedaInput().nativeElement.select();
  }

  /** Teclear no lanza una petición por letra: se espera a que el usuario pare 300 ms (RxJS, módulo 46). */
  protected readonly busqueda = new Subject<string>();

  constructor() {
    this.busqueda
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(inject(DestroyRef)))
      .subscribe((q) => this.cambiar({ q: q || undefined }));
  }

  protected cambiar(cambio: Partial<FiltrosMovimientos>) {
    this.cambio.emit(cambio);
  }
}
