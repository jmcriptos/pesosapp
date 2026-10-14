# Notificaciones push de pedidos nuevos — diseño

**Fecha:** 2026-10-14
**Pedido de JM:** «implementar los mensajes push y las notificaciones
específicamente para los nuevos pedidos registrados, la idea es que los
usuarios estén enterados de los nuevos pedidos».

## Qué resuelve

Hoy un pedido que carga un vendedor en la calle recién se ve cuando alguien
abre el listado. Bodega, facturación y JM se enteran tarde o por WhatsApp.
Con esto, cada usuario que lo active recibe un aviso en el teléfono (o la
PC) en el momento en que se guarda el pedido, aunque la app esté cerrada.
Al tocar el aviso se abre el detalle del pedido.

## Decisiones

- **Web Push estándar (VAPID), sin terceros.** La app ya es una PWA; lo que
  faltaba era un service worker y un par de claves. No se suma Firebase,
  OneSignal ni ningún SDK: el push lo entrega el servicio del propio
  navegador (Apple, Google, Mozilla). Costo cero, sin cuenta nueva, sin datos
  de la empresa en otro proveedor.
- **Solo pedidos nuevos.** Un único evento, el que JM pidió. Agregar más
  (facturado, entregado) es trivial después —`_despachar_push` ya es
  genérico— pero cada aviso extra es ruido hasta que alguien lo pida.
- **A todos los usuarios activos con dispositivo suscrito, menos a quien
  cargó el pedido.** El vendedor que acaba de guardarlo ya lo sabe. No hay
  filtro por rol: quien no quiera avisos no activa la función en su teléfono.
  Un usuario dado de baja (`activo = false`) no recibe nada aunque su
  teléfono siga suscrito.
- **Opt-in por dispositivo, desde Mi cuenta → Notificaciones.** La campana
  de la barra superior, que era un botón sin acción, ahora lleva ahí. La
  activación necesita un toque del usuario (Safari exige el gesto para pedir
  permiso), así que no se pide solo al entrar.
- **El aviso nunca interrumpe la creación del pedido.** Se dispara después
  del commit, envuelto en try/except, y el envío real sale en un hilo daemon
  (mismo patrón que el webhook HACCP). Si Apple o Google no responden, el
  vendedor no se entera y el pedido ya está guardado.
- **Las suscripciones muertas se borran solas.** Un 404/410 del servicio de
  push significa que el usuario revocó el permiso o desinstaló la PWA; se
  borra la fila en vez de reintentar para siempre. Un 5xx o un corte de red
  no borra nada.
- **La tabla se asegura al arrancar**, como `evento_auditoria` y las del
  módulo de producción. El historial de Alembic ya tiene dos heads
  (`b7e1d94c02aa`, `f2a3b4c5d6e7`) y no se usa para tablas nuevas; hay un
  `scripts/push_migracion.sql` para quien prefiera correrlo a mano.
- **El service worker no cachea nada.** Solo recibe push y abre el pedido al
  tocar. Una caché de pantallas sería otra decisión, con su propio riesgo
  (un listado viejo en pantalla).

## Piezas

| Pieza | Dónde | Qué hace |
|---|---|---|
| `SuscripcionPush` | `app.py` | Una fila por dispositivo: endpoint (único), claves `p256dh`/`auth`, usuario, último envío. |
| `utils/push_notificaciones.py` | módulo puro | Lee las claves del entorno, arma el texto, manda con `pywebpush`, mapea 404/410 → baja. |
| `_notificar_nuevo_pedido` | `app.py`, al final de `nuevo_pedido` | Junta suscripciones, arma el payload y despacha en segundo plano. |
| `/api/push/clave-publica`, `/suscribir`, `/desuscribir`, `/probar` | `app.py` | Lo que usa `push.js`. Todos con login; suscribir/desuscribir sólo tocan filas del usuario logueado. |
| `/sw.js` | `app.py` → `static/sw.js` | Service worker servido desde la raíz (alcance de toda la app), público, `Cache-Control: no-cache`. |
| `static/js/push.js` | todas las pantallas con sesión | `window.PesosPush` (estado, activar, desactivar, probar) y re-sincronización silenciosa una vez por sesión. |
| `templates/cuenta_notificaciones.html` | `/mi-cuenta/notificaciones` | Activar / desactivar / enviar prueba, con la explicación para iPhone. |
| `flask push-generar-claves` | CLI | Genera el par VAPID una sola vez. |

## Configuración

```
VAPID_PUBLIC_KEY=...        # las tres salen de `flask push-generar-claves`
VAPID_PRIVATE_KEY=...
VAPID_CLAIMS_EMAIL=mailto:jm@jomarfoods.com
```

Sin las tres variables la función queda apagada: los endpoints responden
503 con un mensaje claro, la pantalla lo explica, y `nuevo_pedido` ni
intenta mandar nada. Cambiar las claves invalida todas las suscripciones:
cada teléfono tiene que volver a tocar «Activar».

## Teléfonos

- **Android (Chrome):** funciona desde el navegador y desde la PWA.
- **iPhone/iPad (iOS 16.4+):** solo con la app agregada a la pantalla de
  inicio y abierta desde ese icono. En Safari normal no existe `PushManager`
  y la pantalla lo dice con las instrucciones.
- **PC:** Chrome, Edge y Firefox; Safari de Mac 16+.

## Qué NO hace (todavía)

- No avisa de otros estados del pedido (preparado, facturado, entregado).
- No hay preferencias por usuario más allá de activar/desactivar el
  dispositivo; no se filtra por territorio ni por cliente.
- No hay centro de notificaciones dentro de la app: el aviso vive en el
  sistema operativo y, al tocarlo, en el pedido.

## Verificación

`tests/test_push_pedidos.py`: el aviso llega a los demás y no al autor ni a
inactivos; un 410 borra la suscripción; un error de red no borra ni rompe
el pedido; sin claves no se intenta nada; suscribir/desuscribir sólo tocan
lo propio; `sw.js` se sirve sin login; el mapeo de respuestas de pywebpush y
la generación de claves.
