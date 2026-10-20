import { inject } from '@angular/core';
import { CanMatchFn, Router } from '@angular/router';

import { AuthStore } from './auth-store';

/** canMatch (no canActivate): sin sesión, ni siquiera se descarga el código de la zona privada (módulo 50). */
export const conSesion: CanMatchFn = (_ruta, segmentos) => {
  if (inject(AuthStore).autenticado()) return true;
  const destino = '/' + segmentos.map((s) => s.path).join('/');
  return inject(Router).createUrlTree(['/login'], {
    queryParams: destino !== '/' ? { volver: destino } : {},
  });
};

export const sinSesion: CanMatchFn = () =>
  inject(AuthStore).autenticado() ? inject(Router).createUrlTree(['/hogares']) : true;

/** Solo para el personal (backoffice). Es comodidad: no descargar ni enseñar lo que no puede usar; protege la API. */
export const esPersonal: CanMatchFn = () =>
  inject(AuthStore).usuario()?.es_personal ? true : inject(Router).createUrlTree(['/hogares']);
