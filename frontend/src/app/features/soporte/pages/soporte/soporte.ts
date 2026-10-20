import { Component } from '@angular/core';
import { MatTabsModule } from '@angular/material/tabs';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

const PESTANAS = [
  { ruta: 'panel', texto: 'Panel' },
  { ruta: 'hogares', texto: 'Hogares' },
  { ruta: 'usuarios', texto: 'Usuarios' },
  { ruta: 'auditoria', texto: 'Auditoría' },
  { ruta: 'tareas', texto: 'Tareas programadas' },
];

/** Armazón de la sección de soporte: pestañas que son rutas (cada una se carga al visitarla). */
@Component({
  selector: 'app-soporte',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, MatTabsModule],
  templateUrl: './soporte.html',
})
export default class Soporte {
  protected readonly pestanas = PESTANAS;
}
