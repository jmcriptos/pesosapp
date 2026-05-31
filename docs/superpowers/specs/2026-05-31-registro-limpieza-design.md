# Registros de limpieza + Productos/diluciones (HACCP)

**Fecha:** 2026-05-31
**Estado:** Aprobado — listo para plan de implementación

## Objetivo

Incluir, dentro de los registros HACCP de PesosApp (que ya contienen los
registros de temperatura), un sistema de **registros de limpieza y
desinfección** y una sección consultable de **productos de limpieza con su
dilución y procedimiento correctos**.

La limpieza y desinfección es un **prerrequisito (PRP/SSOP)** de HACCP, no un
PCC. El registro debe demostrar: qué se limpió y según qué procedimiento,
quién y cuándo, la verificación del resultado (Conforme/No conforme), la
acción correctiva ante un desvío, y la verificación periódica por un
responsable.

El diseño **espeja la feature de temperaturas ya existente** (modelos, rutas,
plantillas, PDF auditable, verificación de período, configuración de
documento/versión) para mantener consistencia de patrón y de código.

## Contexto del código existente (a replicar)

La feature de temperaturas vive en `app.py` (modelos en el mismo archivo) y
`templates/registros/`. Referencias:

| Pieza | Ubicación |
|------|-----------|
| Modelos `Camara`, `LecturaTemperatura`, `RegistroConfig`, `RevisionRegistro` | `app.py` ~2065–2134 |
| Rutas cámaras / temperaturas / historial / revisar / export / config | `app.py` ~8728–9073 |
| Helpers (`_get_registro_config`, `_camaras_con_lectura_hoy`, `_filtrar_lecturas`, `_revision_que_cubre`, `_build_temperaturas_pdf`) | `app.py` ~8692–9034 |
| Decoradores `requiere_rol`, `requiere_permiso_recurso` | `app.py` ~2283–2323 |
| Plantillas `temperaturas.html`, `temperaturas_historial.html`, `camaras.html`, `config.html` | `templates/registros/` |
| Navegación (drawer + dropdown) | `templates/base.html` ~281, ~419 |
| CSS | `static/css/registros.css` |

## Modelos nuevos (en `app.py`)

### `ProductoLimpieza` — catálogo consultable de diluciones/procedimientos
```
id              Integer  PK
nombre          String(120)  not null            # "Sanitizante clorado"
dilucion        String(255)  not null            # "10 ml por 1 L de agua"
procedimiento   Text         nullable            # pasos de aplicación
notas_seguridad Text         nullable            # EPP, precauciones
activo          Boolean      not null default True
creado_en       DateTime     not null default utcnow
```

### `AreaLimpieza` — catálogo de equipos/espacios (análogo a `Camara`)
```
id              Integer  PK
nombre          String(120)  not null            # "Sierra de cortar"
tipo            String(20)   not null default 'equipo'   # 'equipo' | 'espacio'
producto_id     Integer  FK -> producto_limpieza.id  nullable
metodo          Text         nullable            # instrucciones específicas del área
frecuencia_texto String(120) nullable            # "Diaria", "Por turno"
activa          Boolean      not null default True
creado_en       DateTime     not null default utcnow

producto = relationship('ProductoLimpieza')
```

### `RegistroLimpieza` — el log diario (análogo a `LecturaTemperatura`)
```
id                  Integer  PK
area_id             Integer  FK -> area_limpieza.id  not null  index
registrado_por      Integer  FK -> vendedor.id  nullable
registrado_en       DateTime  not null default utcnow  index
conforme            Boolean   not null default True     # True=Conforme, False=No conforme
observacion         Text      nullable                  # siempre disponible
accion_causa        Text      nullable
accion_tomada       Text      nullable                  # obligatoria si No conforme
accion_responsable  String(120) nullable
accion_disposicion  Text      nullable                  # obligatoria si No conforme

area = relationship('AreaLimpieza')
registrado_por_vendedor = relationship('Vendedor')
```

### `LimpiezaConfig` — singleton para el PDF (análogo a `RegistroConfig`)
```
id                      Integer  PK
codigo_documento        String(60)  not null default 'FR-HACCP-LIMP-01'
version                 String(20)  not null default '1'
frecuencia_texto        String(120) not null default 'Según programa de limpieza'
responsable_verificacion String(120) nullable
actualizado_en          DateTime  not null default utcnow
```

### `RevisionLimpieza` — verificación de período (análogo a `RevisionRegistro`)
```
id              Integer  PK
revisado_por    Integer  FK -> vendedor.id  nullable
revisado_en     DateTime  not null default utcnow
periodo_desde   Date     nullable
periodo_hasta   Date     nullable
nota            Text     nullable

revisado_por_vendedor = relationship('Vendedor')
```

## Rutas y permisos

Mismo patrón y decoradores que temperaturas.

| Método | URL | Función | Permiso |
|--------|-----|---------|---------|
| GET | `/registros/limpieza/productos` | `productos_limpieza_index` | login (todos) — consulta |
| POST | `/registros/limpieza/productos/nuevo` | `producto_limpieza_nuevo` | super_admin |
| POST | `/registros/limpieza/productos/<id>/editar` | `producto_limpieza_editar` | super_admin |
| POST | `/registros/limpieza/productos/<id>/toggle` | `producto_limpieza_toggle` | super_admin |
| GET | `/registros/limpieza/areas` | `areas_limpieza_list` | super_admin |
| POST | `/registros/limpieza/areas/nueva` | `area_limpieza_nueva` | super_admin |
| POST | `/registros/limpieza/areas/<id>/editar` | `area_limpieza_editar` | super_admin |
| POST | `/registros/limpieza/areas/<id>/toggle` | `area_limpieza_toggle` | super_admin |
| GET | `/registros/limpieza` | `limpieza_index` | login (todos) |
| POST | `/registros/limpieza/registrar` | `limpieza_registrar` | login (todos) |
| GET | `/registros/limpieza/historial` | `limpieza_historial` | login (todos) |
| POST | `/registros/limpieza/revisar` | `limpieza_revisar` | super_admin / supervisor |
| POST | `/registros/limpieza/export` | `limpieza_export` | login (todos) |
| GET/POST | `/registros/limpieza/config` | `limpieza_config` | super_admin |

### Reglas de validación
- `limpieza_registrar`: requiere `area_id` (área activa). Si `conforme=False`
  (No conforme), **`accion_tomada` y `accion_disposicion` son obligatorias**
  (mismo criterio que temperaturas fuera de rango). `observacion` siempre opcional.
- `area_limpieza_*`: `nombre` obligatorio, `tipo` ∈ {`equipo`,`espacio`},
  `producto_id` opcional (debe existir si se envía).
- `producto_limpieza_*`: `nombre` y `dilucion` obligatorios.

## Plantillas (en `templates/registros/`)

- `limpieza.html` — pantalla de registro (espejo de `temperaturas.html`).
  Lista áreas activas en tarjetas; por área muestra el **producto vinculado con
  su dilución y procedimiento** (consulta rápida) y un formulario con resultado
  Conforme/No conforme, observación, y bloque de acción correctiva expandible.
  Barra de herramientas: Historial · Áreas/equipos (admin) · Productos y
  diluciones · Configuración (admin).
- `limpieza_historial.html` — filtros (fecha_inicio, fecha_fin, area_id),
  export PDF, badge de verificación, botón "Marcar período como revisado"
  (super_admin/supervisor), lista de registros con acción correctiva expandible.
- `areas_limpieza.html` — CRUD admin de áreas/equipos (espejo de `camaras.html`),
  con selector de `producto_id`, `tipo`, `metodo`, `frecuencia_texto`.
- `productos_limpieza.html` — **nueva**: consulta para todos (nombre, dilución,
  procedimiento, notas de seguridad) + formularios CRUD visibles solo a super_admin.
- `limpieza_config.html` — config del documento (espejo de `config.html`).

Reutilizan `static/css/registros.css`.

## PDF auditable

Helper `_build_limpieza_pdf(registros, fecha_inicio, fecha_fin, config, revision)`
espejo de `_build_temperaturas_pdf`. Landscape A4, ReportLab.
- Encabezado: logo, "Jomar Foods B.V.", título "Registro de limpieza y
  desinfección", `Documento: {codigo_documento} · Versión: {version}`, período,
  generado.
- Tabla: Fecha/Hora · Área · Tipo · Producto · Resultado (Conforme/No conforme)
  · Responsable · Acción correctiva. Filas No conforme resaltadas en rojo.
- Bloque de verificación: si existe `RevisionLimpieza`, "Revisado por {nombre}
  el {fecha}"; si no, líneas para firma manual.
- Pie numerado con código de documento y versión en cada página.
- Integración iOS (`_is_ios_request`) inline vs attachment, como en temperaturas.

## Navegación

Convertir el ítem de menú "Registros" (hoy apunta directo a
`temperaturas_index`) en un **hub** `/registros` (`registros_index`) con dos
tarjetas: **Temperaturas** y **Limpieza**. Actualizar los dos enlaces de
`base.html` (drawer ~281 y dropdown ~419) para apuntar a `registros_index`.
Nueva plantilla `templates/registros/index.html` (hub).

## Base de datos / despliegue

Crear las **5 tablas nuevas** (`producto_limpieza`, `area_limpieza`,
`registro_limpieza`, `limpieza_config`, `revision_limpieza`) en local **y en
Heroku** vía `heroku pg:psql --app pesosapp`. Reiniciar dyno con
`heroku restart --app pesosapp`. No se modifican tablas existentes.

Orden de creación por FKs: `producto_limpieza` → `area_limpieza` →
`registro_limpieza`; `limpieza_config` y `revision_limpieza` independientes.

## Pruebas

Archivo `tests/test_registro_limpieza.py` (espejo de
`tests/test_registro_temperaturas.py`): registrar conforme, registrar No
conforme exige acción correctiva, CRUD de áreas y productos según rol,
verificación de período por supervisor, generación de PDF sin error.

## Fuera de alcance (YAGNI)

- Distinción pre-operacional/operacional (descartada en brainstorming).
- Lecturas numéricas / rangos automáticos (eso es de temperaturas).
- Recordatorios o programación automática de limpieza por frecuencia.
- Carga de fichas de seguridad (SDS) como archivos adjuntos.
