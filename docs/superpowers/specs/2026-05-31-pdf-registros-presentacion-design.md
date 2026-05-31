# Mejorar la presentación del PDF de registros (temperaturas y limpieza)

**Fecha:** 2026-05-31
**Estado:** Aprobado — implementación directa (cambio acotado a las 2 funciones del PDF)

## Problema

La tabla del PDF se ve despareja: la columna "Acción correctiva" mete mucho texto
en una celda angosta y estira solo algunas filas; no hay franjas alternas; el
estado va en texto plano ("Sí/NO"); grilla completa que recarga.

## Diseño (aplica a temperaturas y limpieza)

Se reescribe **solo la sección de tabla** de `_build_temperaturas_pdf` y
`_build_limpieza_pdf`; el encabezado (logo, documento/versión, período), el bloque
de verificación y el pie numerado se mantienen.

1. **Acción correctiva / observación en sub-fila de ancho completo.** Sale de la
   columna angosta. Cuando hay desvío (fuera de rango / no conforme) u observación,
   se agrega una sub-fila con `SPAN` a todo el ancho, fondo rojo claro (desvío) o
   gris claro (observación conforme), texto pequeño indentado:
   `Acción correctiva — Causa: … · Acción: … · Resp.: … · Disposición: …`.
   Así **las filas normales quedan de altura pareja**.
   - **Temperaturas** → columnas: Fecha/Hora · Cámara · Tipo · Límite crítico (°C) ·
     Lectura (°C) · En rango · Responsable.
   - **Limpieza** → columnas: Fecha/Hora · Área · Tipo · Producto · Resultado ·
     Responsable. (observación + acción → sub-fila).
2. **Zebra**: filas alternas en gris muy claro (`#f8fafc`); filas/sub-filas de
   desvío en rojo claro (`#fee2e2`).
3. **Grilla mínima**: sin líneas verticales; solo una línea horizontal fina
   (`#e2e8f0`) bajo cada grupo (fila + sub-fila). Encabezado navy (`#1f2937`) con
   texto blanco y línea inferior gruesa.
4. **Estado en color**: "Sí"/"Conforme" en verde (`#15803d`); "NO"/"No conforme" en
   rojo (`#b91c1c`), negrita, centrado.
5. **Números a la derecha** (Límite crítico, Lectura), alineación derecha.
6. **Robustez**: se escapan los caracteres XML (`& < >`) del texto dinámico al
   construir los Paragraph, para que nombres/observaciones con esos caracteres no
   rompan la generación del PDF.

## Implementación

- Nuevo import: `TA_RIGHT` (junto a `TA_LEFT`, `TA_CENTER`).
- Helper de módulo `_registro_pdf_tabla(headers, aligns, widths, estado_col, filas)`
  que centraliza zebra/grilla/estado-en-color/sub-fila (DRY: lo usan los dos
  builders). `filas` = lista de `{cols, desvio, detalle}`.
- Helper `_pdf_xe(s)` para escape XML.
- Cada builder arma `filas` y llama al helper; se elimina el estilo `cell` y el
  armado manual de `data`/`TableStyle`/`GRID` previos.

## Verificación

- Generar un PDF de muestra de cada reporte con datos reales (incl. una fila de
  desvío con acción correctiva), renderizar a imagen y revisar visualmente que las
  filas queden parejas, zebra/colores correctos y la sub-fila legible.
- Tests existentes (`test_export_devuelve_pdf` en ambos suites) deben seguir verdes.

## No-alcance (YAGNI)

- Sin franja de resumen ni agrupación (era la opción 2, no elegida).
- Sin cambios de columnas más allá de mover acción/observación a la sub-fila.
- Sin cambios de backend, rutas ni datos.
