import { HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { SIN_AUTH } from '../../../../core/http/contexto';
import { proveedoresDeTest } from '../../../../testing/proveedores';
import { Para } from '../../interfaces/auth.models';
import PedirEnlace from './pedir-enlace';

describe('PedirEnlace (/registro y /recuperar)', () => {
  let ctrl: HttpTestingController;

  async function pintar(para: Para) {
    TestBed.configureTestingModule({ providers: proveedoresDeTest() });
    ctrl = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(PedirEnlace);
    fixture.componentRef.setInput('para', para); // en la app, lo pone la ruta (data)
    await fixture.whenStable();
    return fixture;
  }

  afterEach(() => ctrl.verify());

  async function pedir(fixture: ComponentFixture<PedirEnlace>, email: string) {
    const pagina = fixture.nativeElement as HTMLElement;
    const input = pagina.querySelector('input')!;
    input.value = email;
    input.dispatchEvent(new Event('input'));
    pagina.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
  }

  /** La acción de `submission` es una promesa propia: whenStable() no la espera. Un turno del bucle de eventos, sí. */
  async function terminarEnvio(fixture: ComponentFixture<PedirEnlace>) {
    await new Promise((r) => setTimeout(r));
    await fixture.whenStable();
  }

  const texto = (fixture: ComponentFixture<PedirEnlace>) =>
    (fixture.nativeElement as HTMLElement).textContent;

  it('registro: envía solo el email, sin JWT, y enseña la respuesta de la API', async () => {
    const fixture = await pintar('registro');
    expect(texto(fixture)).toContain('Crear una cuenta');
    await pedir(fixture, 'ana@example.com');

    const peticion = ctrl.expectOne('/api/v1/auth/registro/');
    expect(peticion.request.body).toEqual({ email: 'ana@example.com' });
    expect(peticion.request.context.get(SIN_AUTH)).toBe(true);
    peticion.flush(
      { detail: 'Revisa tu email: te hemos enviado un enlace para continuar.' },
      { status: 202, statusText: 'Accepted' },
    );
    await terminarEnvio(fixture);

    const pagina = fixture.nativeElement as HTMLElement;
    expect(pagina.querySelector('mat-card-title')!.textContent).toContain('Revisa tu email');
    expect(pagina.querySelector('[role=status]')!.textContent).toContain(
      'Revisa tu email: te hemos enviado un enlace para continuar.',
    );
    expect(pagina.querySelector('form')).toBeNull();
  });

  it('recuperar: pide el enlace a recuperar-password/', async () => {
    const fixture = await pintar('recuperar');
    expect(texto(fixture)).toContain('Recuperar la contraseña');
    await pedir(fixture, 'ana@example.com');

    const peticion = ctrl.expectOne('/api/v1/auth/recuperar-password/');
    expect(peticion.request.body).toEqual({ email: 'ana@example.com' });
    peticion.flush({ detail: 'Si el email existe, te hemos enviado un enlace.' });
    await terminarEnvio(fixture);
    expect(texto(fixture)).toContain('Si el email existe, te hemos enviado un enlace.');
  });

  it('un email mal escrito no llama a la API', async () => {
    const fixture = await pintar('registro');
    await pedir(fixture, 'ana@');
    ctrl.expectNone('/api/v1/auth/registro/');
    expect(texto(fixture)).toContain('No parece un email');
  });

  it('el límite de peticiones (429) se explica en la pantalla', async () => {
    const fixture = await pintar('registro');
    await pedir(fixture, 'ana@example.com');
    ctrl
      .expectOne('/api/v1/auth/registro/')
      .flush(
        { type: 'throttled', title: 'Demasiadas peticiones.' },
        { status: 429, statusText: 'Too Many Requests' },
      );
    await terminarEnvio(fixture);
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[role=alert]')!.textContent,
    ).toContain('Demasiadas solicitudes. Espera un rato y vuelve a probar.');
    expect(texto(fixture)).not.toContain('Revisa tu email');
  });
});
