/* =============================================================================
   PesosApp · Dashboard Tabs Controller · Phase 3
   X-style horizontal tab bar with animated indicator underline.
   ============================================================================= */

/* eslint-env browser */
/* global */

'use strict';

/**
 * DashboardTabs — X-style horizontal tab controller.
 *
 * Usage:
 *   <div data-dashboard-tabs>
 *     <nav class="dash-tabs" role="tablist" aria-label="Dashboard sections">
 *       <button class="dash-tab" role="tab" data-tab="ventas" aria-selected="true">Ventas</button>
 *       <button class="dash-tab" role="tab" data-tab="servicio">Servicio</button>
 *       …
 *       <span class="dash-tabs-indicator" aria-hidden="true"></span>
 *     </nav>
 *     <div class="tab-panels" id="dashboardCarousel">
 *       <div class="tab-panel active" data-panel="ventas">…</div>
 *       …
 *     </div>
 *   </div>
 */
class DashboardTabs {
    /**
     * @param {HTMLElement} root — the [data-dashboard-tabs] container
     * @param {object}      opts — optional overrides
     */
    constructor(root, opts = {}) {
        this.root      = root;
        this.nav       = root.querySelector('.dash-tabs');
        this.indicator = root.querySelector('.dash-tabs-indicator');
        this.tabs      = Array.from(root.querySelectorAll('.dash-tab'));
        this.panels    = Array.from(root.querySelectorAll('.tab-panel'));
        this.panelsContainer = root.querySelector('.tab-panels') || root;
        this.onActivate = opts.onActivate || null;   // callback(panelKey)

        if (!this.nav || !this.tabs.length) return;

        this._bindEvents();
        this._bindKeyboard();
        this._bindSwipe();
        // Activate the tab that is pre-selected (aria-selected="true") or the first
        const initial = this.tabs.find(t => t.getAttribute('aria-selected') === 'true')
            || this.tabs[0];
        this.activate(initial.dataset.tab, { animate: false });
    }

    /**
     * Activate a tab by its data-tab key.
     * @param {string} key      — panel key, e.g. "ventas"
     * @param {object} options  — { animate: bool }
     */
    activate(key, options = {}) {
        const tab   = this.tabs.find(t => t.dataset.tab === key);
        const panel = this.panels.find(p => p.dataset.panel === key);
        if (!tab) return;

        // Update tab aria state
        this.tabs.forEach(t => {
            const isActive = t.dataset.tab === key;
            t.setAttribute('aria-selected', String(isActive));
            t.classList.toggle('is-active', isActive);
        });

        // Update panel visibility
        this.panels.forEach(p => {
            const isActive = p.dataset.panel === key;
            p.classList.toggle('active', isActive);
            p.setAttribute('aria-hidden', String(!isActive));
        });

        // Move the indicator
        const animate = options.animate !== false;
        this._moveIndicator(tab, animate);

        if (typeof this.onActivate === 'function') {
            this.onActivate(key);
        }
    }

    /**
     * Move the sliding indicator under `tab`.
     * @private
     */
    _moveIndicator(tab, animate) {
        if (!this.indicator || !tab) return;

        const navRect = this.nav.getBoundingClientRect();
        const tabRect = tab.getBoundingClientRect();

        const left  = tabRect.left  - navRect.left + this.nav.scrollLeft;
        const width = tabRect.width;

        if (!animate) {
            this.indicator.style.transition = 'none';
            this.indicator.style.transform  = `translateX(${left}px)`;
            this.indicator.style.width      = `${width}px`;
            // Re-enable transition on next frame
            requestAnimationFrame(() => {
                this.indicator.style.transition = '';
            });
        } else {
            this.indicator.style.transform = `translateX(${left}px)`;
            this.indicator.style.width     = `${width}px`;
        }
    }

    /** @private */
    _bindEvents() {
        this.tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                this.activate(tab.dataset.tab);
            });
        });

        // Re-position indicator on resize (debounced)
        let resizeTimer;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                const activeTab = this.tabs.find(t => t.getAttribute('aria-selected') === 'true');
                if (activeTab) this._moveIndicator(activeTab, false);
            }, 120);
        });
    }

    /** @private — keyboard ← / → navigation within the tab bar */
    _bindKeyboard() {
        this.tabs.forEach((tab, i) => {
            tab.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    const nextIdx = Math.min(this.tabs.length - 1, i + 1);
                    const nextTab = this.tabs[nextIdx];
                    this.activate(nextTab.dataset.tab);
                    nextTab.focus();
                } else if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    const prevIdx = Math.max(0, i - 1);
                    const prevTab = this.tabs[prevIdx];
                    this.activate(prevTab.dataset.tab);
                    prevTab.focus();
                }
            });
        });
    }

    /** @private — horizontal swipe on the panel body advances the adjacent tab */
    _bindSwipe() {
        let startX = 0;
        let startY = 0;
        let tracking = false;
        const THRESHOLD = 50;

        this.panelsContainer.addEventListener('touchstart', (e) => {
            if (e.touches.length !== 1) return;
            startX = e.touches[0].clientX;
            startY = e.touches[0].clientY;
            tracking = true;
        }, { passive: true });

        this.panelsContainer.addEventListener('touchend', (e) => {
            if (!tracking) return;
            tracking = false;
            const t = e.changedTouches[0];
            const dx = t.clientX - startX;
            const dy = t.clientY - startY;
            // Ignore if mostly vertical (user was scrolling)
            if (Math.abs(dy) > Math.abs(dx)) return;
            const activeTab = this.tabs.find(tab => tab.getAttribute('aria-selected') === 'true');
            const activeIdx = this.tabs.indexOf(activeTab);
            if (dx <= -THRESHOLD) {
                const nextTab = this.tabs[Math.min(this.tabs.length - 1, activeIdx + 1)];
                this.activate(nextTab.dataset.tab);
            } else if (dx >= THRESHOLD) {
                const prevTab = this.tabs[Math.max(0, activeIdx - 1)];
                this.activate(prevTab.dataset.tab);
            }
        }, { passive: true });
    }
}

// Auto-init on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    const roots = document.querySelectorAll('[data-dashboard-tabs]');
    roots.forEach(root => {
        // Expose instance on the element for external access (e.g. chart callbacks)
        root._dashboardTabs = new DashboardTabs(root);
    });
});
