(function () {
  function todayISO() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }

  function addYearsISO(iso, years) {
    const [year, month, day] = iso.split('-').map(Number);
    const next = new Date(year + years, month - 1, day);
    return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}-${String(next.getDate()).padStart(2, '0')}`;
  }

  function formatISO(iso) {
    if (!iso) return '—';
    const [year, month, day] = iso.split('-');
    return `${day}/${month}/${year}`;
  }

  function daysBetween(fromISO, toISO) {
    if (!fromISO || !toISO) return 0;
    const from = new Date(`${fromISO}T00:00:00`);
    const to = new Date(`${toISO}T00:00:00`);
    return Math.round((to - from) / 86400000);
  }

  function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
  }

  function parseWeight(value) {
    const normalized = String(value || '').replace(',', '.').trim();
    const numeric = Number.parseFloat(normalized || '0');
    return Number.isFinite(numeric) ? numeric : 0;
  }

  function closeModal() {
    const root = document.getElementById('modal-root');
    if (root) root.innerHTML = '';
    document.body.classList.remove('is-pesar-modal-open');
  }

  function openDatePicker(options) {
    const existing = document.querySelector('.pesar-date-sheet');
    if (existing) existing.remove();

    const current = options.value || todayISO();
    const [startYear, startMonth] = current.split('-').map(Number);
    let viewYear = startYear;
    let viewMonth = startMonth - 1;
    const accent = options.accent || '#6366f1';
    const selected = () => options.value || current;

    const sheet = document.createElement('div');
    sheet.className = 'pesar-date-sheet';
    const resetBtnHtml = options.onReset
      ? '<button type="button" class="pesar-date-sheet-secondary" data-reset><i class="fas fa-rotate-left"></i> Auto (+1 año)</button>'
      : '';
    sheet.innerHTML = `
      <div class="pesar-date-sheet-panel" style="--cat:${accent}">
        <div class="pesar-date-sheet-handle"></div>
        <div class="pesar-date-sheet-header">
          <div>
            <div class="pesar-date-sheet-title">${options.title || 'Seleccionar fecha'}</div>
            <div class="pesar-date-sheet-subtitle">${options.subtitle || ''}</div>
          </div>
          <button type="button" class="pesar-modal-close" data-close-sheet><i class="fas fa-times"></i></button>
        </div>
        <div class="pesar-date-sheet-nav">
          <button type="button" data-nav="-1"><i class="fas fa-chevron-left"></i></button>
          <strong data-month-label></strong>
          <button type="button" data-nav="1"><i class="fas fa-chevron-right"></i></button>
        </div>
        <div class="pesar-date-sheet-calendar" data-calendar></div>
        <div class="pesar-date-sheet-actions">
          <button type="button" class="pesar-date-sheet-secondary" data-close-sheet>Cancelar</button>
          ${resetBtnHtml}
          <button type="button" class="pesar-date-sheet-primary" data-today>Hoy</button>
        </div>
      </div>
    `;

    const monthLabel = sheet.querySelector('[data-month-label]');
    const calendar = sheet.querySelector('[data-calendar]');
    const monthNames = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
    const dow = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];

    function isDisabled(iso) {
      if (!options.min) return false;
      return iso < options.min;
    }

    function renderCalendar() {
      monthLabel.textContent = `${monthNames[viewMonth]} ${viewYear}`;
      const firstDow = (new Date(viewYear, viewMonth, 1).getDay() + 6) % 7;
      const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
      const cells = [];
      for (let idx = 0; idx < firstDow; idx += 1) cells.push(null);
      for (let day = 1; day <= daysInMonth; day += 1) cells.push(day);
      while (cells.length % 7 !== 0) cells.push(null);

      calendar.innerHTML = '';
      dow.forEach((label) => {
        const el = document.createElement('div');
        el.className = 'pesar-date-sheet-dow';
        el.textContent = label;
        calendar.appendChild(el);
      });

      cells.forEach((day) => {
        const cell = document.createElement('button');
        cell.type = 'button';
        cell.className = 'pesar-date-cell';
        if (!day) {
          cell.disabled = true;
          calendar.appendChild(cell);
          return;
        }

        const iso = `${viewYear}-${String(viewMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        cell.textContent = String(day);
        if (iso === selected()) cell.classList.add('is-selected');
        if (isDisabled(iso)) cell.classList.add('is-disabled');
        cell.addEventListener('click', () => {
          options.onSelect(iso);
          closeSheet();
        });
        calendar.appendChild(cell);
      });
    }

    function closeSheet() {
      sheet.remove();
    }

    sheet.addEventListener('click', (event) => {
      if (event.target === sheet) closeSheet();
    });

    sheet.querySelectorAll('[data-close-sheet]').forEach((button) => {
      button.addEventListener('click', closeSheet);
    });

    sheet.querySelectorAll('[data-nav]').forEach((button) => {
      button.addEventListener('click', () => {
        const delta = Number.parseInt(button.dataset.nav, 10);
        viewMonth += delta;
        if (viewMonth < 0) {
          viewMonth = 11;
          viewYear -= 1;
        } else if (viewMonth > 11) {
          viewMonth = 0;
          viewYear += 1;
        }
        renderCalendar();
      });
    });

    sheet.querySelector('[data-today]').addEventListener('click', () => {
      const iso = todayISO();
      if (!isDisabled(iso)) {
        options.onSelect(iso);
        closeSheet();
      }
    });

    sheet.querySelector('[data-reset]')?.addEventListener('click', () => {
      options.onReset();
      closeSheet();
    });

    document.body.appendChild(sheet);
    renderCalendar();
  }

  document.addEventListener('DOMContentLoaded', () => {
    const screen = document.querySelector('.pesar-screen');
    if (!screen) return;

    const frame = screen.querySelector('.pesar-frame');
    const form = document.getElementById('pesar-add-form');
    const chipRow = document.getElementById('pesar-chip-row');
    const loteInput = document.getElementById('pesar-lote-input');
    const detalleInput = document.getElementById('pesar-detalle-id');
    const pesoHidden = document.getElementById('pesar-peso-hidden');
    const fechaElabHidden = document.getElementById('pesar-fecha-elab-hidden');
    const fechaVencHidden = document.getElementById('pesar-fecha-venc-hidden');
    const fechaElabDisplay = document.getElementById('pesar-fecha-elab-display');
    const fechaVencDisplay = document.getElementById('pesar-fecha-venc-display');
    const fechaVencBadge = document.getElementById('pesar-venc-badge');
    const weightDisplay = document.getElementById('pesar-weight-display');
    const readoutLabel = document.getElementById('pesar-readout-box-label');
    const readoutProduct = document.getElementById('pesar-readout-product');
    const undoButton = document.getElementById('pesar-undo');

    const state = {
      activeId: Number.parseInt(screen.dataset.activeDetalleId || detalleInput?.value || '0', 10),
      weight: '',
      fechaElaboracion: todayISO(),
      fechaVencimiento: addYearsISO(todayISO(), 1),
      vencManual: false,
    };

    function activePanel() {
      return screen.querySelector(`.pesar-panel[data-detalle-id="${state.activeId}"]`);
    }

    function activePanelState() {
      return activePanel()?.querySelector('.pesar-panel-state');
    }

    function syncDates() {
      fechaElabHidden.value = state.fechaElaboracion;
      fechaVencHidden.value = state.fechaVencimiento;
      fechaElabDisplay.textContent = formatISO(state.fechaElaboracion);
      fechaVencDisplay.textContent = formatISO(state.fechaVencimiento);
      fechaVencBadge.textContent = state.vencManual ? 'MANUAL' : 'AUTO';
    }

    function renderWeight() {
      weightDisplay.textContent = state.weight || '0';
      pesoHidden.value = state.weight;
      const submit = screen.querySelector('.pesar-key.is-submit');
      if (submit) {
        const weightOk = parseWeight(state.weight) > 0;
        const loteOk = String(loteInput?.value || '').trim().length > 0;
        submit.disabled = !(weightOk && loteOk);
      }
    }

    function updateUndoButton() {
      const lastChip = activePanel()?.querySelector('.pesar-box-chip:last-of-type');
      undoButton.disabled = !lastChip;
    }

    // Pedido 1357 (2026-09): pesos de Pork Chorizo y Andouille Pork Chorizo
    // quedaron cruzados. Safari recarga la pestaña cuando el teléfono se
    // bloquea entre caja y caja, y la recarga volvía al producto de la URL
    // (o al primero incompleto), no al que se estaba pesando. Guardar el
    // chip activo en la URL hace que la recarga vuelva al mismo producto.
    function rememberActiveInUrl() {
      try {
        const url = new URL(window.location.href);
        url.searchParams.set('detalle_id', String(state.activeId));
        window.history.replaceState(window.history.state, '', url.toString());
      } catch (err) {
        // Sin History API la pantalla sigue funcionando igual que antes.
      }
    }

    // Cada producto trae su propio lote: al cambiar de chip se toma el de su
    // última caja. Un producto sin cajas conserva lo que está escrito.
    function loadLoteFromPanel() {
      const panelState = activePanelState();
      if (!panelState) return;
      const lote = panelState.dataset.ultimoLote || '';
      if (!lote) return;
      loteInput.value = lote;
      if (panelState.dataset.ultimaElab) state.fechaElaboracion = panelState.dataset.ultimaElab;
      if (panelState.dataset.ultimoVenc) {
        state.fechaVencimiento = panelState.dataset.ultimoVenc;
        state.vencManual = state.fechaVencimiento !== addYearsISO(state.fechaElaboracion, 1);
      }
      syncDates();
    }

    function flashProduct() {
      readoutProduct.classList.remove('is-flash');
      // Forzar reflow para reiniciar la animación en cambios seguidos.
      void readoutProduct.offsetWidth;
      readoutProduct.classList.add('is-flash');
    }

    function setBusy(busy) {
      screen.classList.toggle('is-busy', busy);
      screen.querySelectorAll('.pesar-key').forEach((key) => {
        if (busy) {
          key.disabled = true;
        } else if (!key.classList.contains('is-submit')) {
          key.disabled = false;
        }
      });
      if (!busy) renderWeight();
    }

    function refreshActivePanel() {
      screen.querySelectorAll('.pesar-panel').forEach((panel) => {
        panel.classList.toggle('is-hidden', Number.parseInt(panel.dataset.detalleId, 10) !== state.activeId);
      });

      screen.querySelectorAll('.pesar-chip').forEach((chip) => {
        chip.classList.toggle('is-active', Number.parseInt(chip.dataset.detalleId, 10) === state.activeId);
      });

      // La propuesta de maquila se dibuja para el producto con que abrió la
      // pantalla; con otro chip activo confundiría de qué producto es.
      screen.querySelectorAll('.maquila-asignar[data-detalle-id]').forEach((block) => {
        block.hidden = Number.parseInt(block.dataset.detalleId, 10) !== state.activeId;
      });

      const panelState = activePanelState();
      if (!panelState) return;

      const target = Number.parseInt(panelState.dataset.target || '0', 10);
      const count = Number.parseInt(panelState.dataset.count || '0', 10);
      const productName = panelState.dataset.productName || '';
      const cat = panelState.dataset.cat || 'RES';
      const nextBox = Math.min(count + 1, Math.max(target, 1));

      frame.dataset.cat = cat;
      detalleInput.value = String(state.activeId);
      form.setAttribute('hx-target', `#cajas-list-producto-${state.activeId}`);
      readoutLabel.textContent = `Caja ${nextBox} de ${target}`;
      readoutProduct.textContent = productName;
      updateUndoButton();
    }

    function resetWeight() {
      state.weight = '';
      renderWeight();
    }

    function submitBox() {
      if (!form) return;
      if (parseWeight(state.weight) <= 0) return;
      if (!String(loteInput.value || '').trim()) return;
      form.requestSubmit();
    }

    function incrementLote() {
      const value = loteInput.value.trim();
      const match = value.match(/^(.*?)(\d+)$/);
      if (!match) return;
      const next = String(Number.parseInt(match[2], 10) + 1).padStart(match[2].length, '0');
      loteInput.value = `${match[1]}${next}`;
    }

    function pressKey(key) {
      if (key === 'submit') {
        submitBox();
        return;
      }
      if (key === 'back') {
        state.weight = state.weight.slice(0, -1);
        renderWeight();
        return;
      }
      if (key === 'clear') {
        resetWeight();
        return;
      }
      if (key === '.') {
        if (state.weight.includes('.')) return;
        state.weight = state.weight ? `${state.weight}.` : '0.';
        renderWeight();
        return;
      }
      if (/^\d$/.test(key)) {
        if (state.weight === '0') {
          state.weight = key;
          renderWeight();
          return;
        }
        if (state.weight.includes('.')) {
          const decimals = state.weight.split('.')[1];
          if (decimals.length >= 3) return;
        }
        if (state.weight.length >= 7) return;
        state.weight = `${state.weight}${key}`;
        renderWeight();
      }
    }

    function openMainDatePicker(field) {
      const isVenc = field === 'fecha_vencimiento';
      openDatePicker({
        title: field === 'fecha_elaboracion' ? 'Fecha de elaboración' : 'Fecha de vencimiento',
        subtitle: isVenc && !state.vencManual ? 'Por defecto +1 año desde la elaboración' : '',
        value: field === 'fecha_elaboracion' ? state.fechaElaboracion : state.fechaVencimiento,
        min: isVenc ? state.fechaElaboracion : '',
        accent: getComputedStyle(frame).getPropertyValue('--cat').trim(),
        onSelect: (iso) => {
          if (field === 'fecha_elaboracion') {
            state.fechaElaboracion = iso;
            if (!state.vencManual || state.fechaVencimiento < iso) {
              state.fechaVencimiento = addYearsISO(iso, 1);
            }
          } else {
            state.fechaVencimiento = iso;
            state.vencManual = true;
          }
          syncDates();
        },
        onReset: isVenc && state.vencManual ? () => {
          state.vencManual = false;
          state.fechaVencimiento = addYearsISO(state.fechaElaboracion, 1);
          syncDates();
        } : undefined,
      });
    }

    function showFeedbackMessage(message) {
      // Se busca cada vez: la respuesta de «+ Caja» reemplaza el nodo entero
      // (outerHTML) para poder traer la confirmación en verde.
      const feedback = document.getElementById('pesar-feedback');
      if (!feedback) return;
      feedback.classList.remove('is-ok');
      feedback.textContent = message || '';
    }

    chipRow?.addEventListener('click', (event) => {
      const chip = event.target.closest('.pesar-chip');
      if (!chip) return;
      const nextId = Number.parseInt(chip.dataset.detalleId, 10);
      if (nextId === state.activeId) return;
      if (screen.classList.contains('is-busy')) return;
      state.activeId = nextId;
      // Un peso tecleado para un producto no viaja al otro.
      resetWeight();
      showFeedbackMessage('');
      refreshActivePanel();
      loadLoteFromPanel();
      rememberActiveInUrl();
      flashProduct();
    });

    // «Imprimir etiqueta» de una caja. En Android/escritorio el enlace abre
    // el PDF en pestaña nueva y el navegador lo descarga o lo muestra. En iOS
    // (sobre todo la PWA instalada, sin pestañas) va por la hoja de compartir
    // nativa, que trae «Imprimir» y AirPrint: mismo camino que las etiquetas
    // del pedido completo.
    // ---- Impresora Zebra (Browser Print o Bluetooth de baja energía) ----
    const printer = {
      root: document.getElementById('pesar-printer'),
      name: document.getElementById('pesar-printer-name'),
      msg: document.getElementById('pesar-printer-msg'),
      connect: document.getElementById('pesar-printer-connect'),
      all: document.getElementById('pesar-printer-all'),
      autoWrap: document.getElementById('pesar-printer-auto-wrap'),
      auto: document.getElementById('pesar-printer-auto'),
      test: document.getElementById('pesar-printer-test'),
      disconnect: document.getElementById('pesar-printer-disconnect'),
      ultimaImpresa: null,
    };
    const AUTO_KEY = 'pesar.imprimirAlPesar';

    // Dos formas de llegar a la Zebra, en este orden:
    //  1. Zebra Browser Print: app de Zebra en el mismo Android (o PC),
    //     emparejada con la impresora por Bluetooth clásico. Es lo que Zebra
    //     soporta oficialmente y lo único que sirve con la ZQ520, cuya radio
    //     no expone baja energía.
    //  2. Web Bluetooth directo (baja energía), para impresoras que sí lo
    //     tengan, o para Bluefy en iPhone.
    const transportes = [window.ZebraBrowserPrint, window.ZebraBLE].filter(Boolean);
    let transporte = null;

    function printerReady() {
      return !!(transporte && transporte.conectada());
    }

    function printerMsg(text, isError) {
      if (!printer.msg) return;
      printer.msg.textContent = text || '';
      printer.msg.classList.toggle('is-error', !!isError);
    }

    function printerRender() {
      if (!printer.root) return;
      const on = printerReady();
      printer.name.textContent = on
        ? `Impresora: ${transporte.nombre()}`
        : 'Impresora no conectada';
      printer.root.classList.toggle('is-on', on);
      printer.connect.hidden = on;
      // «Bluetooth directo» abre el selector de Web Bluetooth (baja energía).
      printer.all.hidden = on || !(window.ZebraBLE && window.ZebraBLE.disponible());
      printer.autoWrap.hidden = !on;
      printer.test.hidden = !on;
      printer.disconnect.hidden = !on;
    }

    async function printerConnect(mostrarTodos) {
      printerMsg('Buscando impresora…');
      const errores = [];
      transporte = null;
      // Browser Print primero: si la app está abierta con la Zebra
      // emparejada, no hace falta ningún selector.
      if (!mostrarTodos && window.ZebraBrowserPrint && window.ZebraBrowserPrint.disponible()) {
        printerMsg('Buscando Zebra Browser Print… Si la app de Browser Print pide autorizar este sitio, acéptalo y vuelve aquí.');
        try {
          await window.ZebraBrowserPrint.conectar();
          transporte = window.ZebraBrowserPrint;
        } catch (err) {
          errores.push(err && err.message ? err.message : String(err));
        }
      }
      // Web Bluetooth solo cuando se pide con «Bluetooth directo» o cuando no
      // hay Browser Print (iPhone con Bluefy). En Android, el escaneo de
      // baja energía tumba la conexión clásica que Browser Print tiene con
      // la ZQ520: el ícono de Bluetooth de la impresora se apagaba al tocar
      // «Conectar» y la app quedaba sin impresora.
      const usarBle = window.ZebraBLE && window.ZebraBLE.disponible()
        && (mostrarTodos || !(window.ZebraBrowserPrint && window.ZebraBrowserPrint.disponible()));
      if (!transporte && usarBle) {
        printerMsg('Elige la impresora en la ventana de Chrome…');
        try {
          await window.ZebraBLE.conectar(mostrarTodos);
          transporte = window.ZebraBLE;
        } catch (err) {
          // Cancelar el selector de Chrome no es un error que haya que gritar.
          const cancelado = err && (err.name === 'NotFoundError' || err.name === 'AbortError');
          errores.push(cancelado ? 'No se eligió ninguna impresora.' : (err && err.message ? err.message : String(err)));
        }
      }
      if (transporte) {
        printerMsg('Conectada. La etiqueta sale al registrar cada caja.');
      } else if (errores.length) {
        printerMsg(`No se pudo conectar: ${errores.join(' · ')}`, true);
      } else {
        printerMsg('Este navegador no puede llegar a la impresora. En Android, instala Zebra Browser Print y empareja la Zebra.', true);
      }
      printerRender();
    }

    async function printerPrintCaja(cajaId, etiqueta) {
      if (!printerReady()) return false;
      printerMsg(`Imprimiendo ${etiqueta || 'etiqueta'}…`);
      try {
        const datos = await transporte.imprimirCaja(cajaId);
        printerMsg(`Etiqueta impresa: caja #${String(datos.numero).padStart(2, '0')} · ${datos.producto}`);
        return true;
      } catch (err) {
        printerMsg(`No se imprimió: ${err.message || err}`, true);
        return false;
      }
    }

    if (printer.root && transportes.some((t) => t.disponible())) {
      printer.root.hidden = false;
      try {
        printer.auto.checked = localStorage.getItem(AUTO_KEY) !== '0';
      } catch (err) { /* sin localStorage queda el valor por defecto */ }
      printer.auto.addEventListener('change', () => {
        try { localStorage.setItem(AUTO_KEY, printer.auto.checked ? '1' : '0'); } catch (err) { /* idem */ }
      });
      printer.connect.addEventListener('click', () => printerConnect(false));
      printer.all.addEventListener('click', () => printerConnect(true));
      printer.disconnect.addEventListener('click', () => {
        if (transporte) transporte.desconectar();
        transporte = null;
        printerRender();
      });
      printer.test.addEventListener('click', async () => {
        if (!printerReady()) return;
        printerMsg('Imprimiendo prueba…');
        try {
          await transporte.imprimirPrueba();
          printerMsg('Prueba enviada.');
        } catch (err) {
          printerMsg(`No se imprimió: ${err.message || err}`, true);
        }
      });
      transportes.forEach((t) => t.alCambiar((evento, detalle) => {
        if (t !== transporte) return;
        if (evento === 'desconectada') {
          printerMsg('La impresora se desconectó.', true);
          transporte = null;
        }
        if (evento === 'progreso' && detalle) printerMsg(detalle.mensaje);
        printerRender();
      }));
      printerRender();
    }

    document.addEventListener('click', (event) => {
      const link = event.target.closest('[data-etiqueta-caja]');
      if (!link) return;
      // Con la Zebra conectada, el botón imprime por Bluetooth en vez de
      // abrir el PDF (que exigiría salir a la app del fabricante).
      if (printerReady() && link.dataset.cajaId) {
        event.preventDefault();
        printerPrintCaja(Number.parseInt(link.dataset.cajaId, 10));
        return;
      }
      if (!(window.esDispositivoIOS && window.esDispositivoIOS())) return;
      if (typeof window.compartirEtiquetaIOS !== 'function') return;
      event.preventDefault();
      link.classList.add('is-loading');
      window.compartirEtiquetaIOS(link.href, null, link.dataset.filename || 'etiqueta.pdf')
        .finally(() => link.classList.remove('is-loading'));
    });

    screen.addEventListener('click', (event) => {
      const keyButton = event.target.closest('[data-key]');
      if (keyButton) {
        pressKey(keyButton.dataset.key);
        return;
      }

      const dateTrigger = event.target.closest('[data-date-trigger]');
      if (dateTrigger) {
        openMainDatePicker(dateTrigger.dataset.dateTrigger);
        return;
      }
    });

    document.getElementById('pesar-nuevo-lote')?.addEventListener('click', () => {
      incrementLote();
      renderWeight();
    });

    loteInput?.addEventListener('input', renderWeight);

    undoButton?.addEventListener('click', () => {
      const lastChip = activePanel()?.querySelector('.pesar-box-chip:last-of-type');
      const deleteUrl = lastChip?.dataset.deleteUrl;
      if (!deleteUrl || !window.htmx) return;
      window.htmx.ajax('DELETE', deleteUrl, {
        target: `#cajas-list-producto-${state.activeId}`,
        swap: 'innerHTML',
      });
    });

    if (window.htmx) {
      document.body.addEventListener('htmx:configRequest', (event) => {
        const token = getCsrfToken();
        if (token) event.detail.headers['X-CSRFToken'] = token;
      });

      document.body.addEventListener('htmx:beforeRequest', (event) => {
        const formEl = event.target.closest('#pesar-add-form');
        if (formEl) {
          showFeedbackMessage('');
          // Teclado y chips quietos hasta que el servidor confirme la caja:
          // sin esto, un peso tecleado durante el envío se borraba al llegar
          // la respuesta, y un doble toque encolaba una segunda caja.
          setBusy(true);
        }
      });

      document.body.addEventListener('htmx:afterRequest', (event) => {
        if (event.target.closest && event.target.closest('#pesar-add-form')) {
          setBusy(false);
        }
      });

      document.body.addEventListener('htmx:afterSwap', (event) => {
        if (event.target.id === 'modal-root') {
          initEditModal(event.target);
          return;
        }
        if (event.target.id && event.target.id.startsWith('cajas-list-producto-')) {
          closeModal();
          resetWeight();
          refreshActivePanel();
        }
      });

      // Los chips llegan por OOB y pueden aplicarse después de `afterSwap`:
      // se vuelve a marcar el activo cuando todo quedó asentado.
      document.body.addEventListener('htmx:afterSettle', () => {
        screen.querySelectorAll('.pesar-chip').forEach((chip) => {
          chip.classList.toggle('is-active', Number.parseInt(chip.dataset.detalleId, 10) === state.activeId);
        });

        // «Imprimir al pesar»: la confirmación verde trae el id de la caja
        // recién registrada; con la Zebra conectada se imprime sola. Se
        // recuerda la última para no repetirla en el siguiente settle.
        const nueva = document.querySelector('#pesar-feedback.is-ok [data-etiqueta-caja][data-caja-id]');
        if (!nueva || !printerReady() || !printer.auto || !printer.auto.checked) return;
        const cajaId = Number.parseInt(nueva.dataset.cajaId, 10);
        if (!cajaId || cajaId === printer.ultimaImpresa) return;
        printer.ultimaImpresa = cajaId;
        printerPrintCaja(cajaId);
      });

      document.body.addEventListener('htmx:responseError', (event) => {
        const message = event.detail.xhr?.responseText || 'Ocurrió un error procesando la solicitud.';
        showFeedbackMessage(message);
      });
    }

    function initEditModal(root) {
      const modal = root.querySelector('[data-pesar-modal]');
      if (!modal) return;
      document.body.classList.add('is-pesar-modal-open');

      const overlay = modal;
      const formEl = modal.querySelector('form');
      const weightHidden = modal.querySelector('[data-edit-hidden-weight]');
      const weightVisible = modal.querySelector('[data-edit-weight-display]');

      function renderModalWeight() {
        weightVisible.textContent = weightHidden.value || '0';
      }

      function editPress(key) {
        let value = weightHidden.value || '';
        if (key === 'back') {
          weightHidden.value = value.slice(0, -1);
          renderModalWeight();
          return;
        }
        if (key === 'clear') {
          weightHidden.value = '';
          renderModalWeight();
          return;
        }
        if (key === '.') {
          if (!value.includes('.')) weightHidden.value = value ? `${value}.` : '0.';
          renderModalWeight();
          return;
        }
        if (/^\d$/.test(key)) {
          if (value === '0') {
            weightHidden.value = key;
            renderModalWeight();
            return;
          }
          if (value.includes('.') && value.split('.')[1].length >= 3) return;
          if (value.length >= 7) return;
          weightHidden.value = `${value}${key}`;
          renderModalWeight();
        }
      }

      modal.querySelectorAll('[data-modal-close]').forEach((button) => {
        button.addEventListener('click', closeModal);
      });

      overlay.addEventListener('click', (event) => {
        if (event.target === overlay) closeModal();
      });

      modal.querySelectorAll('[data-edit-key]').forEach((button) => {
        button.addEventListener('click', () => editPress(button.dataset.editKey));
      });

      modal.querySelectorAll('[data-edit-date-trigger]').forEach((button) => {
        button.addEventListener('click', () => {
          const field = button.dataset.editDateTrigger;
          const hidden = modal.querySelector(`[data-edit-date-input="${field}"]`);
          const display = modal.querySelector(`[data-edit-date-display="${field}"]`);
          const min = field === 'fecha_vencimiento'
            ? modal.querySelector('[data-edit-date-input="fecha_elaboracion"]').value
            : '';

          openDatePicker({
            title: field === 'fecha_elaboracion' ? 'Fecha de elaboración' : 'Fecha de vencimiento',
            value: hidden.value,
            min,
            accent: getComputedStyle(frame).getPropertyValue('--cat').trim(),
            onSelect: (iso) => {
              hidden.value = iso;
              display.textContent = formatISO(iso);
              if (field === 'fecha_elaboracion') {
                const vencHidden = modal.querySelector('[data-edit-date-input="fecha_vencimiento"]');
                const vencDisplay = modal.querySelector('[data-edit-date-display="fecha_vencimiento"]');
                if (vencHidden.value < iso) {
                  vencHidden.value = addYearsISO(iso, 1);
                  vencDisplay.textContent = formatISO(vencHidden.value);
                }
              }
            },
          });
        });
      });

      formEl?.addEventListener('htmx:beforeRequest', () => {
        showFeedbackMessage('');
      });

      renderModalWeight();
    }

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeModal();
    });

    loteInput.value = 'L-0001';
    syncDates();
    renderWeight();
    refreshActivePanel();
    loadLoteFromPanel();
    rememberActiveInUrl();
  });
})();
