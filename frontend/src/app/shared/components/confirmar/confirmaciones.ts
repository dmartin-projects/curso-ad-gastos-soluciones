import { inject, Service } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { firstValueFrom } from 'rxjs';

import { DatosConfirmar, DialogoConfirmar } from './confirmar';

/** `await confirmaciones.preguntar(…)`: true si la persona confirma (el diálogo, en confirmar.ts). */
@Service()
export class Confirmaciones {
  private readonly dialog = inject(MatDialog);

  async preguntar(titulo: string, mensaje: string, accion = 'Aceptar'): Promise<boolean> {
    const ref = this.dialog.open<DialogoConfirmar, DatosConfirmar, boolean>(DialogoConfirmar, {
      data: { titulo, mensaje, accion },
      role: 'alertdialog',
    });
    return (await firstValueFrom(ref.afterClosed())) === true;
  }
}
