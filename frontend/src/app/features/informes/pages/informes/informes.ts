import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { injectQuery } from '@tanstack/angular-query-experimental';
import { firstValueFrom, lastValueFrom } from 'rxjs';

import { Informe } from '../../../../core/api/tipos';
import { HogarStore } from '../../../../core/hogar/hogar-store';
import { Avisos } from '../../../../core/http/avisos';
import { guardarArchivo } from '../../../../shared/utils/descargar';
import { InformesApi } from '../../services/informes-api';

@Component({
  selector: 'app-informes',
  imports: [DatePipe, MatButtonModule, MatIconModule, MatInputModule, MatCheckboxModule],
  templateUrl: './informes.html',
})
export default class Informes {
  protected readonly store = inject(HogarStore);
  private readonly api = inject(InformesApi);
  private readonly avisos = inject(Avisos);
  private readonly hogarId = computed(() => this.store.activoId()!);
  protected readonly mes = signal('');
  protected readonly enviar = signal(false);
  protected readonly anual = signal(false);

  /** Se refresca solo cuando llega la notificación "informe_listo" (invalida ['hogar', h, …]). */
  protected readonly informes = injectQuery(() => ({
    queryKey: ['hogar', this.hogarId(), 'informes'],
    queryFn: () => lastValueFrom(this.api.listar(this.hogarId())),
  }));

  protected async generar() {
    const tipo = this.anual() ? 'anual' : 'mensual';
    await firstValueFrom(
      this.api.generar(this.hogarId(), { mes: this.mes(), enviar: this.enviar(), tipo }),
    );
    this.avisos.exito('Generando el informe; te avisaremos cuando esté listo');
  }

  protected async descargar(i: Informe) {
    guardarArchivo(await firstValueFrom(this.api.pdf(this.hogarId(), i.periodo)));
  }
}
