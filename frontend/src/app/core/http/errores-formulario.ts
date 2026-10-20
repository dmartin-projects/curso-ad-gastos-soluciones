import { FieldTree, ValidationError } from '@angular/forms/signals';

import { ErrorApi } from './errores';

/** {"importe": [...], "lineas.1.precio": [...]} de la API → errores de Signal Forms en cada campo (módulo 53). */
export function erroresDelServidor(
  e: unknown,
  raiz: FieldTree<unknown>,
): ValidationError.WithOptionalFieldTree[] {
  if (!(e instanceof ErrorApi) || e.tipo !== 'validacion') {
    return [
      { kind: 'servidor', message: e instanceof ErrorApi ? e.titulo : 'No se pudo guardar.' },
    ];
  }
  return Object.entries(e.errores).flatMap(([ruta, mensajes]) => {
    const campo = ruta === 'non_field_errors' ? undefined : buscarCampo(raiz, ruta.split('.'));
    return mensajes.map((message) => ({ kind: 'servidor', message, fieldTree: campo ?? raiz }));
  });
}

function buscarCampo(raiz: FieldTree<unknown>, partes: string[]): FieldTree<unknown> | undefined {
  let actual: unknown = raiz;
  for (const parte of partes) {
    actual = (actual as Record<string, unknown> | undefined)?.[parte];
    if (actual === undefined) return undefined;
  }
  return actual as FieldTree<unknown>;
}
