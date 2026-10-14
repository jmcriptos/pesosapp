/* Notificaciones push: registro del service worker y suscripción.
 *
 * Expone `window.PesosPush` para la pantalla de Mi cuenta → Notificaciones y,
 * en cada carga de página de un usuario logueado, re-sincroniza en silencio
 * la suscripción con el servidor (una vez por sesión del navegador).
 *
 * Se sirve directo, sin minificar, igual que registros.css. Carga después de
 * base.min.js, que es quien parchea `fetch` para mandar el token CSRF.
 */
(function () {
  'use strict';

  var API = {
    clave: '/api/push/clave-publica',
    suscribir: '/api/push/suscribir',
    desuscribir: '/api/push/desuscribir',
    probar: '/api/push/probar'
  };
  var CLAVE_SYNC = 'pesos-push-sync';

  function soportado() {
    return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  }

  function esIOS() {
    return /iPhone|iPad|iPod/.test(navigator.userAgent)
      || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }

  function esStandalone() {
    return (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches)
      || navigator.standalone === true;
  }

  // La clave VAPID viaja en base64url; `subscribe()` la quiere como bytes.
  function b64urlABytes(texto) {
    var relleno = '='.repeat((4 - (texto.length % 4)) % 4);
    var b64 = (texto + relleno).replace(/-/g, '+').replace(/_/g, '/');
    var crudo = window.atob(b64);
    var bytes = new Uint8Array(crudo.length);
    for (var i = 0; i < crudo.length; i++) bytes[i] = crudo.charCodeAt(i);
    return bytes;
  }

  function mismosBytes(a, b) {
    if (!a || !b || a.byteLength !== b.byteLength) return false;
    var va = new Uint8Array(a), vb = new Uint8Array(b);
    for (var i = 0; i < va.length; i++) if (va[i] !== vb[i]) return false;
    return true;
  }

  function postJson(url, cuerpo) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
      body: JSON.stringify(cuerpo || {})
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (datos) {
        if (!r.ok) throw new Error(datos.error || ('El servidor respondió ' + r.status));
        return datos;
      });
    });
  }

  function registracion() {
    if (!soportado()) return Promise.resolve(null);
    return navigator.serviceWorker.getRegistration('/');
  }

  function suscripcionActual() {
    return registracion().then(function (reg) {
      return reg ? reg.pushManager.getSubscription() : null;
    });
  }

  /* Estado para la pantalla de Notificaciones. */
  function estado() {
    var base = { soportado: soportado(), ios: esIOS(), standalone: esStandalone() };
    if (!base.soportado) {
      base.permiso = 'unsupported';
      base.suscrito = false;
      return Promise.resolve(base);
    }
    base.permiso = Notification.permission;
    return suscripcionActual().then(function (sub) {
      base.suscrito = !!sub;
      return base;
    });
  }

  /* Pide permiso, registra el SW, suscribe y le manda la suscripción al
     servidor. Debe llamarse desde un gesto del usuario (un toque): Safari
     rechaza `requestPermission` si no. */
  function activar() {
    if (!soportado()) {
      return Promise.reject(new Error(esIOS() && !esStandalone()
        ? 'En iPhone las notificaciones solo funcionan con la app instalada: Compartir → «Agregar a inicio», y abrila desde ese icono.'
        : 'Este navegador no soporta notificaciones push.'));
    }
    return Notification.requestPermission().then(function (permiso) {
      if (permiso !== 'granted') {
        throw new Error('No se dio permiso para notificaciones. Se puede cambiar en los ajustes del navegador.');
      }
      return navigator.serviceWorker.register('/sw.js');
    }).then(function () {
      return navigator.serviceWorker.ready;
    }).then(function (reg) {
      return fetch(API.clave, { credentials: 'same-origin' }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (datos) {
          if (!r.ok || !datos.clave) throw new Error(datos.error || 'No se pudo obtener la clave del servidor.');
          return { reg: reg, clave: b64urlABytes(datos.clave) };
        });
      });
    }).then(function (ctx) {
      return ctx.reg.pushManager.getSubscription().then(function (sub) {
        // Si el servidor cambió de claves VAPID, la suscripción vieja queda
        // atada a la anterior y cada envío fallaría: se descarta y se arma
        // otra con la clave actual.
        if (sub && sub.options && sub.options.applicationServerKey
            && !mismosBytes(sub.options.applicationServerKey, ctx.clave.buffer)) {
          return sub.unsubscribe().then(function () { return null; });
        }
        return sub;
      }).then(function (sub) {
        if (sub) return sub;
        return ctx.reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: ctx.clave
        });
      });
    }).then(function (sub) {
      return postJson(API.suscribir, sub.toJSON()).then(function (datos) {
        try { sessionStorage.setItem(CLAVE_SYNC, '1'); } catch (e) { /* privado */ }
        return datos;
      });
    });
  }

  function desactivar() {
    return suscripcionActual().then(function (sub) {
      var endpoint = sub ? sub.endpoint : null;
      var quitar = sub ? sub.unsubscribe().catch(function () { return false; }) : Promise.resolve(false);
      return quitar.then(function () {
        return postJson(API.desuscribir, { endpoint: endpoint });
      });
    });
  }

  function probar() {
    return postJson(API.probar, {});
  }

  /* Una vez por sesión del navegador: si ya hay permiso y suscripción, se la
     vuelve a mandar al servidor. Cubre el teléfono compartido (entró otro
     usuario), la rotación de suscripción que hace el servicio de push y una
     base restaurada de backup. Silencioso: nunca molesta al usuario. */
  function sincronizar() {
    try {
      if (!soportado() || Notification.permission !== 'granted') return;
      if (sessionStorage.getItem(CLAVE_SYNC)) return;
    } catch (e) {
      return;
    }
    suscripcionActual().then(function (sub) {
      if (!sub) return null;
      return postJson(API.suscribir, sub.toJSON()).then(function () {
        try { sessionStorage.setItem(CLAVE_SYNC, '1'); } catch (e2) { /* privado */ }
      });
    }).catch(function () { /* sin red o sin configurar: la próxima vez */ });
  }

  window.PesosPush = {
    soportado: soportado,
    estado: estado,
    activar: activar,
    desactivar: desactivar,
    probar: probar,
    sincronizar: sincronizar
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', sincronizar);
  } else {
    sincronizar();
  }
})();
