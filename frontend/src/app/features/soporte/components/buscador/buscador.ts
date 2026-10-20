import { Component, DestroyRef, inject, input, output } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { debounceTime, distinctUntilChanged, Subject } from 'rxjs';

@Component({
  selector: 'app-buscador',
  imports: [MatFormFieldModule, MatInputModule, MatIconModule],
  templateUrl: './buscador.html',
})
export class Buscador {
  readonly placeholder = input('Buscar');
  readonly buscar = output<string>();
  protected readonly texto = new Subject<string>();

  constructor() {
    this.texto
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(inject(DestroyRef)))
      .subscribe((t) => this.buscar.emit(t));
  }
}
