import { inject, Service } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';

@Service()
export class Avisos {
  private readonly snack = inject(MatSnackBar);

  exito(mensaje: string) {
    this.snack.open(mensaje, 'Cerrar', { duration: 3000 });
  }

  error(mensaje: string) {
    this.snack.open(mensaje, 'Cerrar', { duration: 6000, politeness: 'assertive' });
  }
}
