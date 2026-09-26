/* Impresión en la Zebra a través de Zebra Browser Print (app de Zebra para
   Android, Windows y macOS).

   Es el camino que Zebra soporta oficialmente para imprimir desde una página
   web: la app corre en el mismo dispositivo, queda emparejada con la
   impresora por Bluetooth clásico o por red, y expone un servicio local en
   http://localhost:9100 (https://localhost:9101 para páginas seguras). La
   página le manda el ZPL y la app se lo pasa a la impresora. No necesita
   Bluetooth de baja energía, que en la ZQ520 del almacén no está disponible.

   Protocolo (BrowserPrint.js de Zebra): GET /available devuelve los equipos,
   POST /write recibe {"device": {...}, "data": "<ZPL>"}. El cuerpo va como
   texto plano para que el navegador no exija una petición previa de CORS.

   En iPhone no existe Browser Print: `disponible()` es false y no se intenta. */
(function () {
  // Mismas direcciones que BROWSER_PRINT_ORIGENES en app.py (connect-src).
  const BASES = ['http://localhost:9100/', 'http://127.0.0.1:9100/', 'https://localhost:9101/'];
  // La primera vez que un sitio le habla, Browser Print pide autorizarlo
  // DENTRO de su app y retiene la respuesta hasta que el operario acepta.
  // La espera tiene que dar tiempo a ir a la app y volver. Un puerto donde
  // nadie escucha falla al instante, así que sin la app no se espera nada.
  const ESPERA_MS = 20000;

  let base = null;
  let dispositivo = null;
  let cola = Promise.resolve();
  const logosEnviados = new Set();
  const oyentes = [];

  function esIOS() {
    return /iP(hone|ad|od)/.test(navigator.userAgent) ||
           (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }

  function disponible() {
    return !esIOS() && typeof fetch === 'function';
  }

  function conectada() {
    return !!(base && dispositivo);
  }

  function nombre() {
    return dispositivo ? (dispositivo.name || 'Impresora Zebra') : '';
  }

  function avisar(evento, detalle) {
    oyentes.forEach((fn) => {
      try { fn(evento, detalle); } catch (e) { /* un oyente roto no frena la impresión */ }
    });
  }

  function alCambiar(fn) {
    oyentes.push(fn);
  }

  async function pedir(url, opciones) {
    const control = new AbortController();
    const reloj = setTimeout(() => control.abort(), ESPERA_MS);
    try {
      return await fetch(url, Object.assign({ credentials: 'omit', signal: control.signal }, opciones || {}));
    } finally {
      clearTimeout(reloj);
    }
  }

  // Un «Failed to fetch» no dice si Browser Print rechazó el sitio (CORS)
  // o si Chrome ni siquiera dejó salir la petición (permiso de red local,
  // certificado). Una segunda petición en modo no-cors lo distingue: si esa
  // llega, el servicio está y solo falta autorizar el sitio en la app.
  async function servicioAlcanzable(candidata) {
    try {
      await pedir(candidata + 'available', { mode: 'no-cors' });
      return true;
    } catch (err) {
      return false;
    }
  }

  // Busca el servicio local en los dos puertos y devuelve las impresoras.
  // El error dice qué pasó en cada puerto y qué hacer: es lo único que
  // permite resolverlo desde el almacén sin una consola de desarrollador.
  async function buscar() {
    const fallos = [];
    const origen = window.location.origin;
    for (const candidata of BASES) {
      try {
        const resp = await pedir(candidata + 'available');
        if (!resp.ok) {
          fallos.push(`${candidata} respondió ${resp.status}`);
          continue;
        }
        const datos = await resp.json();
        const impresoras = (datos && datos.printer) || [];
        base = candidata;
        return impresoras;
      } catch (err) {
        if (err && err.name === 'AbortError') {
          fallos.push(`${candidata} sin respuesta en 20 s`);
        } else if (await servicioAlcanzable(candidata)) {
          fallos.push(`${candidata} responde pero no autoriza este sitio: en la app Browser Print agrega ${origen} a los sitios permitidos`);
        } else {
          fallos.push(`${candidata} bloqueado por Chrome antes de salir (${err && err.message ? err.message : err}): permite a ${origen} el acceso a la red local en los permisos del sitio`);
        }
      }
    }
    base = null;
    throw new Error(`Zebra Browser Print: ${fallos.join(' · ')}`);
  }

  function elegir(impresoras) {
    if (!impresoras.length) return null;
    // La ZQ520 entra por Bluetooth: se prefiere una impresora Bluetooth, y
    // entre varias la que lleve "ZQ" en el nombre.
    const bluetooth = impresoras.filter((p) => String(p.connection || '').toLowerCase() === 'bluetooth');
    const zq = bluetooth.find((p) => /zq/i.test(p.name || '')) || impresoras.find((p) => /zq/i.test(p.name || ''));
    return zq || bluetooth[0] || impresoras[0];
  }

  async function conectar() {
    if (!disponible()) throw new Error('Browser Print no existe para este dispositivo.');
    const impresoras = await buscar();
    const elegida = elegir(impresoras);
    if (!elegida) {
      throw new Error('Browser Print está abierto pero no tiene ninguna impresora. Empareja la Zebra en la app.');
    }
    dispositivo = elegida;
    logosEnviados.clear();
    avisar('conectada', { nombre: nombre() });
    return nombre();
  }

  function desconectar() {
    dispositivo = null;
    logosEnviados.clear();
    avisar('desconectada');
  }

  async function escribir(texto) {
    if (!conectada()) throw new Error('La impresora no está conectada.');
    const resp = await pedir(base + 'write', {
      method: 'POST',
      // Texto plano a propósito: con application/json el navegador manda un
      // OPTIONS previo que el servicio de Zebra no contesta.
      headers: { 'Content-Type': 'text/plain' },
      body: JSON.stringify({ device: dispositivo, data: texto }),
    });
    if (!resp.ok) throw new Error(`Browser Print devolvió ${resp.status}.`);
  }

  function encolar(trabajo) {
    const siguiente = cola.then(trabajo, trabajo);
    cola = siguiente.catch(() => {});
    return siguiente;
  }

  async function imprimirZpl(zpl, logo) {
    return encolar(async () => {
      if (logo && logo.nombre && logo.zpl && !logosEnviados.has(logo.nombre)) {
        avisar('progreso', { mensaje: 'Cargando logo en la impresora…' });
        await escribir(logo.zpl);
        logosEnviados.add(logo.nombre);
      }
      await escribir(zpl);
    });
  }

  async function imprimirCaja(cajaId) {
    const resp = await fetch(`/cajas/${cajaId}/etiqueta.zpl`, {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (!resp.ok) throw new Error('No se pudo generar la etiqueta.');
    const datos = await resp.json();
    await imprimirZpl(datos.zpl, datos.logo);
    return datos;
  }

  async function imprimirPrueba() {
    const zpl = '^XA^CI28^PW812^LL406^MNY^FO40,60^A0N,60,60^FDPesosApp^FS'
      + '^FO40,150^A0N,36,36^FDImpresora conectada (Browser Print)^FS'
      + '^FO40,220^A0N,30,30^FDLa etiqueta sale al pesar cada caja^FS^PQ1^XZ';
    return imprimirZpl(zpl, null);
  }

  window.ZebraBrowserPrint = {
    disponible, conectada, nombre, conectar, desconectar,
    imprimirZpl, imprimirCaja, imprimirPrueba, alCambiar,
  };
})();
