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
    const feedback = document.getElementById('pesar-feedback');
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

    function refreshActivePanel() {
      screen.querySelectorAll('.pesar-panel').forEach((panel) => {
        panel.classList.toggle('is-hidden', Number.parseInt(panel.dataset.detalleId, 10) !== state.activeId);
      });

      screen.querySelectorAll('.pesar-chip').forEach((chip) => {
        chip.classList.toggle('is-active', Number.parseInt(chip.dataset.detalleId, 10) === state.activeId);
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
      if (!feedback) return;
      feedback.textContent = message || '';
    }

    chipRow?.addEventListener('click', (event) => {
      const chip = event.target.closest('.pesar-chip');
      if (!chip) return;
      state.activeId = Number.parseInt(chip.dataset.detalleId, 10);
      refreshActivePanel();
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
          detalleInput.value = String(state.activeId);
          pesoHidden.value = state.weight;
          fechaElabHidden.value = state.fechaElaboracion;
          fechaVencHidden.value = state.fechaVencimiento;
          showFeedbackMessage('');
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
  });
})();
