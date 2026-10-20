import { provideHttpClient, withInterceptors, withXhr } from '@angular/common/http';
import { registerLocaleData } from '@angular/common';
import localeEs from '@angular/common/locales/es';
import {
  ApplicationConfig,
  DEFAULT_CURRENCY_CODE,
  inject,
  LOCALE_ID,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
  isDevMode,
} from '@angular/core';
import { MatIconRegistry } from '@angular/material/icon';
import { provideRouter, withComponentInputBinding, withInMemoryScrolling } from '@angular/router';
import { provideTanStackQuery, QueryClient } from '@tanstack/angular-query-experimental';

import { routes } from './app.routes';
import { authInterceptor } from './core/auth/auth.interceptor';
import { AuthStore } from './core/auth/auth-store';
import { cabecerasInterceptor } from './core/http/cabeceras';
import { Tema } from './core/tema/tema';
import { erroresInterceptor } from './core/http/errores';
import { provideServiceWorker } from '@angular/service-worker';

registerLocaleData(localeEs);

export const appConfig: ApplicationConfig = {
  providers: [
    provideAppInitializer(() => void inject(Tema)), // el modo guardado, antes de pintar (módulo 81)
    provideBrowserGlobalErrorListeners(),
    provideRouter(
      routes,
      withComponentInputBinding(),
      withInMemoryScrolling({ scrollPositionRestoration: 'enabled' }),
    ),
    // withXhr: el progreso de SUBIDA de los tickets solo lo da XMLHttpRequest (fetch no lo informa, módulo 51)
    // Orden: la respuesta recorre la lista al revés → auth ve el 401 antes de que errores lo convierta en ErrorApi
    provideHttpClient(
      withXhr(),
      withInterceptors([cabecerasInterceptor, erroresInterceptor, authInterceptor]),
    ),
    provideTanStackQuery(
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: true },
        },
      }),
    ),
    { provide: LOCALE_ID, useValue: 'es' },
    { provide: DEFAULT_CURRENCY_CODE, useValue: 'EUR' },
    provideAppInitializer(() => {
      inject(MatIconRegistry).setDefaultFontSetClass('material-symbols-outlined');
      return inject(AuthStore).restaurarSesion(); // F5 no cierra la sesión: la cookie de refresh la recupera
    }),
    // sw-gastos.js = ngsw-worker.js + el share_target del manifest (módulo 81)
    provideServiceWorker('sw-gastos.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
