/** DRF devuelve `next` como URL absoluta; nos quedamos con la ruta para que pase por el proxy y los interceptores. */
export function rutaRelativa(url: string): string {
  const u = new URL(url, location.origin);
  return u.pathname + u.search;
}
