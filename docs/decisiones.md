# Decisiones de arquitectura (ADR)

Formato: contexto → decisión → consecuencias. Una decisión no se borra: si cambia, se escribe otra que la sustituye.

## ADR-001 · Un solo modelo `Movimiento` con importe con signo

- **Estado:** aceptada (fase 2).
- **Contexto:** hay gastos e ingresos; los extractos bancarios traen ambos en una columna con signo; el dashboard suma por mes y categoría.
- **Decisión:** un único modelo `Movimiento` con `importe` `Decimal(12, 2)` negativo para gastos y positivo para ingresos. Nada de `Gasto` e `Ingreso` separados ni de un campo `tipo`.
- **Consecuencias:**
  - ✅ El saldo es `SUM(importe)`; importar un extracto no necesita convertir nada; un solo índice y un solo endpoint.
  - ✅ El *manager* da la semántica: `.gastos()` (`importe < 0`), `.ingresos()`.
  - ⚠️ En la interfaz hay que mostrar valores absolutos y elegir el signo al crear ("Gasto"/"Ingreso"), y un `CheckConstraint` impide el importe 0.

## ADR-002 · Idempotencia de las importaciones en la base de datos (`huella` única)

- **Estado:** aceptada (fase 5).
- **Contexto:** el mismo extracto se importa dos veces, o dos extractos se solapan; las tareas de Celery se pueden ejecutar dos veces (`acks_late`); dos importaciones pueden correr a la vez.
- **Decisión:** cada movimiento importado lleva `huella` = hash de cuenta + fecha + importe + concepto normalizado + número de ocurrencia ese día, con `UniqueConstraint(cuenta, huella)`, y se inserta con `bulk_create(ignore_conflicts=True)`.
- **Consecuencias:**
  - ✅ La garantía no depende del código de la aplicación ni de que no haya carreras: la da PostgreSQL.
  - ✅ Reimportar es seguro y barato; el resumen cuenta "nuevos" frente a "ya existían".
  - ⚠️ Dos movimientos legítimamente idénticos el mismo día se distinguen solo por el número de ocurrencia: si el banco cambia el orden entre extractos, puede haber un falso duplicado (aceptable; se crea a mano).

## ADR-003 · Backoffice propio en lugar del admin de Django

- **Estado:** aceptada (fase 9).
- **Contexto:** soporte necesita ver tickets atascados, reprocesar, deshacer importaciones y recategorizar. El admin de Django lo permitiría, pero expone *todos* los datos de *todos* los hogares con permisos de modelo, en otra interfaz y con otro sistema de sesión (cookies + CSRF) que el resto de la app (JWT).
- **Decisión:** una API `/backoffice/` solo para personal (`is_staff` + grupo, `manage.py personal`), que responde 404 a quien no lo es, con acciones concretas y auditadas (`RegistroAuditoria`), y sus pantallas dentro de la SPA.
- **Consecuencias:**
  - ✅ Superficie de ataque mínima (sin `/admin/` en producción), mismas reglas de autenticación, cada acción queda en la auditoría.
  - ✅ Pantallas pensadas para las tareas de soporte, no CRUD genérico.
  - ⚠️ Más código que mantener; las tareas imprevistas necesitan un *endpoint* nuevo (o `manage.py shell` en el servidor, documentado en el *runbook*).
