# Administración completa de usuarios (#1 de la serie de gestión de usuarios)

**Fecha:** 2026-05-31
**Estado:** Aprobado — listo para plan de implementación
**Serie:** Mejora de registro/administración de usuarios. Este es el sub-proyecto
**#1 (base)**. Le siguen: #2 permisos por rol configurables, #3 onboarding y
seguridad, #4 auditoría/trazabilidad. Cada uno con su propio spec/plan.

## Objetivo

Completar y arreglar la administración de usuarios en `/admin/vendedores` para que
el `super_admin` pueda gestionar el ciclo de vida de los usuarios: **editar datos,
cambiar rol, activar/desactivar y restablecer contraseña**, con contraseñas
temporales de cambio obligatorio. Hoy solo se puede crear un usuario y cambiarle el
territorio; editar y el botón de activar/desactivar están rotos o ausentes.

Modelo de acceso acordado: **basado en rol**. "Dar acceso a una persona" = asignarle
un rol (`super_admin` / `supervisor` / `vendedor`). *Qué puede hacer cada rol* se
configura en el sub-proyecto **#2** (matriz de permisos en base). Este #1 solo asigna
el rol; no cambia el motor de permisos (`tiene_permiso`).

## Estado actual (contexto)

- `Vendedor` (user) en `app.py:263`: id, username (único), email (único),
  password_hash, nombre_completo, telefono, rol_id, territorio_id, supervisor_id,
  activo, ultimo_login, fecha_ingreso, fecha_creacion. Métodos `set_password`,
  `check_password`. Hereda `UserMixin`.
- Roles existentes (seed): `super_admin`, `vendedor`. **`supervisor` está en la
  matriz de permisos pero NO existe como registro** → hay que crearlo.
- Rutas actuales: `gestionar_vendedores` (GET `/admin/vendedores`, `app.py:3118`),
  `crear_vendedor` (GET/POST `/admin/vendedores/nuevo`, `app.py:3134`),
  `actualizar_territorio_vendedor` (POST `/admin/vendedores/<id>/territorio`).
- Plantilla `templates/admin/vendedores.html`: el botón activar/desactivar hace
  `fetch('/admin/vendedores/<id>/toggle', POST)` (línea ~242) pero **esa ruta no
  existe** → roto. El botón "Editar" muestra un alert "en desarrollo".
- `cambiar_password` (`app.py:514`): cambio propio con contraseña actual; exige
  ≥8 chars; al cambiar hace `logout_user()` y obliga a reloguear.

## Cambios

### A. Modelo (`app.py`)
- Agregar `Vendedor.debe_cambiar_password = db.Column(db.Boolean, nullable=False, default=False)`.
- Crear el rol `supervisor` (seed idempotente: insertar si no existe, con
  `nivel_jerarquia` entre vendedor y super_admin, p. ej. 5).

### B. Rutas nuevas en `app.py` (todas `@login_required` + `@requiere_rol(['super_admin'])`)

**B1. Editar usuario** — `POST /admin/vendedores/<int:v_id>/editar`
- Campos editables: `nombre_completo`, `email`, `telefono`, `rol_id`, `territorio_id`.
- `username` NO es editable (es el identificador de login).
- Validaciones: nombre y email obligatorios; email único excepto el propio usuario;
  `rol_id` debe existir; `territorio_id` opcional y debe existir si se envía.
- **Guard "último super_admin"**: si el usuario editado es el único `super_admin`
  activo y se intenta cambiarle el rol a otro, se rechaza con mensaje.
- Redirige a `gestionar_vendedores` con flash.

**B2. Activar/Desactivar** — `POST /admin/vendedores/<int:v_id>/toggle`
- Invierte `activo`. (Arregla el botón roto del template.)
- **Guards**: no permitir desactivarse a sí mismo (`current_user.id == v_id`); no
  permitir desactivar al único `super_admin` activo.
- Redirige a `gestionar_vendedores` con flash. (Se ajusta el template para usar un
  POST con CSRF — formulario o fetch con token — en vez del fetch actual sin token.)

**B3. Restablecer contraseña** — `POST /admin/vendedores/<int:v_id>/reset-password`
- El admin puede escribir una contraseña temporal o **dejar el campo en blanco**;
  si va en blanco, el sistema **genera** una temporal legible (p. ej. 10 caracteres
  con `secrets`). Mínimo 8 chars si la escribe.
- Aplica `set_password(temp)` y `debe_cambiar_password = True`.
- Muestra la temporal **una sola vez** en un flash para que el admin la comunique.
- Redirige a `gestionar_vendedores`.

### C. Cambio de contraseña obligatorio
- Nuevo `@app.before_request` `forzar_cambio_password`: si `current_user` es
  `Vendedor` autenticado con `debe_cambiar_password=True` y el endpoint solicitado
  NO está en la lista permitida (`cambiar_password`, `logout`, `static`, `login`),
  redirige a `cambiar_password` con un mensaje ("Debes establecer una nueva
  contraseña para continuar").
- En `cambiar_password`, tras cambiarla con éxito, poner `debe_cambiar_password=False`
  (antes del `logout_user()` existente / commit).
- `crear_vendedor`: los usuarios nuevos nacen con `debe_cambiar_password=True`, de
  modo que cambian la contraseña inicial puesta por el admin en su primer ingreso.

### D. UI (`templates/admin/vendedores.html`)
- **Editar** (formulario colapsable por tarjeta): nombre, email, teléfono, **rol**
  (select con super_admin/supervisor/vendedor) y territorio (select) → POST a B1.
- **Activar/Desactivar**: formulario POST con CSRF a B2 (reemplaza el fetch roto).
- **Restablecer contraseña**: formulario con campo opcional + botón "generar"
  (rellena un valor aleatorio del lado cliente) → POST a B3; la temporal resultante
  se muestra en el flash.
- Indicadores por tarjeta: rol, último acceso (ya existe) y un badge
  "debe cambiar contraseña" si el flag está activo.
- El `gestionar_vendedores` debe pasar al template la lista de roles y territorios
  para los selects.

### E. Base de datos / despliegue
- Migración (local **y Heroku** vía `heroku pg:psql`):
  `ALTER TABLE vendedor ADD COLUMN debe_cambiar_password BOOLEAN NOT NULL DEFAULT FALSE;`
- Insertar el rol `supervisor` si no existe (local y Heroku):
  `INSERT INTO rol (nombre, descripcion, nivel_jerarquia, activo, fecha_creacion)
   SELECT 'supervisor', 'Supervisor', 5, true, now() WHERE NOT EXISTS
   (SELECT 1 FROM rol WHERE nombre='supervisor');`
- Reiniciar dyno.

## Pruebas (`tests/test_admin_usuarios.py`)
- Editar: super_admin cambia rol/email de un usuario; email duplicado rechazado.
- Toggle: activa/desactiva; **no** puede auto-desactivarse; **no** puede desactivar
  al último super_admin activo.
- Reset password: setea temporal + `debe_cambiar_password=True`; con campo en blanco
  genera una; el usuario es forzado a `cambiar_password` en el siguiente request y al
  cambiarla se limpia el flag.
- Usuario nuevo creado por admin nace con `debe_cambiar_password=True`.
- No-admin (vendedor) recibe 302/403 en todas las rutas nuevas.
- Guard de "último super_admin" también al editar rol.

## No-alcance (va en otros sub-proyectos)
- **#2**: matriz de permisos por rol configurable en base (cambiar `tiene_permiso` a
  leer de `RolPermiso`), restricciones de registros HACCP. Este #1 NO toca el motor
  de permisos ni agrega/edita lo que cada rol puede hacer.
- **#3**: invitación/reset por email, política de contraseñas avanzada, bloqueo por
  intentos, quitar el backdoor legacy, 2FA.
- **#4**: auditoría/trazabilidad de acciones.
- Editar `username`, borrar usuarios (se usa activar/desactivar en lugar de borrar).
