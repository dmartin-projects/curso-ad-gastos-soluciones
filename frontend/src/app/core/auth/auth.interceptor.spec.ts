import { HttpClient } from '@angular/common/http';
import { HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';

import { proveedoresDeTest } from '../../testing/proveedores';
import { ErrorApi } from '../http/errores';
import { AuthStore } from './auth-store';

describe('authInterceptor', () => {
  let http: HttpClient;
  let ctrl: HttpTestingController;
  let auth: AuthStore;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: proveedoresDeTest() });
    http = TestBed.inject(HttpClient);
    ctrl = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthStore);
    // sesión iniciada con un token que la API va a dar por caducado
    auth.login('a@b.c', 'x').subscribe();
    ctrl.expectOne('/api/v1/auth/login/').flush({ access: 'viejo' });
    ctrl.expectOne('/api/v1/auth/me/').flush({ id: 1, email: 'a@b.c', es_personal: false });
  });

  afterEach(() => ctrl.verify());

  it('tres 401 a la vez → un solo refresh y las tres se repiten con el token nuevo', () => {
    const urls = ['/api/v1/a/', '/api/v1/b/', '/api/v1/c/'];
    const respuestas: unknown[] = [];
    urls.forEach((u) => http.get(u).subscribe((r) => respuestas.push(r)));
    urls.forEach((u) => {
      const r = ctrl.expectOne(u);
      expect(r.request.headers.get('Authorization')).toBe('Bearer viejo');
      r.flush({}, { status: 401, statusText: 'Unauthorized' });
    });

    ctrl.expectOne('/api/v1/auth/refresh/').flush({ access: 'nuevo' }); // expectOne: si hubiera dos, falla

    urls.forEach((u) => {
      const r = ctrl.expectOne(u);
      expect(r.request.headers.get('Authorization')).toBe('Bearer nuevo');
      r.flush({ ok: u });
    });
    expect(respuestas).toHaveLength(3);
  });

  it('si el refresh también falla: logout, a /login y ErrorApi para quien llamó', () => {
    const navegar = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    let error: unknown;
    http.get('/api/v1/a/').subscribe({ error: (e) => (error = e) });
    ctrl.expectOne('/api/v1/a/').flush({}, { status: 401, statusText: 'Unauthorized' });
    ctrl
      .expectOne('/api/v1/auth/refresh/')
      .flush(
        { type: 'no_autenticado', title: 'Debes iniciar sesión.' },
        { status: 401, statusText: 'U' },
      );
    ctrl.expectOne('/api/v1/auth/logout/').flush(null);

    expect(navegar).toHaveBeenCalledWith('/login');
    expect(auth.autenticado()).toBe(false);
    expect(error).toBeInstanceOf(ErrorApi);
  });

  it('no pone el JWT fuera de nuestra API', () => {
    http.get('https://otro.example/datos').subscribe();
    expect(ctrl.expectOne('https://otro.example/datos').request.headers.has('Authorization')).toBe(
      false,
    );
  });
});
