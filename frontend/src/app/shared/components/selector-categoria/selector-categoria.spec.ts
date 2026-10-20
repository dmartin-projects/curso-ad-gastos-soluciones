import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { form, FormField } from '@angular/forms/signals';

import { OpcionCategoria, SelectorCategoria } from './selector-categoria';

const CATEGORIAS = [
  { id: 1, nombre: 'Comida', color: '#0a0', padre: null },
  { id: 2, nombre: 'Fruta', color: '#0b0', padre: 1 },
  { id: 3, nombre: 'Ocio', color: '#00a', padre: null },
] satisfies OpcionCategoria[];

@Component({
  imports: [SelectorCategoria, FormField],
  template: `<app-selector-categoria [formField]="f.categoria" [categorias]="categorias" />`,
})
class Anfitrion {
  readonly modelo = signal({ categoria: null as number | null });
  readonly f = form(this.modelo);
  readonly categorias = CATEGORIAS;
}

describe('SelectorCategoria como control de Signal Forms', () => {
  it('ordena padres e hijas, y elegir dos veces la misma la desmarca', async () => {
    const fixture = TestBed.createComponent(Anfitrion);
    await fixture.whenStable();
    const botones = () =>
      [...fixture.nativeElement.querySelectorAll('button')] as HTMLButtonElement[];
    expect(botones().map((b) => b.textContent!.trim())).toEqual(['Comida', '· Fruta', 'Ocio']);

    botones()[1].click();
    await fixture.whenStable();
    expect(fixture.componentInstance.modelo().categoria).toBe(2);
    expect(botones()[1].getAttribute('aria-checked')).toBe('true');
    expect(fixture.componentInstance.f.categoria().touched()).toBe(true);

    botones()[1].click();
    expect(fixture.componentInstance.modelo().categoria).toBeNull();
  });
});
