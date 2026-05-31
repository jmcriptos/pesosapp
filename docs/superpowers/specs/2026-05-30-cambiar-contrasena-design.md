# Diseño: Cambiar mi contraseña (autoservicio)

**Fecha:** 2026-05-30
**Estado:** Aprobado (pendiente revisión final del usuario)

## Objetivo

Permitir que un usuario autenticado cambie su propia contraseña desde la app,
sin depender de la consola de Heroku. Cierra el gap detectado en la revisión de
seguridad: hoy no existe ninguna pantalla para rotar contraseñas.

## Alcance

- **Incluido:** autoservicio — el usuario logueado cambia su propia clave.
- **Excluido (YAGNI):** reset por super_admin de otros usuarios; recuperación
  por email ("olvidé mi contraseña"); política de expiración/historial de
  contraseñas. Pueden abordarse después en specs separados.

## Comportamiento

### Ruta
- `GET/POST /mi-cuenta/cambiar-contrasena`, decorada con `@login_required`.
- **Solo para usuarios `Vendedor`.** Si `current_user` no es `Vendedor` (usuario
  legacy `DefaultUser`, cuya clave vive en variable de entorno), se hace `flash`
  de "Esta función no está disponible para el usuario del sistema" y se redirige
  al dashboard. No aplica para ese usuario.

### Formulario (HTML plano, patrón existente)
Tres campos + token CSRF (`csrf_token()` como el resto de la app):
- `actual` — contraseña actual
- `nueva` — contraseña nueva
- `confirmar` — repetir la nueva

### Validación (backend, en orden; al fallar: `flash` de error y re-render sin guardar)
1. La contraseña `actual` debe ser correcta → `current_user.check_password(actual)`.
2. `nueva` == `confirmar`.
3. `len(nueva) >= 8`.
4. `nueva` != `actual`.

### Éxito
1. `current_user.set_password(nueva)` + `db.session.commit()`.
2. `app.logger.info(...)` registrando que el usuario X cambió su contraseña
   (NUNCA se registra la contraseña).
3. **Forzar re-login:** `logout_user()`.
4. `flash('Contraseña actualizada. Inicia sesión nuevamente.', 'success')`.
5. `redirect(url_for('login'))`.

## Componentes

| Componente | Archivo | Responsabilidad |
|-----------|---------|-----------------|
| Ruta `cambiar_password` | `app.py` | Validar y aplicar el cambio |
| Template | `templates/cambiar_password.html` | Formulario, extiende `base.html`, estilos `mobile-form-*` |
| Enlace navegación | `templates/base.html` | "Cambiar contraseña" en dropdown de usuario (~línea 436) y en el drawer móvil, junto a "Cerrar sesión" |

## Errores y casos borde
- Campos vacíos → mensaje de validación, sin guardar.
- Usuario legacy `DefaultUser` → función no disponible (redirige).
- No autenticado → `@login_required` redirige a login.
- Tras cambio exitoso, la sesión queda invalidada (logout) → el usuario debe
  iniciar sesión con la clave nueva.

## Pruebas (`tests/test_cambiar_password.py`)
- Contraseña actual incorrecta → 200/re-render, sin cambio en DB.
- `nueva` != `confirmar` → sin cambio.
- `nueva` con menos de 8 caracteres → sin cambio.
- `nueva` igual a la actual → sin cambio.
- Caso exitoso → `check_password(nueva)` True, `check_password(actual)` False;
  redirige a login; la sesión queda cerrada (un request posterior a una ruta
  protegida redirige a login).
- Acceso sin autenticación → redirige a login.

## Notas / decisiones
- **Mínimo 8 caracteres** (decisión del usuario).
- **Forzar re-login** tras el cambio (decisión del usuario) — invalida la sesión
  actual; sesiones "remember me" en otros dispositivos seguirán válidas hasta su
  expiración (Flask-Login no las revoca con el cambio de hash; queda fuera de
  alcance).
- Se mantiene el estilo del proyecto: ruta en `app.py`, form HTML + CSRF global,
  validación en el handler (no Flask-WTF Forms).
