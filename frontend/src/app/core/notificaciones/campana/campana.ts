import { DatePipe } from '@angular/common';
import { Component, inject } from '@angular/core';
import { MatBadgeModule } from '@angular/material/badge';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router, RouterLink } from '@angular/router';

import { TiempoReal } from '../../tiempo-real/tiempo-real';
import { NotificacionesStore } from '../notificaciones-store';

@Component({
  selector: 'app-campana',
  imports: [
    DatePipe,
    RouterLink,
    MatBadgeModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatDividerModule,
    MatTooltipModule,
  ],
  templateUrl: './campana.html',
})
export class Campana {
  protected readonly store = inject(NotificacionesStore);
  protected readonly tiempoReal = inject(TiempoReal);
  private readonly router = inject(Router);

  protected abrir(id: number, enlace: string) {
    this.store.leer(id);
    if (enlace) this.router.navigateByUrl(enlace);
  }
}
