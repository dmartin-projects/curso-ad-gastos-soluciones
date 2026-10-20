import { booleanAttribute, Component, inject, input, OnInit, signal } from '@angular/core';
import { form, FormField, FormRoot, maxLength, required } from '@angular/forms/signals';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { Router, RouterLink } from '@angular/router';

import { HogarStore } from '../../../../core/hogar/hogar-store';
import { erroresDelServidor } from '../../../../core/http/errores-formulario';

@Component({
  selector: 'app-lista-hogares',
  imports: [
    RouterLink,
    FormField,
    FormRoot,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  templateUrl: './lista-hogares.html',
})
export default class ListaHogares implements OnInit {
  protected readonly store = inject(HogarStore);
  private readonly router = inject(Router);
  protected readonly modelo = signal({ nombre: '' });

  protected readonly f = form(
    this.modelo,
    (r) => {
      required(r.nombre, { message: 'Ponle un nombre' });
      maxLength(r.nombre, 100);
    },
    {
      submission: {
        action: async (f) => {
          try {
            const hogar = await this.store.crear({ nombre: this.modelo().nombre });
            await this.router.navigate(['/hogares', hogar.id]);
            return null;
          } catch (e) {
            return erroresDelServidor(e, f);
          }
        },
      },
    },
  );

  /** ?elegir=1 (enlace "Mis hogares" del menú): mostrar la lista aunque haya un hogar al que saltar. */
  readonly elegir = input(false, { transform: booleanAttribute });

  async ngOnInit() {
    await this.store.cargar();
    if (this.elegir()) return;
    const hogares = this.store.hogares();
    const destino = this.store.ultimo() ?? (hogares.length === 1 ? hogares[0].id : null);
    if (destino) this.router.navigate(['/hogares', destino], { replaceUrl: true }); // atajo
  }
}
