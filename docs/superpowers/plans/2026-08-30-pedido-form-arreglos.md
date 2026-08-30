# Arreglos del formulario de pedido — plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: superpowers:subagent-driven-development.

**Goal:** cerrar los seis problemas prioritarios y los menores que encontró la
crítica Impeccable de `/pedidos/nuevo`, sin cambiar lo que se le envía a
QuickBooks.

**Crítica de origen:** `.impeccable/critique/2026-08-30T02-59-09Z__templates-pedido-form-html.md`

**Architecture:** el flujo vive en `templates/pedido_form.html` (742 líneas,
pasos 3 y 4, con su JS inline), `templates/pedido_cliente.html` (pasos 1 y 2) y
`static/css/pedido_nuevo.css`. El servidor lo arma `nuevo_pedido` en `app.py`.
Casi todo el trabajo es de plantilla y JS; solo la tarea 1 toca lógica de
servidor, y solo para EXPONER un dato que ya existe.

## Global Constraints

- **No cambiar el payload que se le manda a QuickBooks.** Ni el `tax_rate` de
  línea, ni `_tax_code_de_linea`, ni `pedido_a_json`. Todo lo de acá es lo que
  el vendedor VE, no lo que se factura. Un cambio en el payload es un defecto.
- **`tax_rate` es un CÓDIGO de QuickBooks, no un porcentaje.** La traducción
  correcta, tomada de `templates/productos.html:108`, es: **código 10 → OB 6%**,
  **código 14 → OB 0%**. En producción existen solo esos dos (41 y 23
  productos). Escribir «Impuesto 14 = 14%» es el error que ya se cometió una vez.
- `precio_base` se guarda **tax-exclusive**: QuickBooks aplica el OB encima.
- Todo `<script>` inline lleva `nonce="{{ csp_nonce() }}"` o no ejecuta.
- Contraste mínimo 4,5:1 (3:1 desde 18px); área táctil ≥44×44.
- La app se usa como **PWA instalada en iPhone**; el ancho real es 390px.
- Correr `.venv/bin/python -m pytest tests/ -q`, **sin** forzar `DATABASE_URL`.
- Hay tests acoplados al markup de este flujo en `tests/test_pedido_dos_pasos.py`
  y `tests/test_pedido_habitual.py`: si se ponen rojos, LEERLOS antes de tocarlos.

---

### Task 1: El impuesto, con un solo dueño

Hoy la traducción código→porcentaje está **duplicada en tres plantillas**
(`productos.html:71,108`, `editar_producto.html:92`) y ausente del formulario de
pedido, que muestra el código crudo. Esta tarea le da un dueño único y lo usa.

**Files:** `app.py`, `templates/pedido_form.html`, `templates/productos.html`,
`templates/editar_producto.html`, `tests/test_pedido_impuesto.py` (crear)

**Interfaces:**
- `_ob_de_codigo(codigo) -> dict` con `{'pct': 6.0, 'etiqueta': 'OB 6%'}`.
  Código desconocido → `{'pct': None, 'etiqueta': 'Tax <n>'}` y **nunca** asume
  0: un código que no conocemos no es "sin impuesto".

- [ ] **Paso 1: tests que fallan**

```python
def test_los_dos_codigos_de_produccion_se_traducen():
    assert _ob_de_codigo(10) == {'pct': 6.0, 'etiqueta': 'OB 6%'}
    assert _ob_de_codigo(14) == {'pct': 0.0, 'etiqueta': 'OB 0%'}


def test_un_codigo_desconocido_no_se_asume_exento():
    """Asumir 0% en un código que no conocemos es inventar que no paga
    impuesto, y eso se le canta al cliente como precio final."""
    r = _ob_de_codigo(99)
    assert r['pct'] is None
    assert '99' in r['etiqueta']


def test_la_etiqueta_del_grupo_deja_de_ser_el_codigo_crudo():
    """El código no le dice nada al vendedor; el propio app.py lo advierte
    tres veces. La app YA traduce en /productos: acá se reusa."""
    assert _etiqueta_grupo(10) == 'OB 6%'
    assert _etiqueta_grupo(14) == 'OB 0%'
```

- [ ] **Paso 2:** correr, ver que falla por `ImportError`.

- [ ] **Paso 3: implementar.** En `app.py`, junto a `_etiqueta_grupo`:

```python
# Los tax_rate son CÓDIGOS de QuickBooks, no porcentajes. La traducción vivía
# duplicada en tres plantillas (productos.html, editar_producto.html) y no
# existía en el formulario de pedido, que mostraba el código crudo — el dato
# que los comentarios de este archivo describen como «no le dice nada al
# vendedor». Un solo dueño, y se usa en los tres lados.
_OB_POR_CODIGO = {10: 6.0, 14: 0.0}


def _ob_de_codigo(codigo):
    """Porcentaje de OB y etiqueta legible de un código de impuesto de QBO."""
    try:
        cod = int(codigo)
    except (TypeError, ValueError):
        return {'pct': None, 'etiqueta': '—'}
    pct = _OB_POR_CODIGO.get(cod)
    if pct is None:
        # Un código que no conocemos NO es 0%: decir «sin impuesto» de algo que
        # sí lo paga le hace cantar al vendedor un precio que la factura
        # desmiente.
        return {'pct': None, 'etiqueta': f'Tax {cod}'}
    return {'pct': pct, 'etiqueta': f'OB {pct:g}%'}
```

y `_etiqueta_grupo` devuelve `_ob_de_codigo(grupo)['etiqueta']`.

Reemplazar las condicionales duplicadas de `productos.html` y
`editar_producto.html` por esta función (exponerla como filtro Jinja o pasar el
valor ya resuelto desde la vista).

- [ ] **Paso 4: el total de la revisión deja de mentir.**

`pedido_form.html:128-130` imprime «Total XCG» sobre un subtotal. Pasar a tres
filas, con el **total inclusivo** como cifra grande:

```
Subtotal        78.96
OB 6%            4.74
Total XCG       83.70
```

Cuando el OB es 0% (grupo 14) **no dibujar la fila de OB**: una línea que dice
«OB 0% — 0.00» es ruido. Cuando el porcentaje es desconocido, no inventar
total: mostrar «Subtotal» y una nota de que la factura suma el impuesto.

El footer del paso 3 mantiene el subtotal, pero rotulado **SUBTOTAL**, no un
número desnudo.

- [ ] **Paso 5:** tests de render que afirmen los NÚMEROS, no los rótulos (el
      rótulo «Subtotal» se satisface con la plantilla rota). Anclar a la fila.
- [ ] **Paso 6:** commit.

---

### Task 2: El lote mecánico

Todo lo que no necesita decisión y se mide.

**Files:** `templates/pedido_form.html`, `static/css/pedido_nuevo.css`

- [ ] **La entrega por defecto salta el fin de semana.** `pedido_form.html:263`
  crea `manana` sin pasar por el `while (getDay()===0||getDay()===6)` que la
  línea 269 sí aplica al tercer chip. El código ya sabe que no hay reparto el
  fin de semana. Pasar `manana` por el mismo filtro y, cuando no sea
  literalmente mañana, rotular el chip con el día («Lun 31»).
- [ ] **`.pn-grupo-chip` mide 131×40** — subir a ≥44 de alto.
- [ ] **`--pn-apagado` (`#a8a8a0` sobre `#fbfbf9`) da 2,3:1** y es el nombre del
  producto que se acaba de quitar: el único texto que dice qué se sacó.
  Oscurecer hasta ≥4,5:1 **midiendo contra el fondo real**, no contra blanco.
- [ ] **Unidad visible en las cantidades.** «· 4» no dice cajas en ningún lado
  salvo en un `aria-label`. Que se lea la unidad en la línea y en la revisión.
- [ ] **Plurales.** `app.py:6624` «Compra cada {n} días» y `app.py:6640`
  «en {n} grupos» no tienen singular.
- [ ] **`outline: none` sin reemplazo** en `.pn-buscador input`, `.pn-add-cajas`,
  `.pn-fecha-otra`, `.pn-notas`, más las dos reglas que anulan el anillo de Tom
  Select. Poner un `:focus-visible` visible.
- [ ] **Escritorio:** el flujo no tiene `max-width` y a 1280px quedan 1.100px
  entre el producto y su precio. Acotar el ancho de contenido.
- [ ] **El desplegable de productos tapa** el botón «Añadir» (71%) y la etiqueta
  «Entrega» (79%). Que no se superpongan.
- [ ] Commit.

---

### Task 3: No perder el pedido

**Files:** `templates/pedido_form.html`

- [ ] **El paso 4 entra al historial.** `mostrarPaso('revision')` solo togglea
  `hidden`. En la PWA instalada el swipe desde el borde sale del formulario y
  destruye el pedido. `history.pushState` al entrar en revisión y un `popstate`
  que vuelva al paso 3.
- [ ] **`beforeunload`** mientras haya líneas activas y no se esté enviando.
- [ ] **Borrador en `localStorage`**, clave `borrador:<cliente>:<grupo>`, con
  líneas, fecha y notas, guardado en cada cambio. Al entrar al paso 3, si hay
  borrador, ofrecer seguirlo. Borrarlo al enviar con éxito.
- [ ] Tests del contrato (que el JS exista y haga lo que dice) y verificación
  real en el navegador en la Task 6.
- [ ] Commit.

---

### Task 4: El envío que puede fallar

**Files:** `templates/pedido_form.html`, `app.py`

- [ ] **Enviar por `fetch`** en vez de POST clásico, y ante fallo de red mostrar
  el error **dentro** del shell hueso/tinta: «Sin señal. El pedido quedó
  guardado», con reintento. Hoy un corte muestra la página de error del
  navegador y se pierde todo.
- [ ] **El flash de éxito deja de mentir.** `app.py:6906` dice siempre «Pedido
  creado con precios registrados», también sobre un pedido con líneas SIN
  PRECIO y total 0.00. Hacerlo condicional.
- [ ] **La confirmación no cambia de mundo visual.** Hoy redirige a `/pedidos`,
  otra tipografía y otras tarjetas. Confirmar dentro del shell: número de
  pedido, cliente, entrega, líneas y total, más el aviso de sin-precio si
  aplica, y dos salidas: otro pedido de este cliente, o volver a la lista.
- [ ] Commit.

**NO se incluye un service worker.** Es la única pieza del P1 que queda fuera y
es deliberado: agregar un SW a una PWA **ya instalada** en el teléfono de dos
personas puede servir HTML o JS viejo indefinidamente si se cachea mal, y la
salida es borrar los datos del sitio — caro en una app que factura. El borrador
más el reintento cubren la pérdida real (el pedido en curso). Si JM quiere el
encolado offline completo, es su decisión y va aparte.

---

### Task 5: El paso del grupo deja de ser un peaje

**Files:** `app.py`, `templates/pedido_cliente.html`

- [ ] **Si el cliente tiene historial en un solo grupo, entrar directo a ese
  grupo**, con el chip visible y reversible. 27 de 49 clientes compran de uno
  solo y hoy pagan la pantalla en cada visita. La pregunta pasa a ser una
  consecuencia reversible, no un peaje. **Ojo:** el cliente sin historial sigue
  eligiendo, y el chip tiene que dejar cambiar de grupo siempre.
- [ ] **Los ejemplos de cada grupo son los del catálogo en orden alfabético e
  idénticos para los 62 clientes.** Usar los productos que **este** cliente
  compra; si no tiene historial, recién ahí el catálogo.
- [ ] **El banner explica la restricción y nunca el remedio.** Al terminar un
  pedido de un cliente que compra de ambos grupos, ofrecer tomar el otro.
- [ ] Tests de las tres conductas. Commit.

---

### Task 6: Verificación en el navegador

Levantar la app local (`SECRET_KEY=preview-secret FLASK_ENV=preview
DATABASE_URL=sqlite:///$(pwd)/instance/local.db`, puerto 5002, `admin` /
`Preview123!`) y **medir el render, no las reglas**, a 390px y 1280px:

- [ ] Contraste de cada texto del flujo, **componiendo el fondo contra los
      ancestros**. Un `background-image` con degradado pinta por encima del
      `background-color`: medir solo `backgroundColor` da falsos «blanco sobre
      blanco». Ya pasó en este proyecto.
- [ ] Área táctil ≥44×44 de todo control.
- [ ] El swipe-back de la revisión (simular `history.back()`) **no** pierde el
      pedido.
- [ ] El borrador sobrevive a recargar la página.
- [ ] El fallo de envío se ve dentro del shell (simular con la red cortada).
- [ ] El total de la revisión coincide con subtotal + OB, y el grupo 14 no
      dibuja fila de OB.
- [ ] Capturas a los dos anchos, y mirarlas.
- [ ] Un lote de arreglos, una confirmación, y parar.

## Nota para quien ejecute

No deducir el estado de una regla CSS ni de una propiedad que uno mismo seteó.
En este repo ya pasó tres veces: `[hidden]` perdiendo contra un `display` de
autor, un `sticky` inerte, y un `color` pisado mientras
`-webkit-text-fill-color` seguía pintando. Medir lo que se ve.

Y para cada test que escribas, preguntate qué substring exacto lo satisface: en
el trabajo anterior aparecieron siete tests que nombraban lo que protegían sin
protegerlo.
