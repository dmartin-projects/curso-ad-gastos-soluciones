import { Component, inject, OnInit, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { Router } from '@angular/router';

import { HogarStore } from '../../../../core/hogar/hogar-store';
import { ArchivoCompartido } from '../../../../core/compartir/archivo-compartido';

/** /compartir: a dónde llega el share_target tras pasar por el service worker. Elige hogar y sigue. */
@Component({
  selector: 'app-compartir',
  imports: [MatButtonModule],
  templateUrl: './compartir.html',
})
export default class Compartir implements OnInit {
  protected readonly store = inject(HogarStore);
  private readonly compartido = inject(ArchivoCompartido);
  private readonly router = inject(Router);
  protected readonly sinArchivo = signal(false);
  protected readonly elegir = signal(false);

  async ngOnInit() {
    const [archivo] = await Promise.all([this.compartido.recoger(), this.store.cargar()]);
    if (!archivo) return this.sinArchivo.set(true);
    const hogares = this.store.hogares();
    const destino = this.store.ultimo() ?? (hogares.length === 1 ? hogares[0].id : null);
    if (destino) this.ir(destino);
    else this.elegir.set(true);
  }

  protected ir(hogarId: number) {
    this.router.navigate(['/hogares', hogarId, 'tickets'], { replaceUrl: true });
  }
}
