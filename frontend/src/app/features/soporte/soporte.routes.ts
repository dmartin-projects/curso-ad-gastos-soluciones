import { Routes } from '@angular/router';

export default [
  {
    path: '',
    loadComponent: () => import('./pages/soporte/soporte'),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'panel' },
      { path: 'panel', loadComponent: () => import('./pages/panel/panel') },
      { path: 'hogares', loadComponent: () => import('./pages/hogares-soporte/hogares-soporte') },
      {
        path: 'hogares/:hogarId',
        loadComponent: () => import('./pages/hogar-soporte/hogar-soporte'),
      },
      {
        path: 'usuarios',
        loadComponent: () => import('./pages/usuarios-soporte/usuarios-soporte'),
      },
      { path: 'auditoria', loadComponent: () => import('./pages/auditoria/auditoria') },
      { path: 'tareas', loadComponent: () => import('./pages/tareas/tareas') },
    ],
  },
] satisfies Routes;
