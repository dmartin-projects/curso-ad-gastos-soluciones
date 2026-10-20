import { Routes } from '@angular/router';

import { conSesion, esPersonal, sinSesion } from './core/auth/guards';
import { hogarGuard } from './core/hogar/hogar.guard';

export const routes: Routes = [
  {
    path: 'login',
    canMatch: [sinSesion],
    loadComponent: () => import('./features/auth/pages/login/login'),
  },
  {
    path: '',
    canMatch: [conSesion],
    loadComponent: () => import('./core/layout/shell/shell'), // también el armazón: el login no lo necesita
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'hogares' },
      {
        path: 'hogares',
        loadComponent: () => import('./features/hogares/pages/lista-hogares/lista-hogares'),
      },
      {
        path: 'hogares/:hogarId',
        canActivate: [hogarGuard],
        children: [
          { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
          {
            path: 'movimientos',
            loadComponent: () => import('./features/movimientos/pages/movimientos/movimientos'),
          },
          {
            path: 'categorias',
            loadComponent: () => import('./features/categorias/pages/categorias/categorias'),
          },
          // Módulo 81
          {
            path: 'dashboard',
            loadComponent: () => import('./features/dashboard/pages/dashboard/dashboard'),
          },
          // una feature con varias rutas trae las suyas (<feature>.routes.ts)
          { path: 'tickets', loadChildren: () => import('./features/tickets/tickets.routes') },
          {
            path: 'importaciones',
            loadChildren: () => import('./features/importaciones/importaciones.routes'),
          },
          {
            path: 'presupuestos',
            loadComponent: () => import('./features/presupuestos/pages/presupuestos/presupuestos'),
          },
          {
            path: 'informes',
            loadComponent: () => import('./features/informes/pages/informes/informes'),
          },
        ],
      },
      {
        path: 'notificaciones',
        loadComponent: () =>
          import('./features/notificaciones/pages/notificaciones/notificaciones'),
      },
      // Backoffice (módulos 79 y 81): solo el personal; el código ni se descarga para los demás
      {
        path: 'soporte',
        canMatch: [esPersonal],
        loadChildren: () => import('./features/soporte/soporte.routes'),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
