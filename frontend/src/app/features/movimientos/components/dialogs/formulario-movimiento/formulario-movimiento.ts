import { Component, computed, inject, Signal, signal } from '@angular/core';
import {
  FieldTree,
  form,
  FormField,
  FormRoot,
  min,
  required,
  validate,
  ValidationError,
} from '@angular/forms/signals';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';

import { SelectorCategoria } from '../../../../../shared/components/selector-categoria/selector-categoria';
import {
  Categoria,
  Cuenta,
  Movimiento,
  MovimientoNuevo,
} from '../../../interfaces/movimientos.models';

/**
 * Lo que el diálogo recibe de su page (MAT_DIALOG_DATA hace de input()): el movimiento a editar, los catálogos y
 * CÓMO guardar. El diálogo es presentacional: valida y arma el cuerpo; guardar en la API es cosa de la page.
 */
export interface DatosFormularioMovimiento {
  movimiento?: Movimiento; // editar; sin él, crear
  cuentas: Signal<Cuenta[]>;
  categorias: Signal<Categoria[]>;
  /** null si se ha guardado; si no, los errores del servidor, cada uno en su campo (o en el formulario). */
  guardar: (
    cuerpo: MovimientoNuevo,
    formulario: FieldTree<unknown>,
  ) => Promise<ValidationError.WithOptionalFieldTree[] | null>;
}

interface Modelo {
  tipo: 'gasto' | 'ingreso';
  importe: number | null; // siempre positivo en el formulario; el signo lo pone `tipo`
  fecha: string;
  concepto: string;
  cuenta: number | null;
  categoria: number | null;
  notas: string;
}

const hoy = () => new Date().toLocaleDateString('sv-SE'); // AAAA-MM-DD en la zona del navegador

@Component({
  selector: 'app-formulario-movimiento',
  imports: [
    FormField,
    FormRoot,
    MatDialogModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    SelectorCategoria,
  ],
  templateUrl: './formulario-movimiento.html',
})
export class FormularioMovimiento {
  protected readonly datos = inject<DatosFormularioMovimiento>(MAT_DIALOG_DATA);
  private readonly ref = inject<MatDialogRef<FormularioMovimiento, boolean>>(MatDialogRef);

  protected readonly modelo = signal<Modelo>(this.inicial());
  protected readonly categoriasDelTipo = computed(() =>
    this.datos.categorias().filter((c) => !!c.es_ingreso === (this.modelo().tipo === 'ingreso')),
  );

  protected readonly f = form(
    this.modelo,
    (r) => {
      required(r.importe, { message: 'Indica el importe' });
      min(r.importe, 0.01, { message: 'Debe ser mayor que cero' });
      required(r.fecha);
      validate(r.fecha, ({ value }) =>
        value() > hoy() ? { kind: 'futura', message: 'No puede ser una fecha futura' } : null,
      );
      required(r.concepto, { message: 'Escribe un concepto' });
      required(r.cuenta, { message: 'Elige la cuenta' });
    },
    {
      submission: {
        action: async (f) => {
          const m = this.modelo();
          const cuerpo = {
            fecha: m.fecha,
            importe: (m.tipo === 'gasto' ? -m.importe! : m.importe!).toFixed(2),
            concepto: m.concepto,
            cuenta: m.cuenta!,
            categoria: m.categoria,
            notas: m.notas,
          };
          const errores = await this.datos.guardar(cuerpo, f);
          if (!errores) this.ref.close(true);
          return errores;
        },
      },
    },
  );

  protected cambiarTipo(tipo: 'gasto' | 'ingreso') {
    this.modelo.update((m) => ({ ...m, tipo, categoria: null })); // las categorías de gasto e ingreso son distintas
  }

  private inicial(): Modelo {
    const m = this.datos.movimiento;
    if (!m)
      return {
        tipo: 'gasto',
        importe: null,
        fecha: hoy(),
        concepto: '',
        cuenta: null,
        categoria: null,
        notas: '',
      };
    const importe = Number(m.importe);
    return {
      tipo: importe < 0 ? 'gasto' : 'ingreso',
      importe: Math.abs(importe),
      fecha: m.fecha,
      concepto: m.concepto,
      cuenta: m.cuenta,
      categoria: m.categoria ?? null,
      notas: m.notas ?? '',
    };
  }
}
