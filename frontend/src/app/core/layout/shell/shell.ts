import { BreakpointObserver } from '@angular/cdk/layout';
import { Component, computed, DestroyRef, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { MatMenuModule } from '@angular/material/menu';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';

import { AuthStore } from '../../auth/auth-store';
import { Campana } from '../../notificaciones/campana/campana';
import { Tema } from '../../tema/tema';
import { AvisoConexion } from '../../tiempo-real/aviso-conexion/aviso-conexion';
import { Sincronizacion } from '../../tiempo-real/sincronizacion';
import { HogarStore } from '../../hogar/hogar-store';

const SECCIONES = [
  { ruta: 'dashboard', icono: 'monitoring', texto: 'Resumen' },
  { ruta: 'movimientos', icono: 'receipt_long', texto: 'Movimientos' },
  { ruta: 'tickets', icono: 'photo_camera', texto: 'Tickets' },
  { ruta: 'importaciones', icono: 'upload_file', texto: 'Importar extracto' },
  { ruta: 'presupuestos', icono: 'savings', texto: 'Presupuestos' },
  { ruta: 'categorias', icono: 'category', texto: 'Categorías' },
  { ruta: 'informes', icono: 'picture_as_pdf', texto: 'Informes' },
];

@Component({
  selector: 'app-shell',
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatSidenavModule,
    MatListModule,
    MatIconModule,
    MatButtonModule,
    MatMenuModule,
    Campana,
    AvisoConexion,
  ],
  templateUrl: './shell.html',
})
export default class Shell {
  protected readonly store = inject(HogarStore);
  protected readonly auth = inject(AuthStore);
  private readonly router = inject(Router);
  protected readonly secciones = SECCIONES;
  protected readonly tema = inject(Tema);
  protected readonly iconosTema = {
    sistema: 'brightness_auto',
    claro: 'light_mode',
    oscuro: 'dark_mode',
  };
  protected readonly nombresTema = { sistema: 'del sistema', claro: 'claro', oscuro: 'oscuro' };
  protected readonly hogar = this.store.activo;
  protected readonly movil = toSignal(
    inject(BreakpointObserver)
      .observe('(max-width: 768px)')
      .pipe(map((r) => r.matches)),
    { initialValue: false },
  );
  private readonly url = toSignal(
    this.router.events.pipe(
      filter((e) => e instanceof NavigationEnd),
      map(() => this.router.url),
    ),
    { initialValue: this.router.url },
  );
  /** La sección actual (/hogares/3/movimientos → "movimientos") para mantenerla al cambiar de hogar. */
  private readonly seccion = computed(() => this.url().split('?')[0].split('/')[3] ?? 'dashboard');

  constructor() {
    inject(Sincronizacion).iniciar(inject(DestroyRef)); // el WebSocket vive mientras el armazón (la sesión) existe
  }

  protected cambiarHogar(id: number) {
    this.router.navigate(['/hogares', id, this.seccion()]);
  }
}
