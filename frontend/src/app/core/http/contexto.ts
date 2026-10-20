import { HttpContextToken } from '@angular/common/http';

/** La petición no lleva el JWT (login, refresh, logout). */
export const SIN_AUTH = new HttpContextToken<boolean>(() => false);

/** La pantalla trata el error ella misma: sin aviso global. */
export const SIN_AVISO_ERROR = new HttpContextToken<boolean>(() => false);
