import { Component, computed, inject, input, signal } from '@angular/core';
import { email, form, FormField, FormRoot, required } from '@angular/forms/signals';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ErrorApi } from '../../../../core/http/errores';
import { erroresDelServidor } from '../../../../core/http/errores-formulario';
import { Para } from '../../interfaces/auth.models';
import { CuentasApi } from '../../services/cuentas-api';

const TEXTOS = {
  registro: {
    titulo: 'Crear una cuenta',
    explicacion: 'Escribe tu email. Te enviaremos un enlace para elegir tu contraseña.',
    boton: 'Crear cuenta',
  },
  recuperar: {
    titulo: 'Recuperar la contraseña',
    explicacion:
      'Escribe el email de tu cuenta. Te enviaremos un enlace para elegir otra contraseña.',
    boton: 'Enviar el enlace',
  },
};

/**
 * /registro y /recuperar: solo el email. La contraseña se elige desde el enlace del correo (ElegirPassword):
 * así la elige quien controla el buzón. La API contesta lo mismo exista o no la cuenta, y eso es lo que se enseña.
 */
@Component({
  selector: 'app-pedir-enlace',
  imports: [
    FormField,
    FormRoot,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    RouterLink,
  ],
  templateUrl: './pedir-enlace.html',
})
export default class PedirEnlace {
  private readonly api = inject(CuentasApi);
  readonly para = input.required<Para>(); // data de la ruta (withComponentInputBinding)
  protected readonly textos = computed(() => TEXTOS[this.para()]);
  protected readonly enviado = signal<string | null>(null); // el "detail" de la respuesta
  protected readonly modelo = signal({ email: '' });

  protected readonly f = form(
    this.modelo,
    (r) => {
      required(r.email, { message: 'Escribe tu email' });
      email(r.email, { message: 'No parece un email' });
    },
    {
      submission: {
        action: async (f) => {
          const correo = this.modelo().email;
          try {
            const respuesta = await firstValueFrom(
              this.para() === 'registro'
                ? this.api.registrar({ email: correo })
                : this.api.recuperar(correo),
            );
            this.enviado.set(respuesta.detail);
            return null;
          } catch (e) {
            if (e instanceof ErrorApi && e.status === 429)
              return [
                {
                  kind: 'servidor',
                  message: 'Demasiadas solicitudes. Espera un rato y vuelve a probar.',
                },
              ];
            return erroresDelServidor(e, f);
          }
        },
      },
    },
  );
}
