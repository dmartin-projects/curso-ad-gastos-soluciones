import { HttpResponse } from '@angular/common/http';

import { Archivo } from '../../shared/interfaces/archivo';

/** La respuesta de una petición con responseType: 'blob' → el archivo, con el nombre de Content-Disposition. */
export function archivoDe(r: HttpResponse<Blob>, porDefecto: string): Archivo {
  const cabecera = r.headers.get('Content-Disposition');
  const m = cabecera?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return { blob: r.body!, nombre: m ? decodeURIComponent(m[1]) : porDefecto };
}
