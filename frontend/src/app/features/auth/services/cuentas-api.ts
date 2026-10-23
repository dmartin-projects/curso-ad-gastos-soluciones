import { HttpClient, HttpContext } from '@angular/common/http';
import { inject, Service } from '@angular/core';

import { Detalle, NuevaPassword, RegistroNuevo } from '../../../core/api/tipos';
import { SIN_AUTH, SIN_AVISO_ERROR } from '../../../core/http/contexto';

/** Aún no hay sesión: sin JWT. Y sin aviso global: cada pantalla enseña sus errores (también el 429). */
const PUBLICA = () => ({
  context: new HttpContext().set(SIN_AUTH, true).set(SIN_AVISO_ERROR, true),
});

/**
 * Crear la cuenta y recuperar la contraseña (API del módulo 71). Los dos van en dos pasos: se pide un enlace
 * por email (la respuesta es la misma exista o no la cuenta) y, desde el enlace (uid + token), se elige la contraseña.
 */
@Service()
export class CuentasApi {
  private readonly http = inject(HttpClient);

  registrar(datos: RegistroNuevo) {
    return this.http.post<Detalle>('/api/v1/auth/registro/', datos, PUBLICA());
  }

  completarRegistro(datos: NuevaPassword) {
    return this.http.post<void>('/api/v1/auth/completar-registro/', datos, PUBLICA());
  }

  recuperar(email: string) {
    return this.http.post<Detalle>('/api/v1/auth/recuperar-password/', { email }, PUBLICA());
  }

  confirmarRecuperacion(datos: NuevaPassword) {
    return this.http.post<void>('/api/v1/auth/recuperar-password/confirmar/', datos, PUBLICA());
  }
}
