# Permisos por rol configurables (#2 de la serie de gestión de usuarios)

**Fecha:** 2026-05-31
**Estado:** Aprobado — listo para plan de implementación
**Serie:** Sub-proyecto **#2**. Depende del #1 (administración de usuarios, ya
desplegado). Le siguen: #3 onboarding/seguridad, #4 auditoría.

## Objetivo

Que el acceso de cada rol deje de estar **hardcodeado** y pase a leerse de la
base de datos, editable desde una **pantalla del super_admin** (matriz
recurso × acción). Incluye traer los **registros HACCP** al sistema de permisos
para poder restringir quién registra, configura y verifica.

## Estado actual (contexto)

- `Vendedor.tiene_permiso(permiso_nombre, tipo_acceso)` (app.py ~295–337): un
  **diccionario Python hardcodeado** por rol (`super_admin`/`supervisor`/
  `vendedor`) y recurso. Cambiarlo exige redeploy.
- Decorador `requiere_permiso_recurso(recurso, tipo_acceso)` (app.py ~2370):
  llama a `tiene_permiso`. Se usa hoy SOLO en: `pedidos` (leer/crear/editar/
  eliminar), `precios` (leer/crear/editar/eliminar), `clientes` (crear/eliminar),
  `productos` (editar/eliminar).
- `requiere_rol([...])`: 39 rutas `super_admin` + 2 `super_admin/supervisor`.
- **Tablas existentes y SIN USO** (de la migración multivendor): `Permiso`
  (id, nombre único, descripcion, categoria, recurso) y `RolPermiso`
  (id, rol_id FK, permiso_id FK, puede_leer/crear/editar/eliminar,
  unique(rol_id, permiso_id)). El #2 las **activa**.
- Registros HACCP hoy: registrar = `@login_required` (cualquiera); configurar
  cámaras/áreas/productos/documento = `@requiere_rol(['super_admin'])`; verificar
  = `@requiere_rol(['super_admin','supervisor'])`; consultar/PDF/hub = `@login_required`.

## Diseño

### A. Recursos configurables
La matriz controla **5 recursos**: `productos`, `clientes`, `pedidos`, `precios`,
`registros`. Cada uno con acciones `leer`/`crear`/`editar`/`eliminar`.
`facturacion`, `importaciones`, `reportes` y gestión de usuarios quedan
**fuera** (siguen como `super_admin` por rol fijo).

### B. `tiene_permiso` lee de la base
Nueva lógica:
1. Si `not self.activo` → `False`.
2. Si `self.rol.nombre == 'super_admin'` → `True` (**bypass**: el super_admin
   siempre tiene todo; su fila no es editable → evita auto-bloqueo).
3. Buscar `RolPermiso` del rol del usuario para ese recurso (join con `Permiso`
   por `recurso`). Si existe, devolver el booleano de la acción
   (`puede_leer/crear/editar/eliminar`).
4. **Fallback**: si no hay fila (no sembrado), usar el diccionario actual
   extraído a un helper `_permiso_default(rol_nombre, recurso, accion)` — así
   nunca se queda sin respuesta por falta de datos. Ese diccionario incluye
   también `registros` con los mismos defaults de la tabla de siembra (vendedor:
   leer/crear; supervisor: leer/crear/editar), para no regresar accesos si la
   siembra no corrió.

### C. Siembra (idempotente, local y Heroku)
- Una fila `Permiso` por recurso (nombre = recurso, recurso = recurso,
  categoria = 'recurso').
- Filas `RolPermiso` para `supervisor` y `vendedor` (y `super_admin`, aunque se
  bypassa) con estos defaults (= comportamiento actual):

| Recurso | vendedor | supervisor |
|---|---|---|
| productos | leer | leer |
| clientes | leer, editar | leer, editar |
| pedidos | leer, crear, editar | leer, crear, editar |
| precios | leer | leer |
| registros | leer, crear | leer, crear, editar |

### D. Registros HACCP → al sistema de permisos
Convertir las rutas de registros de `requiere_rol`/`login_required` a
`requiere_permiso_recurso('registros', <accion>)`:
- **leer**: `temperaturas_historial`, `temperaturas_export`, `limpieza_historial`,
  `limpieza_export`, `productos_limpieza_index`, `registros_index` (hub).
- **crear**: `temperaturas_index`, `temperatura_registrar`, `limpieza_index`,
  `limpieza_registrar`.
- **editar**: `camaras_list` + `camara_nueva/editar/toggle`, `registro_config`,
  `areas_limpieza_list` + `area_limpieza_nueva/editar/toggle`,
  `producto_limpieza_nuevo/editar/toggle`, `temperatura_revisar`,
  `limpieza_revisar`, `limpieza_config`.

Con los defaults sembrados no hay regresión: los 3 roles conservan leer+crear de
registros; configurar/verificar queda en super_admin (+ supervisor, que con el
modelo CRUD gana también configurar — simplificación aprobada).

### E. Pantalla `/admin/roles-permisos` (super_admin)
- GET: matriz. Filas = roles configurables (`supervisor`, `vendedor`); columnas =
  los 5 recursos × 4 acciones, como checkboxes reflejando `RolPermiso`. La fila de
  `super_admin` se muestra **bloqueada con todo activo** (informativo).
- POST: lee los checkboxes (`perm_<rol_id>_<recurso>_<accion>`), crea/actualiza
  las filas `RolPermiso` y guarda. Enlace desde la administración de usuarios.

### F. Rendimiento
`tiene_permiso` hace una consulta por verificación (escala chica → aceptable).
No se agrega caché en este #2.

## Pruebas (`tests/test_permisos.py`)
- `tiene_permiso` lee de `RolPermiso` (sembrar fila → refleja el booleano).
- `super_admin` siempre `True` aunque no tenga filas.
- Fallback: sin filas, usa los defaults.
- Editar la matriz cambia el acceso real (POST quita `pedidos:editar` a vendedor →
  el vendedor recibe 302/403 al editar un pedido).
- Registros respetan el permiso (vendedor sin `registros:crear` → la pantalla de
  registrar redirige; con `registros:editar` puede configurar).
- No-admin no puede abrir `/admin/roles-permisos` (302/403).

## Despliegue
- Sembrar `Permiso` + `RolPermiso` en local y **Heroku** (las tablas ya existen).
- `git push` a main auto-deploy; reiniciar dyno. La siembra debe correr antes/junto
  al deploy para que las rutas convertidas tengan permisos.

## No-alcance
- No se traen facturación/importaciones/reportes a la matriz (futuro).
- No se agregan acciones granulares de registros (registrar/configurar/verificar
  separadas) — se usa el mapeo CRUD aprobado.
- No se toca el motor de roles fijos de las 39 rutas admin-only.
