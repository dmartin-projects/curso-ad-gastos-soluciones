import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { MATERIAL_ANIMATIONS } from '@angular/material/core';
import { provideRouter } from '@angular/router';
import { provideTanStackQuery, QueryClient } from '@tanstack/angular-query-experimental';

import { authInterceptor } from '../core/auth/auth.interceptor';
import { erroresInterceptor } from '../core/http/errores';

/** Proveedores comunes de los tests: HTTP falso con los interceptores de verdad, router vacío y una caché nueva. */
export function proveedoresDeTest(
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
) {
  return [
    provideZonelessChangeDetection(),
    // sin animaciones de Material (no hace falta @angular/animations, que está obsoleto)
    { provide: MATERIAL_ANIMATIONS, useValue: { animationsDisabled: true } },
    provideRouter([]),
    provideHttpClient(withInterceptors([erroresInterceptor, authInterceptor])),
    provideHttpClientTesting(),
    provideTanStackQuery(queryClient),
  ];
}
