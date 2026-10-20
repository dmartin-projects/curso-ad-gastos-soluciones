import { Routes } from '@angular/router';

/** /hogares/:hogarId/importaciones/… */
export default [
  { path: '', loadComponent: () => import('./pages/importaciones/importaciones') },
  { path: ':importacionId', loadComponent: () => import('./pages/importacion/importacion') },
] satisfies Routes;
