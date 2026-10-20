/** Los tipos de la API que usan los components de movimientos (que no ven core/: los reciben de aquí). */
export type { Categoria, Cuenta, Movimiento, MovimientoNuevo } from '../../../core/api/tipos';

/** Los filtros de la lista: viven en la URL (?q=…&categoria=…) y se traducen a parámetros de la API. */
export interface FiltrosMovimientos {
  q?: string;
  desde?: string; // AAAA-MM-DD
  hasta?: string;
  categoria?: number;
  tipo?: 'gasto' | 'ingreso';
  pendientes?: boolean;
}
