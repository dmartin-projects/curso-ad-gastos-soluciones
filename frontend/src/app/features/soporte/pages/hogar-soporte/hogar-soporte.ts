import { DatePipe } from '@angular/common';
import { Component, inject, input, numberAttribute } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { injectQuery } from '@tanstack/angular-query-experimental';
import { lastValueFrom } from 'rxjs';

import { SoporteApi } from '../../services/soporte-api';

@Component({
  selector: 'app-hogar-soporte',
  imports: [DatePipe, RouterLink, MatButtonModule, MatIconModule],
  templateUrl: './hogar-soporte.html',
})
export default class HogarSoporte {
  private readonly api = inject(SoporteApi);
  readonly hogarId = input.required({ transform: numberAttribute });
  protected readonly hogar = injectQuery(() => ({
    queryKey: ['soporte', 'hogar', this.hogarId()],
    queryFn: () => lastValueFrom(this.api.hogar(this.hogarId())),
  }));
}
