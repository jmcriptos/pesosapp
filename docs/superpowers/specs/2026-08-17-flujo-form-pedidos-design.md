# Formulario de pedidos en dos pasos (flujo sin saltos)

**Fecha:** 2026-08-17 · **Estado:** diseño aprobado por JM (pasos, orden y
edición confirmados pregunta a pregunta); pendiente su revisión de este spec.

## Problema

El formulario de pedidos se siente aparatoso y desordenado. JM señaló dos
dolores concretos:

1. **La pantalla salta sola.** Elegir cliente dispara fetches asíncronos
   (precios por cliente, pedido habitual, grupos) que insertan el hero, el
   banner y las líneas precargadas en medio de la pantalla ya renderizada.
   Todo se desplaza; a veces tocas donde ya no está el botón (reproducido
   durante la verificación del 2026-08-17: un clic falló porque el layout
   se movió debajo del cursor).
2. **El orden de las secciones no fluye.** Entrega está entre el cliente y
   los productos, los avisos aparecen en el medio, notas queda escondida.

No se tocan: el panel de añadir producto, el stepper, el buscador filtrado
por grupo, ni ningún contrato del backend (POST, precios, validaciones).

## Decisión de fondo

**Dos pasos renderizados por el servidor** (JM eligió esta opción sobre el
wizard client-side y sobre estabilizar la pantalla única):

- El salto desaparece por construcción: el paso 2 llega completo del
  servidor, como hoy llega la edición de un pedido (que nunca salta).
- El async de carga se elimina de verdad: sin fetch de precios ni de
  habitual al abrir el form. El JS queda para stepper, añadir, chips.
- La URL refleja el estado (`?cliente=…&grupo=…`): recargable, sin estado
  JS que se pierda, y con historial de navegación coherente en la PWA.

## Paso 1 — Elegir cliente

`GET /pedidos/nuevo` (sin `cliente`): pantalla con solo el buscador de
cliente (TomSelect, enfocado al entrar). Al elegir, se navega a
`GET /pedidos/nuevo?cliente=N`.

- **Cliente multi-grupo:** si compra de varios grupos y no vino `grupo`,
  el servidor responde el MISMO paso 1 con la tarjeta «¿Qué pedido vas a
  tomar?» (UI `ph-grupos` actual, movida aquí) listando los grupos como
  enlaces a `?cliente=N&grupo=clave`. Round-trip de servidor, sin fetch.
- **Cliente mono-grupo:** pasa directo al paso 2.
- Permisos como hoy (`clientes_permitidos` del vendedor).

## Paso 2 — El pedido

`GET /pedidos/nuevo?cliente=N[&grupo=clave]` renderiza, en orden:

1. **Cabecera compacta del cliente:** nombre, moneda si USD («USD · 1.78»),
   cadencia e historial (texto del hero actual) y el origen de las líneas
   («Partimos de su pedido habitual · 4 visitas» / «Sin pedidos
   anteriores»). Enlace «Cambiar» que vuelve al paso 1 — con confirmación
   (`data-confirm`) si hay líneas añadidas a mano.
2. **Líneas del pedido** — sembradas server-side (ver Datos).
3. **＋ Añadir otro producto** — panel idéntico al actual. Con cliente sin
   historial, el panel abre desplegado.
4. **Entrega** — chips Hoy/Mañana/…/Otra (bajan aquí desde arriba).
5. **Notas** — igual que hoy.
6. **Footer sticky** — total + «N líneas · entrega X» + Enviar. Sin cambios.

### Datos que el servidor resuelve al armar el paso 2

- `productos_pedido`: líneas habituales con el MISMO formato que usa la
  edición (id, nombre, cajas, precio), más `habitual` para los deltas
  («+2 sobre lo habitual»). Sale de `_calcular_pedido_habitual` — la misma
  función que hoy alimenta la API; el endpoint
  `/api/clientes/<id>/pedido-habitual` queda vivo (lo usan los tests y no
  cuesta nada), pero el form deja de llamarlo.
- `productos` (el catálogo del select): con **precio por cliente resuelto
  por jerarquía en el servidor** (`obtener_precio_producto_cliente` →
  default), en lugar del precio default corregido después por fetch. Menos
  piezas y coherente con el guard de precios v845 (el POST re-resuelve
  igual que siempre).
- Moneda y `tipo_cambio` (hidden, como hoy).
- `cliente_id` viaja como hidden en el form del paso 2 (nuevo y edición):
  el POST actual lo exige y no se toca.

## Edición

`GET /pedidos/<id>/editar` entra directo al paso 2 (ya siembra líneas
server-side). Cambios:

- **Se quita el cambio de cliente de la UI** (decisión de JM): cabecera
  estática con el cliente del pedido, sin select ni «Cambiar». El POST
  sigue mandando `cliente_id` en un hidden (el backend lo exige y no se
  toca). Corregir cliente = borrar y recrear el pedido.
- El catálogo llega con precios del cliente resueltos server-side, igual
  que en paso 2 de nuevo pedido.

## Casos borde

- **Refresh / deep-link** de `?cliente=N`: re-renderiza el paso 2 completo
  (propiedad gratis del enfoque server-side).
- **Cliente inválido o sin permiso** en `?cliente`: redirect al paso 1 con
  flash, como los guards actuales.
- **Volver al paso 1** con líneas manuales: confirmación antes de
  descartar.
- **Grupo inválido en la URL** (`?grupo=` que el cliente no compra): se
  ignora y se re-pregunta (paso 1 con tarjeta de grupos).

## JS que se elimina del template

`cargarPreciosDe`, `cargarPedidoHabitual`, `actualizarMoneda` en su parte
asíncrona, y el manejo de estados de carga intermedios del hero/banner.
Los handlers siguen el patrón `data-*` de `base.js` (sin inline, compatible
con la CSP actual).

## Testing

- Nuevos: paso 1 renderiza buscador sin secciones de pedido; `?cliente=N`
  siembra líneas habituales en el HTML (cliente con historial) y vacío con
  panel abierto (sin historial); multi-grupo sin `grupo` re-pregunta en
  paso 1; con `grupo` válido renderiza paso 2; edición sin select de
  cliente; precios por cliente en el catálogo server-side.
- El POST no cambia: los tests existentes de crear/editar (incluidos los de
  cantidades fraccionarias) deben pasar sin tocarse.
- Revisar los tests acoplados a markup del form viejo (test_gestion_ui,
  test_reskin_smoke, test_loader_barra, test_pedido_habitual) y actualizar
  los tokens que asuman una sola pantalla.
- Verificación en navegador (preview worktree): flujo completo nuevo pedido
  con habitual, sin historial, multi-grupo, edición, y creación con media
  caja para confirmar que nada del flujo fraccionario se movió.

## Fuera de alcance

- Rediseño visual (colores, tipografía) — solo estructura y flujo.
- Panel de añadir producto, stepper, buscador/regla de grupos.
- Backend de POST, precios, validaciones, facturación.
- La pantalla de detalles y el flujo de pesaje.
