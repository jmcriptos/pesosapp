# Diseño: Registro de temperaturas de cámaras (HACCP)

**Fecha:** 2026-05-30
**Estado:** Aprobado (pendiente revisión final del usuario)

## Contexto y objetivo

Primer sub-proyecto del grupo de registros HACCP/BPM. Driver: **exigencia
regulatoria de Curaçao** — formalidad media: cada registro lleva responsable y
fecha/hora, se conserva históricamente, y se puede **exportar a PDF** para
mostrar/entregar al inspector.

La app no tiene hoy ningún sistema de registros de inocuidad. Este sub-proyecto
crea el registro de **temperaturas de cámaras de refrigeración/congelación**.
El registro de **limpieza y desinfección** es un sub-proyecto posterior aparte.

## Alcance

- **Incluido:** administrar cámaras con rango aceptable; registrar lecturas de
  temperatura con responsable y hora; marcar y exigir acción correctiva cuando
  una lectura sale de rango; ver historial; exportar PDF por rango de fechas.
- **Excluido (YAGNI):** notificaciones/recordatorios, cadencia exigida por
  cámara, gráficas de tendencia, registro de limpieza (sub-proyecto aparte).

## Modelos (en `app.py`, patrón SQLAlchemy existente)

### `Camara`
- `id` (PK)
- `nombre` (String, requerido)
- `tipo` (String): `'refrigeracion'` | `'congelacion'`
- `temp_min` (Numeric, °C) — límite inferior aceptable
- `temp_max` (Numeric, °C) — límite superior aceptable
- `activa` (Boolean, default True)
- `creado_en` (DateTime, default ahora)

### `LecturaTemperatura`
- `id` (PK)
- `camara_id` (FK → camara.id, requerido)
- `temperatura` (Numeric, °C, requerido)
- `registrado_por` (FK → vendedor.id, nullable para usuario legacy)
- `registrado_en` (DateTime, default ahora)
- `fuera_de_rango` (Boolean) — se calcula y **persiste** al guardar (comparando
  con el rango de la cámara en ese momento), para que el histórico no cambie si
  luego se ajusta el rango de la cámara.
- `accion_correctiva` (Text, nullable) — obligatorio si `fuera_de_rango`.
- relación: `camara` (Camara), `registrado_por_vendedor` (Vendedor).

## Reglas de negocio

- Al registrar una lectura: `fuera_de_rango = (temperatura < camara.temp_min or
  temperatura > camara.temp_max)`.
- Si `fuera_de_rango` y `accion_correctiva` vacía → **error de validación, NO se
  guarda** (mensaje: "La lectura está fuera de rango; describe la acción
  correctiva").
- `registrado_por` = `current_user` si es Vendedor; `registrado_en` = ahora.
- Solo se pueden registrar lecturas de cámaras `activa=True`.

## Permisos

- **Registrar lecturas / ver historial / exportar:** cualquier usuario
  autenticado (`@login_required`).
- **Crear / editar / activar-desactivar cámaras:** solo `super_admin`
  (`@requiere_rol(['super_admin'])`, patrón existente; el usuario legacy también
  pasa, como en el resto de la app).

## Rutas y pantallas (mobile-first, extienden `base.html`, estilos `mobile-*`)

Prefijo `/registros/temperaturas` (el de limpieza será `/registros/limpieza`).

1. **`GET /registros/temperaturas`** — Principal. Lista las cámaras activas con
   el **estado de hoy**: ✓ si ya tiene al menos una lectura hoy, ⏳ si falta.
   Cada cámara tiene botón "Registrar lectura". Enlaces a Historial y Exportar.
2. **`POST /registros/temperaturas/registrar`** — Crea una `LecturaTemperatura`.
   Campos: `camara_id`, `temperatura`, `accion_correctiva` (condicional).
   Calcula `fuera_de_rango`; aplica la regla de acción correctiva. CSRF.
3. **`GET /registros/temperaturas/historial`** — Lista lecturas, filtrable por
   `fecha_inicio`/`fecha_fin` y `camara_id`. Las fuera de rango resaltadas en
   rojo, mostrando la acción correctiva.
4. **`POST /registros/temperaturas/export`** — PDF (reportlab) con tabla:
   fecha/hora, cámara, tipo, rango, lectura, ¿en rango?, responsable, acción
   correctiva; filtrado por rango de fechas (y cámara opcional) enviados por
   formulario. Encabezado con empresa y período. Se usa POST (con CSRF) para
   reutilizar tal cual el helper `compartirEtiquetaIOS` (fetch POST → hoja de
   compartir en iOS) y el `target=iframe` en Android; el servidor sirve inline
   en iOS vía `_is_ios_request()`, igual que las etiquetas. Nombre del PDF:
   `registro_temperaturas_<fecha_inicio>_<fecha_fin>.pdf`.
5. **Admin de cámaras** (solo super_admin):
   - `GET /registros/temperaturas/camaras` — lista.
   - `POST /registros/temperaturas/camaras/nueva` — crea (nombre, tipo,
     temp_min, temp_max).
   - `POST /registros/temperaturas/camaras/<id>/editar` — edita.
   - `POST /registros/temperaturas/camaras/<id>/toggle` — activar/desactivar.

## Acceso (navegación)

Enlace nuevo "Registros" en el menú de usuario (dropdown desktop) y el drawer
móvil de `base.html`, que lleva a `/registros/temperaturas`. Cuando se agregue
Limpieza, "Registros" pasará a ser un pequeño índice de registros.

## Validación y errores

- `temperatura` debe ser numérica; `camara_id` debe existir y estar activa.
- Acción correctiva obligatoria si fuera de rango (ver reglas).
- Rango de cámara: `temp_min <= temp_max` al crear/editar.
- Errores → `flash` + re-render del formulario sin guardar (patrón actual).

## Pruebas (TDD, `tests/test_registro_temperaturas.py`)

- Lectura dentro de rango → `fuera_de_rango=False`, se guarda sin acción
  correctiva.
- Lectura fuera de rango **sin** acción correctiva → rechazada (no se crea fila).
- Lectura fuera de rango **con** acción correctiva → se guarda, `fuera_de_rango=True`.
- `registrado_por` = usuario logueado; `registrado_en` poblada.
- CRUD de cámaras: un usuario no-admin recibe 403/redirect y no se crea/edita.
- Registrar lectura sin autenticación → redirige a login.
- Estado de hoy: una cámara con lectura hoy aparece ✓; sin lectura, ⏳.
- Export: `POST .../export` con `fecha_inicio`/`fecha_fin` devuelve `application/pdf`.

## Notas de implementación

- Migración: crear tablas `camara` y `lectura_temperatura`. **Recordar correr la
  migración también en Heroku** (`heroku pg:psql` / `db.create_all` en deploy) —
  ver MEMORY.md (cambios de esquema deben aplicarse en producción).
- Reusar `_is_ios_request()` y `etiquetas_ios_share.js` para la descarga del PDF.
- PDF tabular con reportlab Platypus (Table) — más limpio que canvas para tablas.
