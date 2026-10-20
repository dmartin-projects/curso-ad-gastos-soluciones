/**
 * Tipos de la API, generados a partir del esquema OpenAPI del backend (módulo 38):
 *   npx openapi-typescript ../backend/schema.yml -o src/app/core/api/esquema.ts
 * Aquí solo se les da un nombre corto. Si el backend cambia un campo, `ng build` falla donde se use.
 */
import type { components } from './esquema';

type S = components['schemas'];

export type Usuario = S['Usuario'];
export type Hogar = S['Hogar'];
export type HogarNuevo = S['HogarRequest'];
export type Cuenta = S['Cuenta'];
export type Categoria = S['Categoria'];
export type CategoriaNueva = S['CategoriaRequest'];
export type Movimiento = S['Movimiento'];
export type MovimientoNuevo = S['MovimientoRequest'];
export type Presupuesto = S['Presupuesto'];
export type Ticket = S['Ticket'];
export type ConfirmarTicket = S['ConfirmarTicketRequest'];
export type Importacion = S['Importacion'];
export type FilaImportacion = S['FilaImportacion'];
export type Dashboard = S['Dashboard'];
export type Informe = S['Informe'];
export type Notificacion = S['Notificacion'];

export type Rol = 'admin' | 'miembro' | 'lector';

/** Respuesta de la paginación por cursor de DRF (módulo 37). */
export interface PaginaCursor<T> {
  next: string | null;
  previous: string | null;
  results: T[];
}

/** Respuesta de la paginación numérica del proyecto (PaginacionEstandar). */
export interface Pagina<T> {
  count: number;
  total_pages: number;
  page: number;
  page_size: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// Backoffice (módulo 79)
export type ResumenSoporte = S['Resumen'];
export type TicketSoporte = S['TicketSoporte'];
export type ImportacionSoporte = S['ImportacionSoporte'];
export type HogarSoporte = S['HogarSoporte'];
export type HogarDetalleSoporte = S['HogarDetalleSoporte'];
export type UsuarioSoporte = S['UsuarioSoporte'];
export type MovimientoSoporte = S['MovimientoSoporte'];
export type RegistroAuditoria = S['Auditoria'];
export type TareaProgramada = S['TareaProgramada'];
export type ResultadoLote = S['ResultadoLote'];
