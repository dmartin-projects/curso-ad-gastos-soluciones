/** Un archivo que se descarga (un PDF, un CSV…): el contenido y con qué nombre guardarlo. */
export interface Archivo {
  blob: Blob;
  nombre: string;
}
