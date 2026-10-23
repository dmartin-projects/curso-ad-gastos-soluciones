import { HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';

import { Avisos } from '../../../../core/http/avisos';
import { proveedoresDeTest } from '../../../../testing/proveedores';
import ElegirPassword from './elegir-password';
import { Para } from '../../interfaces/auth.models';

describe('ElegirPassword (/completar-registro y /nueva-password)', () => {
  let ctrl: HttpTestingController;
  let navegar: ReturnType<typeof vi.spyOn>;
  let exito: ReturnType<typeof vi.spyOn>;

  const ENLACE = { uid: 'MQ', token: 'cz4k1a-0123456789abcdef' };

  async function pintar(para: Para, enlace: Record<string, string> = ENLACE) {
    TestBed.configureTestingModule({ providers: proveedoresDeTest() });
    ctrl = TestBed.inject(HttpTestingController);
    navegar = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    exito = vi.spyOn(TestBed.inject(Avisos), 'exito').mockImplementation(() => undefined);
    const fixture = TestBed.createComponent(ElegirPassword);
    fixture.componentRef.setInput('para', para); // la ruta (data) y la query del enlace
    for (const [nombre, valor] of Object.entries(enlace))
      fixture.componentRef.setInput(nombre, valor);
    await fixture.whenStable();
    return fixture;
  }

  afterEach(() => ctrl.verify());

  async function enviar(
    fixture: ComponentFixture<ElegirPassword>,
    password: string,
    otra = password,
  ) {
    const [nueva, repetida] = (fixture.nativeElement as HTMLElement).querySelectorAll('input');
    for (const [input, valor] of [
      [nueva, password],
      [repetida, otra],
    ] as const) {
      input.value = valor;
      input.dispatchEvent(new Event('input'));
    }
    (fixture.nativeElement as HTMLElement)
      .querySelector('form')!
      .dispatchEvent(new Event('submit'));
    await fixture.whenStable();
  }

  /** La acción de `submission` es una promesa propia: whenStable() no la espera. Un turno del bucle de eventos, sí. */
  async function terminarEnvio(fixture: ComponentFixture<ElegirPassword>) {
    await new Promise((r) => setTimeout(r));
    await fixture.whenStable();
  }

  const texto = (fixture: ComponentFixture<ElegirPassword>) =>
    (fixture.nativeElement as HTMLElement).textContent;

  it('completar el registro: envía el enlace con la contraseña y lleva al login con un aviso', async () => {
    const fixture = await pintar('registro');
    expect(texto(fixture)).toContain('Completa tu registro');
    await enviar(fixture, 'una-clave-bien-larga');

    const peticion = ctrl.expectOne('/api/v1/auth/completar-registro/');
    expect(peticion.request.body).toEqual({ ...ENLACE, password: 'una-clave-bien-larga' });
    peticion.flush(null, { status: 204, statusText: 'No Content' });
    await terminarEnvio(fixture);
    expect(exito).toHaveBeenCalledWith('Cuenta activada. Ya puedes entrar.');
    expect(navegar).toHaveBeenCalledWith('/login', { replaceUrl: true });
  });

  it('nueva contraseña: la misma pantalla confirma la recuperación', async () => {
    const fixture = await pintar('recuperar');
    expect(texto(fixture)).toContain('Elige otra contraseña');
    await enviar(fixture, 'otra-clave-bien-larga');

    const peticion = ctrl.expectOne('/api/v1/auth/recuperar-password/confirmar/');
    expect(peticion.request.body).toEqual({ ...ENLACE, password: 'otra-clave-bien-larga' });
    peticion.flush(null, { status: 204, statusText: 'No Content' });
    await terminarEnvio(fixture);
    expect(exito).toHaveBeenCalledWith('Contraseña cambiada. Entra con la nueva.');
    expect(navegar).toHaveBeenCalledWith('/login', { replaceUrl: true });
  });

  it('las dos contraseñas tienen que coincidir, y no se llama a la API', async () => {
    const fixture = await pintar('registro');
    await enviar(fixture, 'una-clave-bien-larga', 'una-clave-bien-largo');
    ctrl.expectNone('/api/v1/auth/completar-registro/');
    expect(texto(fixture)).toContain('Las dos contraseñas no coinciden');
  });

  it('los motivos de la API (errors.password) salen en el campo, y el enlace sirve para reintentar', async () => {
    const fixture = await pintar('registro');
    await enviar(fixture, 'password123');
    ctrl.expectOne('/api/v1/auth/completar-registro/').flush(
      {
        type: 'validacion',
        title: 'Datos no válidos',
        errors: { password: ['Esta contraseña es demasiado común.'] },
      },
      { status: 400, statusText: 'Bad Request' },
    );
    await terminarEnvio(fixture);
    expect(texto(fixture)).toContain('Esta contraseña es demasiado común.');
    expect(navegar).not.toHaveBeenCalled();

    await enviar(fixture, 'una-clave-bien-larga');
    ctrl
      .expectOne('/api/v1/auth/completar-registro/')
      .flush(null, { status: 204, statusText: 'No Content' });
    await terminarEnvio(fixture);
    expect(navegar).toHaveBeenCalledWith('/login', { replaceUrl: true });
  });

  it('un enlace caducado o ya usado: lo dice y ofrece pedir otro', async () => {
    const fixture = await pintar('recuperar');
    await enviar(fixture, 'una-clave-bien-larga');
    ctrl
      .expectOne('/api/v1/auth/recuperar-password/confirmar/')
      .flush(
        { type: 'enlace_no_valido', title: 'Enlace no válido o caducado.' },
        { status: 400, statusText: 'Bad Request' },
      );
    await terminarEnvio(fixture);
    const pagina = fixture.nativeElement as HTMLElement;
    expect(pagina.querySelector('[role=alert]')!.textContent).toContain(
      'Este enlace no es válido: ha caducado o ya se ha usado.',
    );
    expect(pagina.querySelector('form')).toBeNull();
    expect(pagina.querySelector('a')!.getAttribute('href')).toBe('/recuperar');
    expect(navegar).not.toHaveBeenCalled();
  });

  it('sin uid ni token no enseña el formulario', async () => {
    const fixture = await pintar('registro', {});
    const pagina = fixture.nativeElement as HTMLElement;
    expect(pagina.querySelector('form')).toBeNull();
    expect(pagina.querySelector('a')!.getAttribute('href')).toBe('/registro');
  });
});
