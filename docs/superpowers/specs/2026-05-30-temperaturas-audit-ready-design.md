# Diseño: Registro de temperaturas — audit-ready (HACCP)

**Fecha:** 2026-05-30
**Estado:** Aprobado (pendiente revisión final del usuario)

## Contexto y objetivo

El registro de temperaturas de cámaras ya existe (modelos `Camara`,
`LecturaTemperatura`; pantallas registrar/historial/export PDF; admin de
cámaras). Esta mejora lo lleva a ser **auditable** para HACCP (exigencia
regulatoria de Curaçao), agregando: configuración del registro (documento,
frecuencia, calibración del instrumento), acción correctiva estructurada,
verificación/revisión en la app (Principio 6) y un PDF con control de documento.

## Decisiones aprobadas
- Verificación: **en la app** (queda guardado quién revisó y cuándo; sale en el PDF).
- Acción correctiva: **estructurada** (causa, acción tomada, responsable, disposición).
  Obligatorias: **acción tomada** + **disposición del producto**. Opcionales: causa, responsable.
- Calibración: **config simple** (termómetro + última calibración) en nota al pie del PDF.
- Verificar lo pueden hacer **super_admin y supervisor**; configurar = **super_admin**.

## Modelos

### Nuevo: `RegistroConfig` (singleton — una sola fila)
- `id` (PK)
- `codigo_documento` (String, ej. "FR-HACCP-TEMP-01")
- `version` (String, ej. "1")
- `frecuencia_texto` (String, ej. "2 veces al día (mañana y tarde)")
- `termometro` (String, ej. "Termómetro digital TP-01")
- `termometro_calibrado_en` (Date, nullable) — última calibración
- `actualizado_en` (DateTime, default ahora)

Helper `_get_registro_config()`: devuelve la fila única; si no existe, la crea
con valores por defecto y la persiste. Toda lectura de config pasa por él.

### Nuevo: `RevisionRegistro` (verificación de un período)
- `id` (PK)
- `revisado_por` (FK → vendedor.id, nullable)
- `revisado_en` (DateTime, default ahora)
- `periodo_desde` (Date, nullable) — inicio del período revisado
- `periodo_hasta` (Date, nullable) — fin del período revisado
- `nota` (Text, nullable)
- relación `revisado_por_vendedor` (Vendedor)

### Extensión de `LecturaTemperatura` (4 columnas nuevas)
- `accion_causa` (Text, nullable)
- `accion_tomada` (Text, nullable)
- `accion_responsable` (String, nullable)
- `accion_disposicion` (Text, nullable)

Se conserva la columna `accion_correctiva` existente (datos históricos); las
lecturas nuevas usan los campos estructurados. En historial/PDF se muestra lo
que exista (estructurado si está, si no el texto legacy).

## Reglas de negocio

### Registro de lectura (actualiza `temperatura_registrar`)
- Igual que hoy: calcula `fuera_de_rango`.
- Si `fuera_de_rango`: **obligatorios** `accion_tomada` y `accion_disposicion`
  (si falta alguno → error, no guarda). `accion_causa` y `accion_responsable`
  se guardan si vienen. (Si en rango, los campos de acción se ignoran/null.)

### Verificación (`/registros/temperaturas/revisar`, POST)
- Permisos: super_admin o supervisor (login + chequeo de rol).
- Recibe `periodo_desde`/`periodo_hasta` (del filtro actual del historial).
- Crea un `RevisionRegistro` con `revisado_por = current_user`, `revisado_en = ahora`.
- Flash de confirmación; redirige al historial con el mismo filtro.

### Config (`/registros/temperaturas/config`, GET/POST)
- Permisos: super_admin.
- GET: formulario con los valores actuales (vía `_get_registro_config()`).
- POST: valida y guarda (código, versión, frecuencia, termómetro, fecha calibración).
  `termometro_calibrado_en` parsea 'YYYY-MM-DD' (vacío permitido → None).

## PDF (`_build_temperaturas_pdf`)

Encabezado (además de lo actual — logo, empresa, título, período, generado):
- Línea con **código de documento + versión** (de la config).

Tabla:
- La columna "Rango (°C)" se renombra a **"Límite crítico (°C)"**.
- La columna "Acción correctiva" muestra los campos estructurados compuestos
  (ej. `Causa: … | Acción: … | Resp.: … | Disposición: …`), o el texto legacy.

Bloque de verificación (después de la tabla):
- Si existe un `RevisionRegistro` cuyo `[periodo_desde, periodo_hasta]` **cubre**
  el período exportado (desde ≤ fi y hasta ≥ ff; el más reciente), imprime:
  "Verificado por: **{nombre}** — {fecha de revisión}".
- Si no, imprime una línea para firma manual: "Revisado por: ____________  Fecha: __________".
- (Cuando el export no tiene fechas → "todas las fechas", se usa la revisión más reciente si existe, si no la línea de firma.)

Pie de página (en cada página, vía callback `onPage` del `SimpleDocTemplate`):
- Izquierda: "Frecuencia de monitoreo: {config.frecuencia_texto}" y
  "Instrumento: {config.termometro} — última calibración: {fecha o 'N/D'}".
- Derecha: "Página X de Y" (numeración con `canvas.getPageNumber()` + total).
- Línea con el código de documento + versión.

## Pantallas / navegación
- **Registrar lectura** (`temperaturas.html`): el formulario por cámara muestra
  Temperatura y, en un **bloque colapsable `<details>` "Acción correctiva (solo si
  está fuera de rango)"**, los 4 campos (causa, acción tomada, responsable,
  disposición). El servidor exige acción tomada + disposición cuando la lectura
  está fuera de rango. Se mantiene mobile-first y el estilo `registros.css`.
- **Historial** (`temperaturas_historial.html`): cada fila fuera de rango muestra
  los campos estructurados. Si el usuario es super_admin/supervisor, aparece un
  botón **"Marcar período como revisado"** (POST a `/revisar` con el filtro
  actual). Si ya hay revisión del período, muestra "Verificado por X el Y".
- **Config** (`config.html`, nueva): formulario de la configuración. Enlace a
  Config desde la pantalla principal (solo super_admin), junto a "Cámaras".

## Permisos (resumen)
- Registrar lecturas / ver / exportar: cualquier usuario autenticado.
- Verificar (revisar): super_admin o supervisor.
- Configurar (config) y administrar cámaras: super_admin.

## Datos / migración
- Tablas nuevas `registro_config` y `revision_registro`: se crean con
  `db.create_all()` (en deploy, vía `heroku run`).
- 4 columnas nuevas en la tabla existente `lectura_temperatura`: `db.create_all()`
  **no** altera tablas existentes, así que se agregan con `ALTER TABLE` en Heroku
  (ver MEMORY.md). Comandos en el paso de deploy:
  `ALTER TABLE lectura_temperatura ADD COLUMN accion_causa TEXT;` (y las otras 3:
  `accion_tomada TEXT`, `accion_responsable VARCHAR`, `accion_disposicion TEXT`).
  En SQLite (tests) `db.create_all()` ya crea la tabla con todas las columnas.

## Pruebas (TDD, ampliando `tests/test_registro_temperaturas.py`)
- `_get_registro_config()` crea y reutiliza la fila singleton.
- Config: super_admin guarda; no-admin bloqueado.
- Lectura fuera de rango sin `accion_tomada`/`accion_disposicion` → rechazada;
  con ambos → guardada con los campos estructurados poblados.
- Lectura en rango ignora los campos de acción.
- Revisar: super_admin/supervisor crea `RevisionRegistro`; un vendedor normal
  es bloqueado.
- Export PDF sigue devolviendo `application/pdf` (con config + verificación).
- Historial renderiza el botón de revisión para roles autorizados.

## Fuera de alcance (YAGNI)
- Termómetros administrables por lectura (se eligió config simple).
- Notificaciones/recordatorios y cadencia forzada.
- Firma digital criptográfica (basta responsable + verificación registrada).
- Registro de limpieza (sub-proyecto aparte).
