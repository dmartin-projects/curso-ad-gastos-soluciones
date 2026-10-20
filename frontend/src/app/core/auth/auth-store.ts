import { HttpClient, HttpContext } from '@angular/common/http';
import { computed, inject, Service, signal } from '@angular/core';
import { Router } from '@angular/router';
import { QueryClient } from '@tanstack/angular-query-experimental';
import {
  catchError,
  finalize,
  firstValueFrom,
  map,
  Observable,
  of,
  shareReplay,
  switchMap,
  tap,
} from 'rxjs';

import { Usuario } from '../api/tipos';
import { SIN_AUTH, SIN_AVISO_ERROR } from '../http/contexto';

const SIN_TOKEN = () => new HttpContext().set(SIN_AUTH, true).set(SIN_AVISO_ERROR, true);

/**
 * Sesión: el access token vive SOLO en memoria (una signal); el refresh, en una cookie HttpOnly
 * que el navegador envía sola a /api/v1/auth/ (módulos 35 y 51). Nada en localStorage.
 */
@Service()
export class AuthStore {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly queryClient = inject(QueryClient);

  private readonly _access = signal<string | null>(null);
  readonly access = this._access.asReadonly();
  readonly usuario = signal<Usuario | null>(null);
  readonly autenticado = computed(() => this._access() !== null);

  private refrescoEnCurso: Observable<string> | null = null;

  login(email: string, password: string) {
    return this.http
      .post<{ access: string }>(
        '/api/v1/auth/login/',
        { email, password },
        { context: SIN_TOKEN() },
      )
      .pipe(
        tap((r) => this._access.set(r.access)),
        switchMap(() => this.cargarUsuario()),
      );
  }

  /** Una sola petición de refresh aunque la pidan varias peticiones a la vez. */
  refrescar(): Observable<string> {
    this.refrescoEnCurso ??= this.http
      .post<{ access: string }>('/api/v1/auth/refresh/', null, { context: SIN_TOKEN() })
      .pipe(
        map((r) => r.access),
        tap({ next: (a) => this._access.set(a), error: () => this.limpiar() }),
        finalize(() => (this.refrescoEnCurso = null)),
        shareReplay({ bufferSize: 1, refCount: false }),
      );
    return this.refrescoEnCurso;
  }

  /** Al arrancar: si la cookie de refresh sigue siendo válida, se recupera la sesión sin pedir contraseña. */
  restaurarSesion(): Promise<unknown> {
    return firstValueFrom(
      this.refrescar().pipe(
        switchMap(() => this.cargarUsuario()),
        catchError(() => of(null)),
      ),
    );
  }

  logout() {
    this.http
      .post('/api/v1/auth/logout/', null, { context: SIN_TOKEN() })
      .subscribe({ error: () => undefined }); // si falla (sin red), la sesión local se cierra igual
    this.limpiar();
    this.router.navigateByUrl('/login');
  }

  private cargarUsuario() {
    return this.http.get<Usuario>('/api/v1/auth/me/').pipe(tap((u) => this.usuario.set(u)));
  }

  private limpiar() {
    this._access.set(null);
    this.usuario.set(null);
    this.queryClient.clear(); // los datos cacheados eran de otro usuario
  }
}
