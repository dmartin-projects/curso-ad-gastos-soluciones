import { Component, computed, input, model, output } from '@angular/core';
import { FormValueControl } from '@angular/forms/signals';

/** Lo que el selector necesita de cada categoría. La `Categoria` de la API lo cumple, y shared/ no depende de ella. */
export interface OpcionCategoria {
  id: number;
  nombre: string;
  color?: string;
  padre?: number | null;
}

/** Control propio para Signal Forms (módulo 53): basta con un model() llamado `value`. */
@Component({
  selector: 'app-selector-categoria',
  templateUrl: './selector-categoria.html',
})
export class SelectorCategoria implements FormValueControl<number | null> {
  readonly value = model<number | null>(null);
  readonly disabled = input(false);
  readonly touch = output<void>();
  readonly categorias = input.required<OpcionCategoria[]>();
  readonly etiqueta = input('Categoría');

  /** Cada padre seguido de sus hijas. */
  protected readonly ordenadas = computed(() => {
    const todas = this.categorias();
    return todas
      .filter((c) => !c.padre)
      .flatMap((p) => [p, ...todas.filter((c) => c.padre === p.id)]);
  });

  protected elegir(id: number) {
    this.value.set(this.value() === id ? null : id); // pulsar la elegida la desmarca
    this.touch.emit();
  }
}
