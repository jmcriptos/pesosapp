# Eliminar tareas y registros de limpieza

**Fecha:** 2026-06-04
**Objetivo:** Permitir borrar tareas del catálogo de limpieza (`AreaLimpieza`) y registros
firmados del historial (`RegistroLimpieza`), preservando la evidencia de auditoría HACCP
cuando corresponde.

## 1. Contexto

La administración de **Tareas de limpieza** (`/registros/limpieza/areas`) hoy permite crear,
editar y activar/desactivar (toggle `activa`) áreas/equipos, pero no borrarlas. Tras el seed
del catálogo oficial quedaron duplicados sin uso que conviene poder eliminar. Además se
necesita poder corregir errores de captura borrando registros del historial.

Modelos relevantes (en `app.py`):
- `AreaLimpieza`: definición de la tarea (equipo/espacio). `activa` (bool) ya da el toggle.
- `RegistroLimpieza`: registro firmado de una limpieza ejecutada. `area_id` es FK **NOT NULL**
  a `area_limpieza.id`.

## 2. Decisiones de alcance (acordadas)

- **Tarea del catálogo sin historial** → borrado real (hard delete).
- **Tarea del catálogo con historial** → no se borra; solo desactivar (preserva evidencia).
- **Registro del historial** → borrado real con confirmación, restringido a admins
  (`registros:editar`), con traza en el log de auditoría.
- Sin borrado en cascada del historial. Sin papelera/undo nuevo (el toggle ya existe).

## 3. Borrar tarea del catálogo (`AreaLimpieza`)

- **Ruta:** `POST /registros/limpieza/areas/<int:area_id>/eliminar`,
  `@login_required` + `@requiere_permiso_recurso('registros', 'editar')`.
- **Lógica:**
  - `n = RegistroLimpieza.query.filter_by(area_id=area_id).count()`.
  - Si `n > 0` → `flash('La tarea «{nombre}» tiene {n} registro(s) en el historial; no se '
    'puede borrar. Desactívala en su lugar.', 'danger')` y redirect a `areas_limpieza_list`.
    **No** se borra.
  - Si `n == 0` → `db.session.delete(area)`, commit, `_audit('config', 'Eliminó tarea de '
    'limpieza', nombre)`, `flash('Tarea eliminada.', 'success')`, redirect a `areas_limpieza_list`.
  - `area` se obtiene con `get_or_404`.
- **UI** (`templates/registros/areas_limpieza.html`): por fila, un botón papelera (estilo
  danger) en un `<form method="POST">` con `csrf_token` y
  `onsubmit="return confirm('¿Eliminar la tarea «{{ a.nombre }}»? No se puede deshacer.')"`.
  Se ubica junto a los controles de toggle/editar existentes. El toggle se mantiene.

## 4. Borrar registro del historial (`RegistroLimpieza`)

- **Ruta:** `POST /registros/limpieza/registro/<int:registro_id>/eliminar`,
  `@login_required` + `@requiere_permiso_recurso('registros', 'editar')`.
- **Lógica:**
  - `registro = RegistroLimpieza.query.get_or_404(registro_id)`.
  - Capturar `nombre = registro.area.nombre if registro.area else '—'` y
    `cuando = _fmt_local(registro.registrado_en)` antes de borrar.
  - `db.session.delete(registro)`, commit,
    `_audit('clean', 'Eliminó registro de limpieza', f'{nombre} · {cuando}')`,
    `flash('Registro eliminado.', 'success')`.
  - Redirect a `request.referrer or url_for('limpieza_historial')` (conserva filtros).
- **UI** (`templates/registros/limpieza_historial.html`): por fila, **solo cuando
  `puede_verificar`**, un botón papelera dentro de la celda de Estado (a la derecha del
  chip), en un `<form method="POST">` con `csrf_token` y
  `onsubmit="return confirm('¿Eliminar este registro de limpieza? No se puede deshacer.')"`.
  No se añade columna nueva: se mantiene la grilla de 6 columnas.

## 5. Seguridad / auditoría

- Ambas rutas requieren permiso `registros:editar` (el usuario legacy/admin pasa por el
  bypass de `requiere_permiso_recurso`).
- CSRF: los forms incluyen `{{ csrf_token() }}` como el resto de la app.
- Toda eliminación se registra en `EventoAuditoria` vía `_audit`.

## 6. Tests (`tests/test_registro_limpieza.py`)

- `test_area_eliminar_sin_registros`: admin borra una tarea sin registros → desaparece.
- `test_area_eliminar_con_registros_bloqueado`: tarea con un `RegistroLimpieza` → no se borra
  (sigue existiendo) y responde con redirect.
- `test_area_eliminar_no_admin_bloqueado`: `vend` (rol sin `editar`) → 302/403 y la tarea sigue.
- `test_registro_historial_eliminar_admin`: admin borra un registro → `count() == 0`.
- `test_registro_historial_eliminar_no_admin_bloqueado`: `vend` → 302/403 y el registro sigue.

## 7. Fuera de alcance

- Borrado en cascada (tarea + su historial).
- Papelera / deshacer / nuevo borrado suave (el toggle `activa` ya cubre desactivar).
- Borrado masivo / por lote.
