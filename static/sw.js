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
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (ventanas) {
      // Si la app ya está abierta (la PWA en segundo plano), se la trae al
      // frente y se la lleva al pedido; si no, se abre una ventana nueva.
      for (var i = 0; i < ventanas.length; i++) {
        var v = ventanas[i];
        if ('focus' in v) {
          if ('navigate' in v) {
            return v.navigate(destino).then(function (w) { return w ? w.focus() : null; })
              .catch(function () { return v.focus(); });
          }
          return v.focus();
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(destino);
      return null;
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
