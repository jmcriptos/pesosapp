/* Service worker de PesosApp — SOLO notificaciones push.
 *
 * No cachea nada ni intercepta `fetch`: la app sigue yendo al servidor en
 * cada pantalla, igual que hoy. Agregarle caché sería otra decisión (y otro
 * bug posible: una lista de pedidos vieja en pantalla). Se sirve desde /sw.js
 * (ruta `sw_js` en app.py) para que su alcance sea toda la app.
 */

self.addEventListener('install', function () {
  // Un SW nuevo reemplaza al anterior sin esperar a que se cierren las
  // pestañas: acá no hay caché que invalidar, así que no hay riesgo.
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', function (event) {
  var datos = {};
  try {
    datos = event.data ? event.data.json() : {};
  } catch (e) {
    datos = { body: event.data ? event.data.text() : '' };
  }
  var titulo = datos.title || 'PesosApp';
  var opciones = {
    body: datos.body || '',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    // `tag` + `renotify`: un reintento del mismo pedido reemplaza al aviso
    // anterior (y vuelve a sonar) en vez de apilar dos.
    tag: datos.tag || undefined,
    renotify: !!datos.tag,
    data: { url: datos.url || '/pedidos' },
    vibrate: [100, 50, 100]
  };
  // Siempre se muestra algo: si el push llega y no hay notificación visible,
  // Chrome muestra una genérica ("este sitio se actualizó en segundo plano")
  // y a la tercera vez revoca el permiso.
  event.waitUntil(self.registration.showNotification(titulo, opciones));
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var url = (event.notification.data && event.notification.data.url) || '/pedidos';
  var destino = new URL(url, self.location.origin).href;

  function abrirVentanaNueva() {
    return self.clients.openWindow ? self.clients.openWindow(destino) : null;
  }

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (ventanas) {
      // Si la app ya está abierta (la PWA en segundo plano), se la trae al
      // frente y se la lleva al pedido; si no, se abre una ventana nueva.
      //
      // Llevarla al pedido tiene dos caminos, porque `WindowClient.navigate`
      // solo funciona sobre una ventana que ESTE service worker controla y
      // en iOS falla seguido: la primera versión hacía navigate → focus, y
      // cuando navigate fallaba el usuario veía la app tal como la dejó (el
      // listado) y no el pedido. Ahora:
      //   1. se le manda un mensaje a la página, que navega por su cuenta
      //      (push.js escucha `tipo: 'abrir'`); eso no depende de que el SW
      //      la controle;
      //   2. si además navigate está disponible, se usa; si falla, no pasa
      //      nada porque el mensaje ya salió;
      //   3. si no hay ninguna ventana, o no se la pudo enfocar, se abre
      //      una nueva directamente en el pedido.
      var ventana = null;
      for (var i = 0; i < ventanas.length; i++) {
        if ('focus' in ventanas[i]) { ventana = ventanas[i]; break; }
      }
      if (!ventana) return abrirVentanaNueva();

      return ventana.focus().then(function (enfocada) {
        var v = enfocada || ventana;
        try { v.postMessage({ tipo: 'abrir', url: destino }); } catch (e) { /* sin mensaje */ }
        if ('navigate' in v) {
          return v.navigate(destino).catch(function () { return null; });
        }
        return null;
      }).catch(function () {
        return abrirVentanaNueva();
      });
    })
  );
});

// El servicio de push puede rotar la suscripción por su cuenta (Chrome lo
// hace cada tanto). Acá se vuelve a suscribir con la misma clave; el
// servidor se entera en la próxima visita, cuando push.js re-sincroniza
// (desde el SW no hay token CSRF para hacer el POST).
self.addEventListener('pushsubscriptionchange', function (event) {
  var opciones = (event.oldSubscription && event.oldSubscription.options) || { userVisibleOnly: true };
  event.waitUntil(
    self.registration.pushManager.subscribe(opciones).catch(function () { return null; })
  );
});
