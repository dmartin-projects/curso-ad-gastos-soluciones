import { signal, WritableSignal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { By } from '@angular/platform-browser';

import { ErrorApi } from '../../../../../core/http/errores';
import { erroresDelServidor } from '../../../../../core/http/errores-formulario';
import { proveedoresDeTest } from '../../../../../testing/proveedores';
import { Cuenta } from '../../../interfaces/movimientos.models';
import { DatosFormularioMovimiento, FormularioMovimiento } from './formulario-movimiento';

describe('FormularioMovimiento', () => {
  const cerrar = vi.fn();

  /** El diálogo recibe de su page los catálogos y cómo guardar: aquí, un guardar falso. */
  async function crear(guardar: DatosFormularioMovimiento['guardar']) {
    const datos: DatosFormularioMovimiento = {
      cuentas: signal([{ id: 5, nombre: 'Común', saldo: '0' } as Cuenta]),
      categorias: signal([]),
      guardar,
    };
    TestBed.configureTestingModule({
      providers: [
        ...proveedoresDeTest(),
        { provide: MAT_DIALOG_DATA, useValue: datos },
        { provide: MatDialogRef, useValue: { close: cerrar } },
      ],
    });
    const fixture = TestBed.createComponent(FormularioMovimiento);
    await fixture.whenStable();
    return fixture;
  }

  function escribir(fixture: Awaited<ReturnType<typeof crear>>, etiqueta: string, valor: string) {
    const campo = fixture.debugElement
      .queryAll(By.css('mat-form-field'))
      .find((c) => c.nativeElement.textContent.includes(etiqueta))!
      .query(By.css('input'));
    campo.nativeElement.value = valor;
    campo.nativeElement.dispatchEvent(new Event('input'));
  }

  /** La cuenta, sin abrir el panel del mat-select: el modelo es protected, pero el test lo ve. */
  function elegirCuenta(fixture: Awaited<ReturnType<typeof crear>>, cuenta: number) {
    const formulario = fixture.componentInstance as unknown as {
      modelo: WritableSignal<{ cuenta: number | null }>;
    };
    formulario.modelo.update((m) => ({ ...m, cuenta }));
  }

  /** La acción de `submission` es una promesa propia: whenStable() no la espera. Un turno del bucle de eventos, sí. */
  async function terminarEnvio(fixture: Awaited<ReturnType<typeof crear>>) {
    await new Promise((r) => setTimeout(r));
    await fixture.whenStable();
  }

  const enviar = (fixture: Awaited<ReturnType<typeof crear>>) =>
    fixture.debugElement.query(By.css('form')).nativeElement.dispatchEvent(new Event('submit'));

  it('un gasto se guarda con importe negativo y cierra el diálogo', async () => {
    const guardar = vi.fn().mockResolvedValue(null);
    const fixture = await crear(guardar);
    escribir(fixture, 'Importe', '12.5');
    escribir(fixture, 'Concepto', 'Cine');
    elegirCuenta(fixture, 5);
    enviar(fixture);
    await terminarEnvio(fixture);

    expect(guardar).toHaveBeenCalledOnce();
    expect(guardar.mock.calls[0][0]).toMatchObject({
      importe: '-12.50',
      concepto: 'Cine',
      cuenta: 5,
    });
    expect(cerrar).toHaveBeenCalledWith(true);
  });

  it('sin importe ni concepto no intenta guardar y muestra los errores', async () => {
    const guardar = vi.fn();
    const fixture = await crear(guardar);
    enviar(fixture);
    await fixture.whenStable();
    expect(guardar).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Indica el importe');
  });

  it('los errores de validación de la API aparecen en su campo', async () => {
    cerrar.mockClear();
    // lo que hace la page si la API responde 400: erroresDelServidor() pone cada error en su campo
    const fixture = await crear(async (_cuerpo, formulario) =>
      erroresDelServidor(
        new ErrorApi(400, 'validacion', 'Datos no válidos', { concepto: ['Demasiado corto.'] }),
        formulario,
      ),
    );
    escribir(fixture, 'Importe', '3');
    escribir(fixture, 'Concepto', 'X');
    elegirCuenta(fixture, 5);
    enviar(fixture);
    await terminarEnvio(fixture);
    expect(fixture.nativeElement.textContent).toContain('Demasiado corto.');
    expect(cerrar).not.toHaveBeenCalled();
  });
});
