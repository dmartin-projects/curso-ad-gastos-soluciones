import { Component, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { firstValueFrom } from 'rxjs';

import { InformesApi } from '../../services/informes-api';

/**
 * /baja-informes?token=…: el enlace del pie del email (módulo 78). Pública: no hace falta iniciar sesión.
 * El email lleva además la cabecera List-Unsubscribe, con la que el propio cliente de correo da de baja.
 * Pide un clic a propósito: abrir el enlace (o que lo abra un antivirus) no cambia nada.
 */
@Component({
  selector: 'app-baja-informes',
  imports: [MatCardModule, MatButtonModule],
  templateUrl: './baja-informes.html',
})
export default class BajaInformes {
  private readonly api = inject(InformesApi);
  readonly token = input<string>(); // ?token=… (withComponentInputBinding)
  protected readonly estado = signal<'inicio' | 'enviando' | 'hecho' | 'error'>('inicio');

  protected async darseDeBaja() {
    this.estado.set('enviando');
    try {
      await firstValueFrom(this.api.baja(this.token()!));
      this.estado.set('hecho');
    } catch {
      this.estado.set('error');
    }
  }
}
