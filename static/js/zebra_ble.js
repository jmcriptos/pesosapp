/* Impresión directa a una Zebra por Web Bluetooth (Chrome en Android).

   La ZQ520 del almacén es solo Bluetooth. Hoy imprimir una etiqueta exige
   salir a la app de Zebra para que convierta el PDF. Con esto la pantalla de
   pesar manda ZPL a la impresora sin salir de la página: se conecta una vez
   y cada caja registrada imprime su etiqueta sola.

   Protocolo (documentado por Zebra para sus Link-OS con Bluetooth 4.0):
   servicio 38eb4a80-…, característica de escritura 38eb4a82-…, paquetes de
   20 bytes con confirmación. Safari en iPhone no tiene Web Bluetooth: ahí
   `disponible()` es false y la pantalla sigue como antes.
*/
(function () {
  const SERVICIO = '38eb4a80-c570-11e3-9507-0002a5d5c51b';
  const ESCRITURA = '38eb4a82-c570-11e3-9507-0002a5d5c51b';
  const PAQUETE = 20;

  let dispositivo = null;
  let caracteristica = null;
  let cola = Promise.resolve();
  const logosEnviados = new Set();
  const oyentes = [];

  function disponible() {
    return !!(navigator.bluetooth && typeof navigator.bluetooth.requestDevice === 'function');
  }

  function conectada() {
    return !!(dispositivo && dispositivo.gatt && dispositivo.gatt.connected && caracteristica);
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

  async function conectar(mostrarTodos) {
    if (!disponible()) throw new Error('Este navegador no tiene Bluetooth web. Usa Chrome en Android.');
    const opciones = mostrarTodos
      ? { acceptAllDevices: true, optionalServices: [SERVICIO] }
      : { filters: [{ services: [SERVICIO] }], optionalServices: [SERVICIO] };
    const elegido = await navigator.bluetooth.requestDevice(opciones);
    elegido.addEventListener('gattserverdisconnected', () => {
      caracteristica = null;
      logosEnviados.clear();
      avisar('desconectada');
    });
    const servidor = await elegido.gatt.connect();
    const servicio = await servidor.getPrimaryService(SERVICIO);
    caracteristica = await servicio.getCharacteristic(ESCRITURA);
    dispositivo = elegido;
    logosEnviados.clear();
    avisar('conectada', { nombre: nombre() });
    return nombre();
  }

  function desconectar() {
    if (dispositivo && dispositivo.gatt && dispositivo.gatt.connected) {
      dispositivo.gatt.disconnect();
    }
    caracteristica = null;
    logosEnviados.clear();
    avisar('desconectada');
  }

  async function escribir(texto) {
    if (!conectada()) throw new Error('La impresora no está conectada.');
    const bytes = new TextEncoder().encode(texto);
    for (let i = 0; i < bytes.length; i += PAQUETE) {
      // Con confirmación: más lento que sin ella, pero la impresora nunca
      // pierde un paquete a mitad de una etiqueta.
      await caracteristica.writeValue(bytes.slice(i, i + PAQUETE));
    }
  }

  // Una etiqueta a la vez: dos cajas seguidas no mezclan sus paquetes.
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
      + '^FO40,150^A0N,36,36^FDImpresora conectada^FS'
      + '^FO40,220^A0N,30,30^FDLa etiqueta sale al pesar cada caja^FS^PQ1^XZ';
    return imprimirZpl(zpl, null);
  }

  window.ZebraBLE = {
    disponible, conectada, nombre, conectar, desconectar,
    imprimirZpl, imprimirCaja, imprimirPrueba, alCambiar,
  };
})();
