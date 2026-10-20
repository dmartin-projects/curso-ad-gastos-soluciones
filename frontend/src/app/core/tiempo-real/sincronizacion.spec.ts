import { DestroyRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { QueryClient } from '@tanstack/angular-query-experimental';
import { Subject } from 'rxjs';

import { proveedoresDeTest } from '../../testing/proveedores';
import { NotificacionesStore } from '../notificaciones/notificaciones-store';
import { Sincronizacion } from './sincronizacion';
import { MensajeWs, TiempoReal } from './tiempo-real';

describe('Sincronizacion', () => {
  const mensajes = new Subject<MensajeWs>();
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient();
    TestBed.configureTestingModule({
      providers: [
        ...proveedoresDeTest(queryClient),
        { provide: TiempoReal, useValue: { mensajes$: mensajes } },
      ],
    });
    TestBed.inject(Sincronizacion).iniciar(TestBed.inject(DestroyRef));
  });

  it('un evento de movimientos invalida movimientos, dashboard y presupuestos de ESE hogar', () => {
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries');
    mensajes.next({ tipo: 'evento', evento: 'movimientos_cambiados', hogar: 3, datos: {} });
    expect(invalidar.mock.calls.map(([f]) => f?.queryKey)).toEqual([
      ['hogar', 3, 'movimientos'],
      ['hogar', 3, 'dashboard'],
      ['hogar', 3, 'presupuestos'],
    ]);
  });

  it('el progreso de una importación se escribe en la caché sin pedir nada', () => {
    queryClient.setQueryData(['hogar', 3, 'importaciones', 9], {
      id: 9,
      estado: 'importando',
      progreso: 10,
    });
    mensajes.next({
      tipo: 'evento',
      evento: 'importacion_progreso',
      hogar: 3,
      datos: { id: 9, progreso: 60 },
    });
    expect(queryClient.getQueryData(['hogar', 3, 'importaciones', 9])).toMatchObject({
      progreso: 60,
    });
  });

  it('las notificaciones suben el contador de la campana', () => {
    const store = TestBed.inject(NotificacionesStore);
    mensajes.next({ tipo: 'conectado', no_leidas: 2 });
    mensajes.next({
      tipo: 'notificacion',
      datos: {
        id: 1,
        tipo: 'ticket_procesado',
        titulo: 'Listo',
        mensaje: '',
        enlace: '',
        hogar: 3,
        creado: '',
      },
    });
    expect(store.noLeidas()).toBe(3);
    expect(store.recientes()[0].titulo).toBe('Listo');
  });
});
