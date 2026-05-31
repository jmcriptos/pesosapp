/* Compartir/guardar PDFs de etiquetas en iOS — incluido el modo PWA
   standalone (instalada en pantalla de inicio), donde NO hay navegador,
   pestañas, barra de direcciones ni botón atrás.

   En iOS no se puede "descargar" un PDF a un iframe oculto ni abrirlo en una
   pestaña nueva (no existen pestañas en standalone). La forma correcta es
   descargar el PDF en segundo plano y abrir la hoja de compartir nativa de
   iOS con navigator.share({files}) — aparece DENTRO de la app, con "Guardar
   en Archivos", "Imprimir", AirDrop, etc., sin abandonar la app.

   Android/escritorio NO usan esto: siguen con el submit nativo al iframe. */
(function () {
  function esDispositivoIOS() {
    return /iP(hone|ad|od)/.test(navigator.userAgent) ||
           (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }
  window.esDispositivoIOS = esDispositivoIOS;

  /* Descarga el PDF (POST con FormData — incluye csrf_token) y lo comparte.
     Devuelve una promesa que siempre resuelve (los errores se notifican con
     alert para no romper el .finally() de la UI). */
  window.compartirEtiquetaIOS = async function (url, formData, filename) {
    let resp;
    try {
      resp = await fetch(url, {
        method: 'POST',
        body: formData,
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin'
      });
    } catch (e) {
      alert('No se pudo conectar para generar las etiquetas. Revisa tu conexión.');
      return;
    }

    if (!resp.ok) {
      let msg = 'No se pudieron generar las etiquetas.';
      try {
        const data = await resp.json();
        if (data && data.error) msg = data.error;
      } catch (e) { /* respuesta no-JSON */ }
      alert(msg);
      return;
    }

    const blob = await resp.blob();
    const file = new File([blob], filename, { type: 'application/pdf' });

    // Camino principal: hoja de compartir nativa (iOS 15+).
    // Compartir SOLO el archivo, sin title/text: si se incluye un título, iOS
    // lo guarda como un archivo de texto aparte ("text", 9 bytes) al "Guardar
    // en Archivos". Compartir solo files entrega únicamente el PDF.
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      try {
        await navigator.share({ files: [file] });
      } catch (e) {
        // El usuario canceló la hoja de compartir → no es un error.
      }
      return;
    }

    // Respaldo (iOS antiguo sin compartir archivos): abrir el PDF en el visor.
    const blobUrl = URL.createObjectURL(blob);
    window.location.href = blobUrl;
    setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 60000);
  };
})();
