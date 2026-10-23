import { Component, computed, inject, input, linkedSignal, signal } from '@angular/core';
import { form, FormField, FormRoot, minLength, required, validate } from '@angular/forms/signals';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { Avisos } from '../../../../core/http/avisos';
import { ErrorApi } from '../../../../core/http/errores';
import { erroresDelServidor } from '../../../../core/http/errores-formulario';
import { Para } from '../../interfaces/auth.models';
import { CuentasApi } from '../../services/cuentas-api';

const TEXTOS = {
  registro: {
    titulo: 'Completa tu registro',
    explicacion: 'Elige la contraseña con la que entrarás en Gastos.',
    boton: 'Activar la cuenta',
    hecho: 'Cuenta activada. Ya puedes entrar.',
    pedirOtro: '/registro',
  },
  recuperar: {
    titulo: 'Elige otra contraseña',
    explicacion: 'Será la contraseña con la que entres a partir de ahora.',
    boton: 'Cambiar la contraseña',
    hecho: 'Contraseña cambiada. Entra con la nueva.',
    pedirOtro: '/recuperar',
  },
};

/**
 * /completar-registro y /nueva-password: la página del enlace del email (?uid=…&token=…). Pide la contraseña dos
 * veces y la envía con el enlace. Completar no inicia sesión: al terminar, al login (los tokens solo los da /auth/login/).
 */
@Component({
  selector: 'app-elegir-password',
  imports: [
    FormField,
    FormRoot,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    RouterLink,
  ],
  templateUrl: './elegir-password.html',
})
export default class ElegirPassword {
  private readonly api = inject(CuentasApi);
  private readonly avisos = inject(Avisos);
  private readonly router = inject(Router);
  readonly para = input.required<Para>(); // data de la ruta (withComponentInputBinding)
  readonly uid = input<string>(); // ?uid=…&token=… del enlace del email
  readonly token = input<string>();
  protected readonly textos = computed(() => TEXTOS[this.para()]);
  /** Sin uid o token no hay nada que enviar; y la API puede decir que ya no vale (400 enlace_no_valido). */
  protected readonly enlaceNoValido = linkedSignal(() => !this.uid() || !this.token());
  protected readonly modelo = signal({ password: '', confirmacion: '' });

  protected readonly f = form(
    this.modelo,
    (r) => {
      required(r.password, { message: 'Escribe una contraseña' });
      minLength(r.password, 10, { message: 'Al menos 10 caracteres' });
      validate(r.confirmacion, ({ value, valueOf }) =>
        value() !== valueOf(r.password)
          ? { kind: 'distinta', message: 'Las dos contraseñas no coinciden' }
          : null,
      );
    },
    {
      submission: {
        action: async (f) => {
          const datos = {
            uid: this.uid()!,
            token: this.token()!,
            password: this.modelo().password,
          };
          try {
            await firstValueFrom(
              this.para() === 'registro'
                ? this.api.completarRegistro(datos)
                : this.api.confirmarRecuperacion(datos),
            );
          } catch (e) {
            if (e instanceof ErrorApi && e.tipo === 'enlace_no_valido') {
              this.enlaceNoValido.set(true);
              return null;
            }
            // una contraseña que no pasa los validators de Django vuelve en errors.password: a su campo
            return erroresDelServidor(e, f);
          }
          this.avisos.exito(this.textos().hecho);
          await this.router.navigateByUrl('/login', { replaceUrl: true }); // "atrás" no vuelve al enlace gastado
          return null;
        },
      },
    },
  );
}
