---
target: maquila
total_score: 27
max_score: 40
na_heuristics:
p0_count: 0
p1_count: 2
timestamp: 2026-09-06T22-45-21Z
slug: templates-maquila
---

# Crítica — /maquila (módulo completo, 16 pantallas)

**Fecha:** 2026-09-06 · **Método:** un solo hilo (revisión de diseño + detector +
navegador real). **Desviación del método habitual:** la skill `impeccable` no
está instalada en esta sesión remota —es un plugin local— así que no hubo
dual-agent ni script de overlay. Se reconstruyó el procedimiento contra
`.impeccable/design.json` (que sí está versionado) y se midió con Chromium
sobre la app corriendo con datos sembrados. Todo número de este documento sale
de una medición o de una línea de código citada.

**Objetivo:** `templates/maquila/*.html` (20 plantillas), `static/css/maquila.css`
(1.610 líneas), `maquila/routes.py`, `maquila/servicios.py`.
**Modo:** Operate · **Salud de diseño: 27/40** (las diez heurísticas aplican).

## Salud de diseño

| # | Heurística | Pts | Hallazgo que fija la nota |
|---|---|---|---|
| 1 | Visibilidad del estado | 3 | La franja del total, el chip «Desactualizado: recalculá» y el aviso pegado al botón dicen siempre por qué el cierre está bloqueado. |
| 2 | Correspondencia con el mundo real | 3 | Habla como la planta (corrida, lote, cámara, merma, custodia) y vosea sin fisuras. Pero el campo de fecha se pinta en la locale del navegador. |
| 3 | Control y libertad | 3 | Nada se borra nunca; anular devuelve al saldo; corregir exige motivo. La salida de la pantalla de cierre es un enlace de 16px dentro de una frase. |
| 4 | Consistencia y estándares | 2 | 65 % de los destinos táctiles miden 44px donde el sistema manda 48; ~40 hex a mano donde ya hay token. |
| 5 | Prevención de errores | 4 | Lo mejor del módulo. Firma obligatoria, doble cierre imposible, «Real» sin precargar a propósito, botón deshabilitado hasta que el reparto refleje lo declarado. |
| 6 | Reconocer antes que recordar | 2 | Diez destinos en un riel de 1.063px dentro de 356px: tres visibles, 707px fuera de cuadro. |
| 7 | Flexibilidad y eficiencia | 2 | «Copiar el teórico» es el único atajo. Cada caja pesada es un POST con recarga completa. |
| 8 | Estético y minimalista | 2 | 162 palabras de prosa antes del primer campo en la pantalla de cierre. |
| 9 | Diagnóstico y recuperación | 3 | Cada ruta atrapa su excepción y el mensaje dice qué se conservó. |
| 10 | Ayuda y documentación | 3 | La prosa *es* la documentación, en su sitio y correcta. Explica de más, pero nunca miente. |
| **Total** | | **27/40** | **Bueno — refinamiento dirigido, no rediseño.** |

Para calibrar: el dashboard sacó 12/40 el 2026-08-30. Este módulo está en otra
categoría. La nota no premia el gusto; premia que la pantalla haga su trabajo.

## Veredicto de especificidad

**Irremplazable.** Es el veredicto opuesto al del dashboard, y merece decirse
con todas las letras: no se puede cambiar cuatro rótulos y vender esto como
otra cosa. «Inventario en custodia de» arriba de cada pantalla que toca números
ajenos; el reparto FIFO que nombra de qué recepción y de qué lote del cliente
sale cada kilo; la merma contra la receta con su umbral; la firma de quien
descontó. Y la frase que resume el criterio del módulo entero, en
`corrida_cerrar.html:41`:

> «no viene precargado a propósito, para que el rendimiento mida lo que salió
> de la cámara y no lo que dice la receta»

Eso es una decisión de negocio defendida dentro de la interfaz. No sale de
ninguna librería.

## Evidencia mecánica

Chromium real, sesión iniciada, 16 rutas × 2 breakpoints (390×844 con
`is_mobile`, 1440×900), contraste calculado contra el píxel de fondo pintado
—no contra el `background-color` declarado.

- **1.274 pares texto/fondo medidos. Cero fallas AA. Peor caso: 4,76:1**
  (`#64748b` sobre blanco, en `.ops-firma-label`), que es exactamente el piso
  que `DESIGN.md` nombra como tinta-tenue. La Regla de los Dos Grises se
  cumple en las 16 pantallas.
- **Texto más chico medido: 11,0px.** La Regla del Piso de 11px se cumple sin
  excepción.
- **646 destinos táctiles medidos. 423 (65 %) miden exactamente 44,0px de alto.**
  Ver P1-1.
- **Cero desbordes horizontales de página**: `document.scrollWidth == 390` en
  las 16 rutas.
- **`tests/`: 1.112 pasan, 1 salteado, 0 fallos** (229s). De esos, 186 son del
  módulo de maquila.

**Falsos positivos que maté antes de escribirlos** (van acá porque el detector
crudo los reporta y son trampas conocidas de este código):

1. *«La casilla de quitar caja mide 20×20px»* — **falso**. La casilla está
   dentro de su `<label class="rec-quitar">` (`corrida_editar.html:106`), que
   mide 44×107,7. El destino real es la píldora, no la casilla.
2. *«Hay 484px de contenido inalcanzable en Rendimiento»* — **falso**. El
   scroller de la app es `document.body`, no la ventana, así que `window.scrollY`
   se queda en 0 y `documentElement.scrollHeight` no representa nada. Con
   `body.scrollTop` al máximo, las 16 pantallas llegan al final.
3. *«Hay contenido bajo el fold en Corrida cerrada y Cerrar corrida»* — **falso**.
   Son los `<thead>` que el patrón de fichas móviles esconde con
   `position:absolute; clip:rect(0 0 0 0)` (`maquila.css:425`). Están fuera de
   pantalla a propósito y su contenido ya viaja en el `data-label` de cada celda.
4. *«La regla `font-size:10px` del chip del kardex rompe el piso de 11px»* —
   **muerta**. `maquila.css:1283` la declara y `:1399` la pisa a 11px desde un
   media query posterior del mismo ancho. Es código muerto, no un bug visible.
5. *Errores de consola* — 3 por página, todos `ERR_TUNNEL_CONNECTION_FAILED`.
   Es el proxy de este entorno bloqueando CDNs, no la app. Ver Menores.

## Lo que está funcionando

1. **El botón de cierre no se habilita hasta que la pantalla dice la verdad.**
   `corrida_cerrar.html:298-317` exige dos cosas a la vez: que el reparto
   refleje lo declarado (sin ediciones posteriores) y que haya firma. Si editás
   un consumo después de recalcular, el chip pasa a «Desactualizado», la franja
   del total se marca, el `<details>` se marca y el aviso del pie cambia de
   texto para decir cuál de las dos falta. Es la única pantalla de la app que
   se niega a dejarte confirmar un número que ella misma sabe viejo.

2. **El ledger no borra nunca, y la interfaz lo sostiene.** Quitar una línea de
   recepción escribe su inverso (`models.py:80-86`); anular una corrida devuelve
   cada consumo al saldo; corregir exige motivo. Y `lineas_vivas` existe para
   que un total en pantalla no cuente lo que el rastro ya dejó en cero — el
   número mostrado y el rastro no pueden divergir por construcción.

3. **El banner de dueño.** `_macros.html:37-49` pone «Inventario en custodia de
   {cliente}» arriba de toda pantalla que opera sobre material ajeno, antes de
   cualquier cifra. Es una línea de markup que convierte «descontar 96 kg» en
   «descontar 96 kg de Carnicos del Caribe NV». En una maquila eso no es
   decoración: es el encuadre legal de la operación.

4. **El saldo insuficiente no es un callejón.** `routes.py:891-901` manda el
   `ingrediente_id` que faltó en la query string y la pantalla ofrece
   «Registrar el ajuste» ya precargado con cliente e ingrediente, conservando
   lo declarado. El error trae su remedio a un toque.

## Prioridades

### [P1] El piso táctil del módulo es 44px; el sistema dice 48, y 56 con guante

**Medido:** de 646 destinos táctiles en las 16 pantallas, **423 (65 %) miden
exactamente 44,0px de alto**. Son los diez enlaces del nav, todos los `select` e
`input` de formulario, las píldoras «Quitar», «Borrar firma» del pad, los tres
campos «Real» de la pantalla de cierre y los enlaces Saldos/Kardex del banner de
dueño. `design.json` fija 48px como mínimo para todo lo tocable y 56px para lo
que se opera con guante (`ds-btn-primary` es `min-height:48px`, `ds-btn-glove`
es 56px, `ds-input` es 52px).

Lo que convierte esto en P1 y no en una diferencia de 4px: **el código cree que
ya cumple**. `maquila.css:170` dice literalmente

```css
/* 44px de alto: el mínimo táctil, y esto se opera con guantes. */
min-height: 44px;
```

y `:564` repite el argumento («no se podía tocar con guante») justificando otros
44px. Es el número genérico de iOS aplicado donde el sistema tiene dos números
propios, más grandes, y precisamente por el guante. Nueve declaraciones lo
repiten; una sola (`.maquila-reparto-ing > summary`, `:1471`) usa 48.

Peores casos por debajo incluso de esos 44px, todos en móvil de 390px:
- el campo de peso de cada caja en «Corregir corrida»: **40,0 × 67,3px**, ocho
  veces en la misma pantalla (`maquila.css` no lo alcanza; hereda de la grilla);
- el nombre del cliente en la tarjeta del Resumen, que es el enlace a Saldos:
  **24,0 × 252,9px** — `:1496` le dio 44px a los enlaces meta de esa tarjeta y
  se olvidó del título;
- los enlaces en prosa «corrida» (**16,0 × 48,9px**, en Cerrar corrida) y
  «kardex» (**16,0 × 47,5px**, en Recepción detalle).

**Por qué importa:** esto se usa en cámara, con el guante puesto y el teléfono
en una mano. El campo «Real» de 44px es donde se teclea el número que descuenta
inventario ajeno.

**Arreglo:** subir el piso del módulo a 48px y llevar a 56px lo que se opera con
guante —los campos «Real» del cierre, el peso de caja y las píldoras «Quitar»—.
Al título de la tarjeta del Resumen, el mismo tratamiento de padding con margen
negativo que ya tienen sus enlaces meta. Y corregir los dos comentarios: dicen
«el mínimo táctil» sobre un número que no lo es en este sistema.

### [P1] La pantalla de mayor consecuencia arranca sin un solo campo a la vista

**Medido en 390×844:** «Cerrar corrida» carga con **162 palabras de prosa
repartidas en 6 bloques**, y el primer campo «Real» está a **y=745 en un
viewport de 844** — debajo del pie sticky, que ya ocupa la franja inferior. La
captura de pantalla completa lo confirma: la primera pantalla es topbar, título,
riel de nav, banner de dueño, ficha de la corrida con su párrafo, el encabezado
«Consumo real», cinco líneas más de explicación… y el pie. Cero entradas.

Para comparar, en el mismo teléfono: «Recepción nueva» tiene 82 palabras y su
primer campo a y=352; «Corregir corrida», 49 palabras y y=402.

**Por qué importa:** la prosa es buena y es cierta —explica por qué «Real» no
viene precargado, algo que un operario nuevo necesita saber una vez—. El
problema es que no se retira nunca. Quien cierra corridas todos los días paga
745px de scroll cada vez para llegar al primer número, en la única pantalla del
módulo que mueve inventario de un tercero.

**Arreglo:** que la tabla de consumo sea lo primero después del banner de dueño,
y que las dos explicaciones largas (`:41` y la del reparto) vivan en un
`<details>` plegado con un resumen de una línea —el módulo ya usa ese patrón,
bien, en el reparto por ingrediente—. La ficha de la corrida se comprime a la
línea meta que ya existe (`producto · lote · 96,69 kg en 8 cajas`); su párrafo
repite lo que el pie ya dice.

### [P2] Diez destinos en un riel de 1.063px dentro de 356px, y tres caen en un selector vacío

**Medido:** el nav de `base_maquila.html` mide **1.063px de scrollWidth en 356px
de ancho útil**. Con la sección activa centrada por el script de `:44-52`,
**tres de los diez destinos son visibles**; 707px quedan fuera de cuadro. La
agrupación en tres bloques con separador es la decisión correcta y está bien
argumentada en el comentario, pero no cambia la aritmética en un teléfono.

Peor: **Saldos, Kardex y Trazabilidad no muestran nada al llegar.** Los dos
primeros abren con «Elegí un cliente para ver sus saldos» y un `select`
(`reporte_saldos.html:29`); Trazabilidad, con un buscador vacío. Tres de diez
destinos del nav principal cuestan un toque para llegar a un segundo toque.

**Arreglo:** el riel lleva cuatro destinos de operación (Resumen, Recepciones,
Producción, Ajustes). Los seis restantes son configuración y consulta: van
detrás de un único destino «Más» o —mejor— desaparecen del nav y se alcanzan
desde donde ya tienen contexto, que es como el módulo ya lo hace bien: el banner
de dueño ofrece Saldos y Kardex del cliente que estás mirando, con el cliente ya
elegido.

### [P2] El estado de una recepción solo mira los kilos, y lo dice en verde

`routes.py:404-409` calcula `queda` filtrando `unidad == 'kg'`. El filtro es
correcto —sumar kilos con unidades da un número que no es nada, y el docstring
de `totales_por_unidad` lo dice—. Pero `recepciones.html:41-45` usa ese mismo
valor kg-only para pintar el **chip de estado de la fila entera**: «Sin
consumir» (verde), «Consumida N %» o «Agotada».

Consecuencia verificable con datos reales: una recepción de 240 kg de carne + 600
unidades de tripa, con la tripa entera consumida y la carne intacta, muestra
**«Sin consumir» en verde** — mientras la celda de al lado, «Recibido», sí
imprime `240 kg · 600 ud`. La misma fila declara que hay unidades y afirma que
no se tocó nada.

**Por qué importa:** rompe La Regla del Estado Reservado por el lado que menos
se vigila. El verde no está mal usado como color; está diciendo algo falso. Y
la tripa es justo el insumo que se agota antes que la carne.

**Arreglo:** o el chip se calcula sobre todas las unidades (el porcentaje, por
la peor de ellas), o dice explícitamente su alcance: «Carne sin consumir» /
«Sin consumir (peso)». Si hay unidades fuera del balance, un segundo chip
neutro que lo diga — el módulo ya usa ese recurso, y bien, en el reporte de
rendimiento: «+ consumo en ud, fuera del balance de peso».

### [P2] Colores de estado usados como colores de tipo

`_macros.html:26-27`, `chip_tipo_movimiento`:

```jinja
{%- set tonos = {'entrada': 'conforme', 'salida': 'neutro',
                 'ajuste': 'aviso', 'devolucion': 'marca'} -%}
```

Una entrada de inventario no es un estado «conforme» y un ajuste no es un
«aviso»: son tipos de movimiento. Verde y ámbar están funcionando acá como la
tercera y cuarta serie de una paleta categórica, que es exactamente lo que
prohíbe la regla («Verde, ámbar y rojo significan estado y nada más. Nunca son
"el cuarto color de la serie"»). En el kardex, donde estos chips se apilan en
columna, la lectura resultante es que las entradas están bien y los ajustes
preocupan.

**Arreglo:** los cuatro tipos van en gris o en índigo (que es identidad, no
estado) diferenciados por la palabra, que ya llevan. El verde queda libre para
lo que sí es un estado en esa tabla.

### [P3] Hex a mano donde el token ya existe

~40 literales hexadecimales en `maquila.css` (`#9f1239`, `#fffbeb`, `#4338ca`,
`#be123c`, `#065f46`…), casi todos valores que ya están en las rampas de
`design.json`. Es un «Don't» explícito del sistema: *«Don't hardcodear hex en
una hoja de pantalla cuando existe el token»*. No se ve hoy —el contraste da
perfecto—, y esa es justamente la razón por la que conviene arreglarlo ahora:
el día que la rampa de falla cambie, esta hoja se queda atrás en silencio.

La cabecera del archivo (`:1-27`) documenta con precisión por qué
`.maquila-wrap` redefine la paleta clara en vez de tocar `operaciones.css`. Ese
razonamiento es correcto y está bien ganado; el resto del archivo debería
consumir esas variables en lugar de repetir sus valores.

### [P3] El campo de fecha se pinta en la locale del navegador, no en la del módulo

Todo lo que el módulo **imprime** es `dd/mm/yyyy` (`strftime('%d/%m/%Y')`, 14
apariciones). Todo lo que el módulo **pide** es un `<input type="date">` nativo,
cuyo formato lo decide la locale del navegador y no `<html lang="es">`. En este
entorno se renderiza **`09/06/2026` para el 6 de septiembre** — mm/dd/yyyy.

**Salvedad honesta:** el Chromium de este contenedor ignora el parámetro de
locale (las capturas con `en-US`, `nl-NL`, `es-ES` y `pap-CW` salen idénticas,
mismo md5), así que **no verifiqué que un iPhone de Curazao muestre mm/dd**. Lo
que sí queda verificado es que la app no controla ese formato y que el módulo
imprime uno distinto del que este navegador ofrece para teclear.

**Por qué vale nombrarlo igual:** los dos campos afectados son «Fecha de
producción» y «Fecha de vencimiento» de un producto cárnico. 05/09 contra 09/05
son cuatro meses de vida útil.

**Arreglo barato y verificable:** una etiqueta de formato bajo cada campo de
fecha del módulo, tomada del propio navegador
(`new Intl.DateTimeFormat().resolvedOptions()`), o eco de la fecha elegida en
prosa («vence el 21 de octubre de 2026») debajo del campo.

## Banderas por persona

**El operario de cámara, con guante, teléfono en una mano.** Su pantalla es
«Cerrar corrida». Llega y no ve un campo: el primero está a 745px. Cuando llega,
mide 44px de alto —el sistema le prometió 56— y tiene 271px de ancho para un
número de tres decimales. Si edita un consumo después de recalcular, el módulo
lo protege bien: el botón se apaga y el aviso le dice por qué. Si el saldo no
alcanza, lo mandan al ajuste con el ingrediente ya elegido. La protección es
excelente; el alcance físico es el que está corto.

**Quien corrige una corrida cerrada.** Ocho campos de peso de 40×67px, ocho
píldoras «Quitar» de 44px, y un campo «Motivo de la corrección (obligatorio)»
cuya etiqueta mide 28px de alto. Es la pantalla con más destinos táctiles del
módulo y la que los tiene más chicos.

**El auditor.** Es a quien mejor sirve el módulo, y no por accidente: la
cabecera de Trazabilidad imprime término, fecha, hora, quién consultó y «Jomar
Foods», con `maquila-no-imprimir` en el formulario para que el papel salga
limpio. El recibo de cierre dice qué se descontó, de qué recepción, con qué lote
del cliente y quién firmó. Eso está terminado.

**Quien entra por primera vez.** Ve diez destinos de los que tres caben en
pantalla, y si toca los tres del final del riel encuentra selectores vacíos.

## Menores de nota

- **Tres recursos de CDN por página** (`base.html:66`, `:69`, `:573` —
  font-awesome, tom-select CSS y JS). En este entorno los tres fallaron y las 16
  pantallas de maquila se renderizaron correctamente: el módulo no los usa. Para
  una app cuyo propio código dice «en ruta la señal falla», son tres bloqueos de
  render de terceros que este módulo paga sin consumir.
- `_leer_consumos_form` (`routes.py:272-282`) **descarta en silencio** los ceros
  y los negativos. Declarar `0` en un ingrediente que la receta pide no es un
  error visible: simplemente no se descuenta. La columna «Diferencia» lo marca
  en rojo, pero la franja del total —el número que se confirma— lo omite sin
  decirlo.
- El consumo declarado viaja **en la query string** entre «Recalcular» y la
  pantalla de cierre (`c<id>=<cantidad>`). La razón está bien argumentada (F5 no
  reenvía un POST), pero deja cantidades de negocio en el historial del
  navegador y en cualquier log de accesos.
- `maquila.css:1283` declara `font-size:10px` para el chip del kardex; `:1399`
  lo pisa a 11px. Regla muerta, borrarla.
- `.maquila-wrap` fija `min-height:100vh` (`:39`): en las cuatro pantallas que
  hoy abren vacías (Saldos, Kardex, Trazabilidad, Ajustes) eso son ~440px de
  blanco bajo un párrafo de una línea.
- La firma usa un color fijo `TINTA = '#0f172a'` con un comentario que explica
  exactamente por qué no puede leer el token del body. La explicación es
  correcta; el valor sigue siendo un hex a mano que nadie va a encontrar cuando
  cambie la tinta.
- Pesar cada caja es un POST con recarga completa de página. Con ocho cajas son
  ocho recargas; el ancla `#peso` mitiga bien la pérdida de posición, pero el
  patrón no escala a una corrida de treinta cajas.
- El escritorio de 1440px reparte el mismo layout de una columna: `Recepciones`
  y `Producción` terminan su contenido en y=501 de 900px de alto.

## Preguntas para pensar

1. La prosa de este módulo es lo mejor escrito de la app —dice *por qué*, no
   *qué*—. ¿Cómo se retira sola después de la tercera vez que alguien cierra una
   corrida, sin perderla para el cuarto operario que entre?
2. El sistema fija 48px y 56px con guante, y este módulo —el único que
   literalmente se opera con guante— usa 44px en el 65 % de sus destinos,
   argumentando el guante en el comentario. ¿Falla el módulo o falla la manera
   en que el sistema comunica esos dos números?
3. `/maquila` muestra una tarjeta por cliente con «1 corrida abierta» como
   enlace. Si esa corrida está abierta desde hace tres días con ocho cajas
   pesadas y sin cerrar, ¿debería la tarjeta decirlo? El módulo mide merma con
   precisión quirúrgica y no mide el tiempo que un descuento lleva sin
   registrarse.
4. El reparto FIFO se muestra pero no se puede editar: `cerrar_corrida` acepta
   `reparto_manual` y ninguna ruta se lo pasa (`servicios.py:800-804`). ¿Qué
   pasa el día que el operario sabe que sacó de la recepción nueva porque la
   vieja estaba al fondo de la cámara?
5. Tres de los diez destinos del nav abren en un selector vacío, y el banner de
   dueño ya lleva a esos mismos reportes con el cliente puesto. ¿Para qué está
   el riel?

## Salvedades

- La skill `impeccable` no corrió: no está instalada en esta sesión remota. No
  hubo dual-agent, ni script de overlay, ni detector determinista propio. Las
  mediciones son de un script escrito para esta revisión contra Chromium real.
- Datos sembrados por mí (dos clientes, tres ingredientes con dos unidades
  distintas, una receta, dos recepciones, una corrida abierta con 8 cajas y una
  cerrada con consumo declarado). Los caminos que mis datos no tocan —recepción
  anulada, corrida anulada, cajas ya asignadas a un pedido facturado— se leyeron
  en el código, no en pantalla.
- CSP de producción sin ejercitar: Talisman solo monta con
  `FLASK_ENV == "production"` (`app.py:371`).
- La locale del navegador no es configurable en este contenedor; el hallazgo de
  formato de fecha queda acotado a lo que sí se verificó.
