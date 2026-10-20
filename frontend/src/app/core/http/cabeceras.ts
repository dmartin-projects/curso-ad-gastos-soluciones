import { HttpInterceptorFn } from '@angular/common/http';
import { inject, LOCALE_ID } from '@angular/core';

/** Idioma y zona del navegador en cada petición a nuestra API (módulos 28 y 30). */
export const cabecerasInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith('/api/')) return next(req);
  return next(
    req.clone({
      setHeaders: {
        'Accept-Language': inject(LOCALE_ID),
        'X-Request-ID': crypto.randomUUID(),
      },
    }),
  );
};
