import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';

export interface DatosConfirmar {
  titulo: string;
  mensaje: string;
  accion: string;
}

/** El diálogo de "¿seguro?". No se usa en plantillas: lo abre Confirmaciones. */
@Component({
  selector: 'app-confirmar',
  imports: [MatDialogModule, MatButtonModule],
  templateUrl: './confirmar.html',
})
export class DialogoConfirmar {
  protected readonly datos = inject<DatosConfirmar>(MAT_DIALOG_DATA);
}
