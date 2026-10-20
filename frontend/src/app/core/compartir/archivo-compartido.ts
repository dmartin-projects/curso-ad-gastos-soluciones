import { Service, signal } from '@angular/core';

const CACHE = 'gastos-compartido';
const CLAVE = '/compartido/ticket';

/**
 * El archivo que llega por "compartir" (share_target, módulo 81). Lo deja el service worker en la
 * Cache Storage; aquí se recoge UNA vez y se guarda en memoria hasta que la pantalla de tickets lo toma.
 */
@Service()
export class ArchivoCompartido {
  private readonly pendiente = signal<File | null>(null);

  /** Saca el archivo de la caché (y lo borra de allí): un segundo intento devuelve null. */
  async recoger(): Promise<File | null> {
    if (!('caches' in globalThis)) return null;
    const cache = await caches.open(CACHE);
    const respuesta = await cache.match(CLAVE);
    if (!respuesta) return null;
    await cache.delete(CLAVE);
    const nombre = decodeURIComponent(respuesta.headers.get('X-Nombre') ?? 'ticket');
    const archivo = new File([await respuesta.blob()], nombre, {
      type: respuesta.headers.get('Content-Type') ?? '',
    });
    this.pendiente.set(archivo);
    return archivo;
  }

  /** Para la pantalla de tickets: lo entrega y lo olvida. */
  tomar(): File | null {
    const archivo = this.pendiente();
    this.pendiente.set(null);
    return archivo;
  }
}
