/*
 * Service worker de la app = el de Angular (ngsw-worker.js) + "compartir con Gastos" (módulo 81).
 *
 * El manifest declara un share_target: al compartir una foto desde la galería del móvil, el sistema
 * hace un POST multipart a /compartir. ngsw no sabe qué hacer con eso, así que lo atendemos aquí:
 * guardamos el archivo en la Cache Storage y redirigimos (303) a la página /compartir de Angular,
 * que lo recoge. Este listener se registra ANTES de importar ngsw: es el primero en verlo.
 */
const CACHE = 'gastos-compartido';
const CLAVE = '/compartido/ticket';

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'POST' || url.pathname !== '/compartir') return;
  event.respondWith(
    (async () => {
      const datos = await event.request.formData();
      const archivo = datos.get('ticket');
      if (archivo instanceof File) {
        const cache = await caches.open(CACHE);
        await cache.put(
          CLAVE,
          new Response(archivo, {
            headers: { 'Content-Type': archivo.type, 'X-Nombre': encodeURIComponent(archivo.name) },
          }),
        );
      }
      return Response.redirect('/compartir', 303); // 303: el navegador sigue con un GET
    })(),
  );
  event.stopImmediatePropagation(); // ngsw también respondería a la petición: que no la vea
});

importScripts('./ngsw-worker.js');
