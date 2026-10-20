import { Routes } from '@angular/router';

/** /hogares/:hogarId/tickets/… */
export default [
  { path: '', loadComponent: () => import('./pages/tickets/tickets') },
  { path: ':ticketId', loadComponent: () => import('./pages/revisar-ticket/revisar-ticket') },
] satisfies Routes;
