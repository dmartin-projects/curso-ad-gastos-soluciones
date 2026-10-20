import { Component, inject, OnInit, signal } from '@angular/core';
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

  async ngOnInit() {
    await this.store.cargar();
    if (this.store.hogares().length === 1)
      this.router.navigate(['/hogares', this.store.hogares()[0].id]); // atajo
  }
}
