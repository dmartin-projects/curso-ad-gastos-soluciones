import { Archivo } from '../interfaces/archivo';

/** Guarda en disco un archivo descargado por la API (módulo 51): un enlace temporal y un clic. */
export function guardarArchivo({ blob, nombre }: Archivo) {
  const enlace = document.createElement('a');
  enlace.href = URL.createObjectURL(blob);
  enlace.download = nombre;
  enlace.click();
  setTimeout(() => URL.revokeObjectURL(enlace.href)); // libera la memoria del blob
}
