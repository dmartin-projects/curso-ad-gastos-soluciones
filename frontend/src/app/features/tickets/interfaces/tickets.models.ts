import { Ticket } from '../../../core/api/tipos';

/** Los tipos de la API que usan los components de tickets (que no ven core/: los reciben de aquí). */
export type { Cuenta, Ticket } from '../../../core/api/tipos';

/** Lo que pide SubirTicket a su page: subir este archivo a esta cuenta. */
export interface TicketParaSubir {
  cuenta: number;
  archivo: File;
}

/** Cómo va una subida: el porcentaje enviado y, al final, el ticket creado. */
export type EventoSubida =
  { tipo: 'progreso'; porcentaje: number } | { tipo: 'subido'; ticket: Ticket };
