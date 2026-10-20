/** Cada estado de una importación, en palabras (la lista y el detalle). */
export const ESTADOS_IMPORTACION: Record<string, string> = {
  pendiente: 'En cola',
  analizando: 'Analizando…',
  vista_previa: 'Lista para revisar',
  importando: 'Importando…',
  completada: 'Completada',
  error: 'Error',
  deshecha: 'Deshecha',
};
