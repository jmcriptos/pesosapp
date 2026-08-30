---
name: PesosApp
description: Panel de operaciones para un distribuidor de alimentos, usado con guantes en planta y en ruta.
colors:
  indigo-lectura: "#6366f1"
  indigo-lectura-honda: "#4f46e5"
  indigo-lectura-tinta: "#4338ca"
  negro-de-bisel: "#0b0e14"
  gris-de-bisel: "#141820"
  blanco-de-esfera: "#f8fafc"
  superficie: "#ffffff"
  tinta: "#0f172a"
  tinta-media: "#475569"
  tinta-tenue: "#64748b"
  linea: "#e2e8f0"
  verde-de-conforme: "#10b981"
  ambar-de-aviso: "#f59e0b"
  rojo-de-falla: "#f43f5e"
  azul-de-dato: "#0ea5e9"
  conforme-marca: "#0f9d6e"
  conforme-fondo: "#ecfdf5"
  conforme-tinta: "#065f46"
  aviso-marca: "#d97706"
  aviso-fondo: "#fffbeb"
  aviso-tinta: "#92400e"
  falla-marca: "#be123c"
  falla-fondo: "#fff1f2"
  falla-tinta: "#9f1239"
typography:
  figure:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'SF Pro Text', Inter, 'Segoe UI', Roboto, system-ui, sans-serif"
    fontSize: "32px"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.02em"
  screen:
    fontFamily: "{typography.figure.fontFamily}"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.25
  client:
    fontFamily: "{typography.figure.fontFamily}"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.25
  body:
    fontFamily: "{typography.figure.fontFamily}"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.4
  meta:
    fontFamily: "{typography.figure.fontFamily}"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.4
  input:
    fontFamily: "{typography.figure.fontFamily}"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "{typography.figure.fontFamily}"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0.06em"
  micro:
    fontFamily: "{typography.figure.fontFamily}"
    fontSize: "10px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.08em"
  headline:
    fontFamily: "{typography.figure.fontFamily}"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
rounded:
  xs: "4px"
  sm: "8px"
  md: "12px"
  control: "14px"
  lg: "16px"
  xl: "20px"
  full: "9999px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
  "12": "48px"
components:
  button:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.tinta}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
    height: "48px"
    typography: "{typography.meta}"
  button-primary:
    backgroundColor: "{colors.indigo-lectura}"
    textColor: "{colors.superficie}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
    height: "48px"
  button-primary-hover:
    backgroundColor: "{colors.indigo-lectura-honda}"
  button-glove:
    backgroundColor: "{colors.indigo-lectura}"
    textColor: "{colors.superficie}"
    rounded: "{rounded.control}"
    height: "56px"
  input:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.tinta}"
    rounded: "{rounded.sm}"
    padding: "12px 16px"
    height: "52px"
    typography: "{typography.input}"
  card:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.tinta}"
    rounded: "{rounded.control}"
    padding: "20px"
  chip:
    backgroundColor: "{colors.linea}"
    textColor: "{colors.tinta-media}"
    rounded: "{rounded.full}"
    padding: "4px 12px"
---

# Design System: PesosApp

## Overview

**Creative North Star: "El Panel de Instrumentos"**

PesosApp se lee como el tablero de una máquina: un bisel oscuro que enmarca lecturas
claras. El `<body>` es Negro de Bisel y la topbar y la tabbar viven ahí; el contenido
—`main.app-content`— es Blanco de Esfera. Eso **no es un modo oscuro**: el modo oscuro
se descartó como producto el 2026-08-28 y su toggle se eliminó de toda la app. El
marco es oscuro a propósito, para que las cifras del centro sean lo único que brilla.

El sistema es preciso y sobrio. La densidad de información es alta porque la pantalla
se consulta muchas veces por día para tareas repetidas, y cada elemento tiene que
ganarse el lugar contra el dato que tapa. No hay ornamento: el color se reserva para
identidad y estado, la tipografía trabaja con cinco roles y no más, y lo que no es
dato es marco.

La escala de los controles no sale de una guía genérica sino del lugar donde se usa
la app: en ruta y en planta, a veces con guante. De ahí que ningún destino de toque
baje de 48px y que lo que se opera con el guante puesto mida 56px. El acabado de
cristal —translucidez, desenfoque de 18px y sombras teñidas de índigo— es el material
del instrumento, presente en reposo, no una señal de jerarquía.

**Key Characteristics:**
- Bisel oscuro (`#0b0e14`), esfera clara (`#f8fafc`); el marco nunca compite con el dato.
- Destinos de toque de 48px mínimo y 56px para uso con guante.
- Cinco roles tipográficos nombrados por significado, no por tamaño.
- Cristal como material (blur 18px, sombra índigo en reposo), no como decoración.
- Índigo para identidad; verde, ámbar y rojo exclusivamente para estado.
- Movimiento corto y elástico como respuesta al toque, nunca como entrada.

## Colors

Una identidad índigo sobre neutros de pizarra fría, con tres colores de estado que no
se prestan a nada más.

### Primary
- **Índigo de Lectura** (`#6366f1`): identidad de la app. Acción principal, enlaces,
  foco, y el trazo del dato en gráficos. En reposo tiñe las sombras de cristal, que es
  lo que le da material a las superficies.
- **Índigo de Lectura Honda** (`#4f46e5`): el mismo color un paso adentro. Hover de la
  acción principal y relleno de barras de dato.
- **Índigo de Lectura Tinta** (`#4338ca`): estado activo y anillos de foco sobre fondo claro.

### Secondary
- **Azul de Dato** (`#0ea5e9`): información neutra que no es ni éxito ni alarma.
  Deliberadamente escaso.

### Neutral
- **Negro de Bisel** (`#0b0e14`): el marco. Topbar, tabbar, cajón de navegación. Nunca
  toca el área de contenido.
- **Gris de Bisel** (`#141820`): elevación dentro del marco oscuro (menús desplegados,
  secciones del cajón).
- **Blanco de Esfera** (`#f8fafc`): el fondo del área de contenido, sobre el que flotan
  las tarjetas.
- **Superficie** (`#ffffff`): tarjetas, hojas, campos.
- **Tinta** (`#0f172a`): texto principal y cifras.
- **Tinta Media** (`#475569`): texto secundario sobre el fondo de la pantalla, donde el
  gris más claro no llega a 4.5:1.
- **Tinta Tenue** (`#64748b`): texto secundario sobre tarjeta blanca.
- **Línea** (`#e2e8f0`): bordes y divisiones.

### Status
Cada estado tiene dos usos y por eso dos valores: el **tono nominal**, que es el que
vive en `tokens.css`, y la **marca medida**, que es la que se pinta cuando el color
tiene que distinguirse de sus vecinos sobre blanco.

- **Verde de Conforme** (`#10b981`) · marca `#0f9d6e`, chip `#ecfdf5` sobre `#065f46`:
  dentro de objetivo, entregado, facturado.
- **Ámbar de Aviso** (`#f59e0b`) · marca `#d97706`, chip `#fffbeb` sobre `#92400e`:
  al límite, requiere atención.
- **Rojo de Falla** (`#f43f5e`) · marca `#be123c`, chip `#fff1f2` sobre `#9f1239`:
  vencido, fuera de objetivo, error.

**Por qué dos.** El ámbar y el rojo nominales, uno al lado del otro sobre blanco,
separan ΔE 5.7 bajo deuteranopía y 11.5 con visión normal: por debajo del piso de 15,
o sea indistinguibles incluso viendo todos los colores. Las marcas medidas separan
ΔE 8.7 y 20.0, y las tres superan 3:1 contra el blanco.

### Named Rules

**La Regla del Bisel.** El oscuro es el marco y solo el marco. Ningún panel de
contenido, tarjeta, tabla ni hoja usa fondo oscuro. Si una pantalla se ve oscura en el
centro, es un bug, no una variante.

**La Regla del Estado Reservado.** Verde, ámbar y rojo significan estado y nada más.
Nunca son «el cuarto color de la serie» en un gráfico ni un acento decorativo. Y al
revés: un estado nunca viaja solo en el color — siempre lleva icono o palabra.

**La Regla de los Dos Grises.** Sobre tarjeta blanca, el texto secundario es Tinta
Tenue (`#64748b`, 4.76:1). Sobre el fondo de la pantalla (`#f4f6fa`/`#f8fafc`) ese mismo
gris cae a 4.4:1 y hay que usar Tinta Media (`#475569`). El fondo decide el gris.

## Typography

**Font:** la pila del sistema — `-apple-system, BlinkMacSystemFont, 'SF Pro Display',
'SF Pro Text', Inter, 'Segoe UI', Roboto, system-ui, sans-serif`.
**Mono:** `ui-monospace, 'SF Mono', Menlo, Consolas, monospace`, solo para lecturas de
instrumento (temperaturas, pesos).

**Character:** sin personalidad tipográfica propia, y a propósito: la fuente del sistema
carga instantáneo, se ve nativa dentro de la PWA y deja que la jerarquía la haga el
tamaño y el peso. La escala arranca en 15px de base móvil, más alta que la web habitual,
porque se lee a un brazo de distancia.

### Hierarchy
- **Figure** (700, 32px, 1.1, -0.02em): cifras. El número que la pantalla existe para mostrar.
- **Screen** (600, 20px, 1.25): título de pantalla o de sección.
- **Client** (600, 17px, 1.25): nombre de cliente o de producto — el dato que se lee en voz alta.
- **Body** (400, 15px, 1.4): texto de interfaz.
- **Meta** (500, 13px, 1.4): dato secundario, fechas, unidades.
- **Input** (400, 16px): campos, y **solo** campos.
- **Headline** (700, 24px, -0.02em): cifra de segundo orden — el total de una tarjeta de gráfico.
- **Label** (700, 11px, 0.06em): micro-etiqueta. Chips, leyendas, unidades, umbrales.
- **Micro** (700, 10px, 0.08em): el piso absoluto. Solo etiquetas de la tabbar.

### Named Rules

**La Regla de los Cinco Roles.** El texto de contenido tiene cinco roles y se piden por
significado (`--text-role-figure`, `-screen`, `-client`, `-body`, `-meta`), no por
tamaño. Una pantalla nueva no elige un `font-size`: elige qué es ese texto. Por debajo
de esos cinco viven tres tamaños de servicio —headline (24px), label (11px) y micro
(10px)— para cifras de segundo orden y micro-etiquetas; están en la escala
(`--text-xl`, `--text-xs`, `--text-2xs`) y no admiten valores intermedios.

**La Regla de los 16px.** Todo campo de formulario va a 16px (`--text-input`). Por debajo
de eso, iOS Safari hace zoom al enfocar y rompe el layout. No es una preferencia
estética, es una restricción de la plataforma.

**La Regla del Piso de 11px.** Ningún texto baja de 11px. Se lee en un teléfono, en
planta, con luz de galpón.

**La Regla de las Cifras.** `font-variant-numeric: tabular-nums` solo donde los números
se alinean verticalmente (columnas, ejes, filas de tabla). En una cifra grande y suelta
las cifras de ancho fijo dejan huecos: ahí van proporcionales.

## Layout

Móvil primero, con un contenedor que se ensancha por pasos. El área de contenido usa
16px de padding lateral en teléfono y se centra con `max-width: 1100px` en escritorio;
la tabbar se limita a 480px y se centra, para que en tablet no quede estirada.

El ritmo es una escala de 4: 4, 8, 12, 16 (base), 20, 24, 32, 48. La separación entre
secciones es de 26px y entre tarjetas de una grilla, de 10 a 16px.

Los cortes observados son **768/769px** (teléfono a tablet), **900px** (grillas de KPI
a varias columnas) y **1024px** (escritorio). No hay tokens de breakpoint: se escriben
a mano y conviene respetar esos tres.

La tabbar es fija abajo, cinco columnas iguales, y **respeta `env(safe-area-inset-bottom)`**.
Todo lo que se fije al pie tiene que ir por encima de ella o quedará intocable.

**Escritorio: una grilla de 12 columnas.** A partir de 1024px el contenedor de una
pantalla larga deja de ser una columna y pasa a `grid-template-columns: repeat(12,
minmax(0, 1fr))` con `gap: 26px 8px`; cada sección declara su `grid-column: span N`.
El gap horizontal es de 8px y no de 20 porque cada componente ya trae sus 16px de
canaleta: 16 + 8 + 16 dan la calle de 40px, sin una segunda escala que mantener.
El orden del DOM no cambia — en teléfono sigue siendo un solo scroll—, así que la
composición de escritorio no puede contradecir el orden de lectura, solo aprovechar
el ancho. Repartos en uso hoy (dashboard): 7/5 para la fila del pliegue, 4/4/4 para
la fila de lecturas y 6/6 para los rankings.

### Named Rules

**La Regla del Pie Alcanzable.** Un botón de guardar dentro de una hoja va en un pie
`position: sticky; bottom: 0` dentro de la hoja. Si se fija a la ventana, la tabbar lo
tapa y no se puede pulsar.

## Elevation & Depth

La profundidad es **ambiental**: da material, no jerarquía. Las superficies de cristal
llevan su sombra teñida de índigo en reposo, porque esa sombra es parte del acabado —el
brillo del vidrio sobre el bisel— y no una señal de que algo esté «más arriba». Las
sombras neutras sí escalan con la elevación real (tarjeta, menú, modal).

### Shadow Vocabulary
- **xs** (`0 1px 2px rgba(15,23,42,0.05)`): botones en reposo.
- **sm** (`0 1px 3px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)`): tarjetas.
- **md** (`0 4px 12px -2px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.04)`): tarjeta al hover.
- **lg / xl**: hojas y modales.
- **glass-sm** (`0 4px 14px -4px rgba(99,102,241,0.18)`): acción principal — el halo índigo del cristal.
- **glass-md** (`0 20px 40px -12px rgba(99,102,241,0.22), 0 2px 6px rgba(15,23,42,0.04)`): tarjeta de cristal.

### Named Rules

**La Regla del Halo con Desplazamiento.** Toda sombra tiene desplazamiento y desenfoque.
Un halo de color centrado en cero no es profundidad, es decoración.

## Shapes

Esquinas suaves y constantes. El radio de control es **14px** (`--radius-control`) y lo
usan las tarjetas y la acción principal; 8px para campos, 12px para botones, 20px para
tarjetas de cristal, y píldora completa para chips y estados.

Los bordes son de 1px y visibles: sobre blanco, `#e2e8f0`; dentro de una tarjeta,
`rgba(15,23,42,0.06)`. La separación entre marcas de dato se hace con un hueco del color
de la superficie, nunca con un borde dibujado alrededor.

### Named Rules

**La Regla de la Franja Prohibida.** Ninguna tarjeta, ítem de lista ni aviso lleva un
borde de color de más de 1px en un solo lado. La franja lateral gruesa es el tic más
reconocible de una interfaz generada; el estado se dice con un chip, no con una barra.

## Components

Los controles son **táctiles y con respuesta**: el botón sube 1px al pasar por encima y
se hunde al presionar, la tarjeta interactiva se eleva 2px. Esa respuesta física es
parte del diseño y usa `--ease-spring`; no es un adorno que se pueda quitar.

### Buttons
- **Forma:** esquinas suaves (12px), altura mínima 48px, nunca menos.
- **Primary:** Índigo de Lectura sobre blanco, sin borde, con halo de cristal (`--shadow-glass-sm`).
- **Hover / Active:** `translateY(-1px)` al hover; `scale(0.98)` al presionar, con `--ease-spring` en 120ms.
- **Focus:** anillo de 3px `rgba(99,102,241,0.35)`, nunca `outline: none` a secas.
- **Guante:** la acción principal a ancho completo en móvil mide 56px (`--control-h-primary`).
- **Ghost / Soft / Danger:** mismas medidas, distinto relleno; el peligro usa Rojo de Falla.

### Inputs / Fields
- **Estilo:** blanco, borde de 1px, 8px de radio, 52px de alto, texto de 16px.
- **Focus:** el borde pasa a Índigo de Lectura y aparece el anillo de 3px.
- **Error:** borde en Rojo de Falla y anillo rojo; el mensaje va debajo, en texto, nunca solo en color.

### Cards / Containers
- **Esquinas:** 14px (20px en la variante de cristal).
- **Fondo:** blanco sobre Blanco de Esfera; la variante de cristal usa `rgba(255,255,255,0.72)` con `blur(18px) saturate(1.2)`.
- **Sombra:** `--shadow-sm` en reposo, `--shadow-md` al hover si es interactiva.
- **Padding:** 20px de cuerpo; 16/20px en cabecera y pie.

### Chips
- **Estilo:** píldora completa, 11px, semibold, fondo tintado y texto del mismo tono oscurecido.
- **Estado:** un chip de estado lleva **siempre** icono y palabra. El color acompaña, no informa solo.

### Navigation
- **Tabbar:** fija abajo, cinco columnas, cristal fuerte con `blur(30px) saturate(1.8)`,
  máximo 480px centrada, respetando el área segura. Cada destino ≥ 44px de alto.
- **Topbar:** sobre Negro de Bisel, con la marca a la izquierda y las acciones a la derecha.

### Medidor (componente propio)
Una franja de 6px que muestra una razón contra su límite. La pista es un paso claro del
**mismo** tono que el relleno, así el estado se lee a lo largo de toda la barra y no solo
en la parte llena. Cuando existe un objetivo por debajo del 100% lleva una marca vertical
en esa posición: es lo que convierte el color en algo que se puede aprender. Reemplazó a
los anillos de progreso, que competían por el ancho con la cifra.

### Selector de periodo (componente propio)
Una fila de chips en píldora —Mes · 4 sem · 3 meses · 6 meses— que cambia el alcance
de una lista sin recargar la página. Son `<button>` con `aria-pressed`, **no** un
`role="tablist"`: no hay cuatro paneles, hay una lista que cambia de contenido, y
anunciar pestañas que no existen le miente al lector de pantalla. El chip activo
lleva fondo índigo **y** peso 700, porque el estado no viaja solo en el color. Cada
chip mide 44px de alto y la fila envuelve antes que recortar.

Solo aparece cuando hay datos de más de un periodo, y **nunca** con la pantalla
degradada: ofrecer otras vistas de una cifra que no se pudo cargar es una invitación
a perder el tiempo.

### Named Rules

**La Regla del Enlace que Cumple.** Una fila se convierte en enlace solo cuando el
servidor ya probó que su destino existe. En el Top de Clientes el nombre puede venir
de QuickBooks y no tiene por qué coincidir con un `Cliente` local: la ruta resuelve el
nombre primero y la plantilla envuelve la fila en `<a>` únicamente si resolvió; si no,
queda como `<div>`. Y al revés: una fila que no lleva a ningún lado **no** se disfraza
de enlace con `cursor: pointer` ni con chevron. El Top de Productos es texto a
propósito, porque la única pantalla por producto que existe es el formulario de
edición del catálogo y no responde la pregunta que la fila despierta.

**La Regla del Formato de un Solo Dueño.** Cuando el mismo dato lo puede dibujar el
servidor y el navegador, lo **formatea el servidor** y el navegador solo imprime. No
es una preferencia: Python redondea 223,45 a «223.4» y JavaScript a «223.5», así que
una lista redibujada del lado del cliente cambiaba de dígito al volver al periodo con
el que había cargado. Por eso el JSON del Top viaja con `cajas_txt` y `peso_txt`
además del número — el número crudo queda para escalar la barra, no para mostrarse.

## Do's and Don'ts

### Do:
- **Do** pedir el tipo por rol (`--text-role-client`) y el color por token semántico
  (`--color-primary`), no por valor.
- **Do** dar 48px de alto mínimo a todo lo tocable, y 56px a lo que se opera con guante.
- **Do** poner los campos de formulario en 16px, sin excepción.
- **Do** acompañar todo color de estado con icono o palabra.
- **Do** separar marcas de dato con un hueco del color de la superficie (2px) en vez de un borde.
- **Do** elegir el gris del texto secundario según el fondo: `#64748b` sobre tarjeta, `#475569` sobre la pantalla.

### Don't:
- **Don't** usar fondo oscuro en el área de contenido. El oscuro es el marco.
- **Don't** declarar variables en `:root` fuera de `static/css/tokens.css`.
- **Don't** agregar `!important` a `static/css/dark-theme.css`; ya tiene 504 y cada uno
  nuevo hace más difícil que una pantalla pueda definir su propio color.
- **Don't** hardcodear hex en una hoja de pantalla cuando existe el token.
- **Don't** poner una franja de color de más de 1px en un lado de una tarjeta o un aviso.
- **Don't** usar un color de estado como serie de un gráfico, ni un color de serie para un estado.
- **Don't** animar `width`, `height`, `padding` ni `margin`; escalar con `transform`.
- **Don't** leer tokens de tema desde `document.body` en pantallas `.ops-*`: los tokens
  claros están scopeados a `.reg-wrap`/`.ops-*` y el body devuelve el token oscuro.

## Known Drift

Deuda real del sistema al 2026-08-30. No es guía de diseño: es el mapa de minas para
quien toque estas hojas.

- **`static/css/dark-theme.css` define su propio `:root`** (`--background-color`,
  `--text-dark`, `--bg-light`…) que compite con `tokens.css` y se carga después. Tiene
  **504 `!important`**. Es la causa conocida de que las pantallas nuevas tengan que
  blindar sus colores con paletas propias.
- **`static/css/app-mobile.css:988`** afirma «Default theme in this app is dark; light is
  an opt-in toggle». Es falso desde el 2026-08-28: no hay toggle y no hay modo oscuro.
- **Hex de estado hardcodeados: cerrado el 2026-08-30.** Los nueve valores medidos
  viven ahora en `tokens.css` como la familia `--mark-*` (`--mark-good`,
  `--mark-warning`, `--mark-critical`, con sus `-soft` y `-ink`), y el dashboard los
  consume por variable. El gráfico los lee de `:root` en JS con un literal de respaldo.
  Quedan hex de neutros (`#475569`, `#0f172a`, `#eef1f6`) sin variable propia.
- **Tres hojas se pisan en el dashboard** (`dashboard_inline` → `dashboard_light` →
  `dashboard_snap`) y el orden de carga es load-bearing.
- **El bloque móvil de `dashboard_snap.css`: cerrado el 2026-08-30.** Sus 17 hallazgos
  advisory se alinearon: los nueve `font-size` en rem a la escala (0.72→`--text-xs`,
  0.78 y 0.85→`--text-sm`, 1.2→`--text-lg`, 1.7 y 1.85→`--text-xl`, y el
  `clamp(1.7rem, 7vw, 2.1rem)` a `clamp(var(--text-xl), 7vw, 32px)`, que a 390px vale
  lo mismo que antes), los dos radios de 22px a `--radius-xl`, y los colores de estado
  del chip de tendencia a la familia `--mark-*`. **`.chart-big` bajó de 29,6px a 24px
  a propósito**: es la «cifra de segundo orden» que este documento define como
  headline, y con 27–33 contra 29,6 no se distinguía de la cifra del KPI.
- **El acento del dashboard NO es el Índigo de Lectura.** El `<body>` lleva
  `data-hue="blue"`, y ese selector de `tokens.css` reescribe `--indigo-500` a
  **`#2563eb`** y `--indigo-300` a `#93c5fd`. O sea que el kicker del hero y los
  enlaces de sección se pintan de un azul que este documento no declara, mientras el
  resto de la app usa `#6366f1`. Salió a la luz al quitar los literales
  `var(--indigo-500, #2563eb)` de `dashboard_snap.css`: el valor de respaldo se fue,
  pero el color en pantalla sigue siendo el mismo. Hay que decidir cuál de los dos es
  el correcto; mientras tanto, `--indigo-400` y `--indigo-700` **sí** valen lo que
  dicen (ningún `data-hue` los toca) y son los que usa el gráfico.
- **No hay tokens de breakpoint.** Los cortes 768/900/1024 se repiten a mano.
- **Conviven dos familias de estado.** La nominal (`--color-success`/`-warning`/
  `-danger` con sus `-soft`) la usan diez hojas y sirve para pintar un estado solo; la
  medida (`--mark-*`) sirve cuando dos estados tienen que distinguirse entre sí. No se
  fusionaron porque cambiar los `-soft` existentes tocaría pantallas que no se
  auditaron. Al elegir: ¿este color convive con otro estado a la vista? `--mark-*`.
- **Tamaños y radios del dashboard: cerrado el 2026-08-30.** Los 27 valores fuera de
  escala (12px ×12, 14px ×3, 22px, 18px, 9px, y radios de 1, 2, 3, 6 y 10px) se
  alinearon a `tokens.css`. Queda un único hallazgo del detector, y es un falso
  positivo: lee la plantilla sin poder resolver `{{ url_for('static', ...) }}`, así que
  no carga las hojas y asume texto negro en un `<div>` que hereda `#0f172a`.
