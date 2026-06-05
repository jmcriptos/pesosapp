# Ajustes al Registro de Limpieza y Desinfección (FR-HACCP-LIMP-01)

**Fecha:** 2026-06-04
**Origen:** `03_Especificacion - Ajustes al Registro de Limpieza.docx` (Jomar Foods, BV — Junio 2026)
**Objetivo:** Dejar el registro digital de limpieza a prueba de auditoría de inocuidad,
agregando campos y reglas sin reemplazar el sistema actual.

## 1. Contexto

El registro digital actual (`RegistroLimpieza` + bottom-sheet de firma en
`templates/registros/limpieza.html`) ya captura: Fecha/Hora, Área (catálogo controlado
vía `AreaLimpieza`), Resultado (Conforme/No conforme), Observación, Firma y acción
correctiva estructurada (causa/tomada/responsable/disposición) condicional a "No conforme".
Existe `RevisionLimpieza` para verificación HACCP a nivel de período.

Esta spec agrega los campos y reglas que faltan respecto a la especificación oficial.

## 2. Decisiones de alcance (acordadas)

- **Verificó**: segunda persona seleccionada en el mismo sheet desde la lista de usuarios
  (`Vendedor`), **distinta del operador**. Sin segunda firma (firma solo el operador).
- **ppm**: obligatorio **solo cuando el área tiene un sanitizante asignado**
  (`AreaLimpieza.sanitizante_id`). Para áreas solo-detergente no se pide.
- **Campos recomendados**: se incluye **Método de verificación** (Visual/ATP/hisopado).
  **No** se incluye "Tipo/frecuencia por registro" (YAGNI: `AreaLimpieza.frecuencia_texto`
  ya cubre la frecuencia a nivel de ficha).
- **Catálogo**: seed idempotente que crea lo faltante; no borra nada.

## 3. Modelo de datos

Tres columnas nuevas en `RegistroLimpieza`:

| Columna | Tipo | Null | Descripción |
|---|---|---|---|
| `concentracion_ppm` | `INTEGER` | sí | ppm de Sani-T-10 Plus medido con tira reactiva. |
| `verificado_por` | `INTEGER` FK→`vendedor.id` | sí | Verificador independiente. |
| `metodo_verificacion` | `VARCHAR(20)` | sí | `visual` \| `atp` \| `hisopado`. |

- Nullable en BD para no romper registros históricos; la obligatoriedad se aplica en la
  capa de validación del formulario, no en el esquema.
- Relación nueva: `verificado_por_vendedor = db.relationship('Vendedor', foreign_keys=[verificado_por])`.
  Como `registrado_por` también apunta a `Vendedor`, ambas relaciones deben declarar
  `foreign_keys` explícito.
- Migración: añadir las tres columnas al dict `wanted['registro_limpieza']` de
  `_ensure_haccp_columns()` ([app.py:182](../../../app.py)). Esto las crea idempotentemente
  en SQLite (local) y Postgres (Heroku) en cada arranque. No requiere `flask db upgrade`
  ni ALTER manual.

## 4. Catálogo (seed idempotente)

Función nueva `_seed_catalogo_limpieza()` llamada en el arranque (junto a
`_ensure_haccp_columns()`). **Solo crea lo que falta; nunca borra ni desactiva.**

- **Productos** (`ProductoLimpieza`, match por `nombre` case-insensitive):
  - "Big Punch" — detergente.
  - "POOFF" — detergente.
  - "Sani-T-10 Plus" — sanitizante.
  - `dilucion` es `NOT NULL`: usar `'Según ficha técnica'` como valor por defecto al crear.
- **Áreas/equipos** (`AreaLimpieza`, match por `nombre` case-insensitive):
  - Equipos (`tipo='equipo'`): Tanque de salmueras; Inyectadora Inject Star;
    Embutidora Vemag; Molino Torrey; Rebanadora Icone 700; Mezclador MPR 400;
    Horno Ahumador; Carros para horno.
  - Espacios (`tipo='espacio'`): Sala de Producción; Sala de Mezclado;
    Sala de Cocción y Ahumado; Almacenes; Pisos y drenajes; Camión de reparto.
  - A los **equipos creados por el seed** se les asigna Sani-T-10 Plus como
    `sanitizante_id` (activa el gate de ppm de fábrica). Áreas preexistentes **no** se
    modifican. El admin puede ajustar el sanitizante desde la UI existente.

## 5. Flujo de registro

### 5.1 UI (bottom-sheet de firma en `limpieza.html`)

Campos nuevos, ubicados antes del pad de firma:

1. **ppm** (`name="concentracion_ppm"`, `type="number"`, `inputmode="numeric"`):
   visible solo si el área tiene sanitizante. El botón `.js-open-firma` expone un nuevo
   atributo `data-area-sani-id`; al abrir el sheet se muestra/oculta el bloque ppm según
   ese dato. Indicador de rango en vivo: verde dentro de 150–400, rojo fuera.
2. **Verificó** (`<select name="verificado_por">`): poblado con usuarios activos;
   se **excluye al operador** (current_user) de las opciones. Obligatorio.
3. **Método de verificación** (`<select name="metodo_verificacion">`):
   opciones vacía/Visual/ATP/Hisopado. Opcional.

Estilos: reutilizar el patrón `.ops-field` (label + control). El indicador de rango ppm
y, si hace falta, el estilo del `<select>` se añaden en el CSS de la pantalla; verificar
si pertenece a un archivo minificado y regenerar (ver §8). El `<script>` es inline en
`{% block scripts %}`, así que **no** afecta `base.min.js`.

### 5.2 Lógica de cliente (`updateConfirm`)

`confirmBtn.disabled` se habilita solo si se cumplen TODAS:
- `hasSign` (firma del operador presente),
- `correctiveValid()` (acción correctiva válida si No conforme) — sin cambio,
- `verifierSelected` (verificado_por con valor),
- `ppmValid`: si el bloque ppm está visible →
  - Resultado **Conforme**: ppm debe ser entero dentro de 150–400.
  - Resultado **No conforme**: ppm puede estar fuera de rango (se documenta el desvío);
    se acepta vacío o cualquier valor.

Al cambiar Resultado o editar el ppm se recalcula. Si el usuario intenta Conforme con
ppm fuera de rango, se muestra hint inline: "ppm fuera de rango (150–400): corrige y
vuelve a medir, o marca No conforme".

### 5.3 Validación de servidor (`limpieza_registrar`)

Espeja el cliente (defensa en profundidad). Si algo falla, `flash(...,'danger')` +
redirect a `limpieza_index` sin crear el registro:

- Si `area.sanitizante_id` está definido:
  - ppm obligatorio y parseable a entero.
  - Si `conforme` y (ppm `< 150` o `> 400`) → rechazar con el mensaje de rango.
- `verificado_por` obligatorio; debe ser un `Vendedor` válido y **distinto** del operador
  (`current_user.id` cuando es `Vendedor`).
- `metodo_verificacion` opcional; si viene, validar contra el set
  `{'visual','atp','hisopado'}` (ignorar si no coincide).
- Persistir las tres columnas nuevas en el `RegistroLimpieza`.

## 6. Superficies de visualización

- **Historial** (`limpieza_historial.html`): añadir ppm y Verificó a cada fila
  (extender la grilla de columnas y el `ops-thead`).
- **PDF** (`_build_limpieza_pdf`): agregar columna **ppm** y columna **Verificó**;
  el **Método** va en la línea de detalle (`_detalle`). Reajustar `widths`/`headers`/
  `aligns` para landscape A4 (ancho útil ≈ 784 pt).
- **Excel** (`limpieza_export`, `formato=excel`): añadir columnas ppm, Verificó,
  Método de verificación a `headers` y `rows`.

## 7. Auditoría

- En no-conformes y en desvíos de rango ppm, el detalle pasado a `_haccp_alerta` /
  `_audit` incluye el valor de ppm medido (ej. "ppm=120 (fuera de 150–400)").

## 8. Minificación

- `limpieza.html` usa `<script>` inline → `base.min.js` no se toca.
- Si las clases `.ops-*` afectadas viven en un CSS minificado (`styles.min.css` /
  `css/main.min.css`), regenerar el minificado desde la fuente tras editar. Confirmar
  durante implementación dónde residen los estilos `.ops-field`/sheet.

## 9. Reglas de la spec ya cubiertas (sin cambio)

- **Catálogo controlado**: las áreas ya se eligen de `AreaLimpieza` (no texto libre).
- **No conforme → acción correctiva**: ya existe, estructurada y obligatoria.

## 10. Fuera de alcance

- Campo "Tipo/frecuencia" por registro (cubierto por `AreaLimpieza.frecuencia_texto`).
- Segunda firma del verificador.
- Re-verificación posterior como flujo separado de estado (la verificación es en el
  mismo momento del registro, por persona distinta).
- Desactivación de áreas no oficiales (el seed no borra).

## 11. Verificación de éxito

- Registrar un área con sanitizante: ppm fuera de rango bloquea Conforme; en rango permite.
- ppm no se exige en áreas sin sanitizante.
- No se puede confirmar sin elegir Verificó; no se puede elegir al propio operador.
- ppm/Verificó/Método aparecen en Historial, PDF y Excel.
- Arranque limpio en BD nueva crea productos y áreas oficiales; segundo arranque no duplica.
