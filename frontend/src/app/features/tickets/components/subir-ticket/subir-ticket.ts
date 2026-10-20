import { Component, computed, input, linkedSignal, output, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';

import { Cuenta, TicketParaSubir } from '../../interfaces/tickets.models';

const TIPOS = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];
const MAXIMO = 10 * 1024 * 1024;

/**
 * Foto desde la cámara del móvil o archivo arrastrado, con barra de progreso real de la subida. Presentacional:
 * comprueba el archivo y pide a su page que lo suba (`subir`); la page le pasa el progreso y el error del servidor.
 */
@Component({
  selector: 'app-subir-ticket',
  imports: [
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    MatSelectModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  templateUrl: './subir-ticket.html',
})
export class SubirTicket {
  readonly cuentas = input.required<Cuenta[]>();
  readonly progreso = input<number | null>(null); // null: no hay subida en marcha
  readonly errorSubida = input<string | null>(null); // lo que contestó la API
  readonly subir = output<TicketParaSubir>();

  /** linkedSignal: por defecto la primera cuenta; el usuario puede cambiarla; si cambian las cuentas, se recalcula. */
  protected readonly cuenta = linkedSignal<number | null>(() => this.cuentas()[0]?.id ?? null);
  protected readonly subiendo = computed(() => this.progreso() !== null);
  private readonly errorArchivo = signal<string | null>(null);
  protected readonly error = computed(() => this.errorArchivo() ?? this.errorSubida());
  protected readonly arrastrando = signal(false);

  protected soltar(e: DragEvent) {
    e.preventDefault();
    this.arrastrando.set(false);
    this.elegir(e.dataTransfer?.files ?? null);
  }

  protected elegir(archivos: FileList | null) {
    const archivo = archivos?.[0];
    if (!archivo) return;
    if (!this.cuenta()) return this.errorArchivo.set('Elige primero la cuenta.');
    // validación en el cliente = mejor experiencia; la de verdad es la del servidor (firmas, módulo 74)
    if (!TIPOS.includes(archivo.type)) return this.errorArchivo.set('Sube una foto o un PDF.');
    if (archivo.size > MAXIMO)
      return this.errorArchivo.set('El archivo no puede superar los 10 MB.');
    this.errorArchivo.set(null);
    this.subir.emit({ cuenta: this.cuenta()!, archivo });
  }
}
