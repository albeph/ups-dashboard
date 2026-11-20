/**
 * Viewport-clamped floating tooltip controller supporting mouse hover, touch tap, and keyboard focus.
 *
 * Uses a single fixed `#ui-tooltip` element outside `.dashboard-panel` so tooltips
 * are never clipped by `overflow: hidden` containers and work reliably on mobile touchscreens.
 */
export class TooltipManager {
  /**
   * @param {string} [tooltipElementId='ui-tooltip']
   */
  constructor(tooltipElementId = 'ui-tooltip') {
    this.tooltipElementId = tooltipElementId;
    this.activeTarget = null;
  }

  /**
   * Attach global dismissal listeners (outside click, Escape key, scroll, and viewport resize).
   */
  init() {
    document.addEventListener('click', (event) => {
      if (this.activeTarget && !this.activeTarget.contains(event.target)) {
        this.hide();
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        this.hide();
      }
    });

    window.addEventListener('scroll', () => this.hide(), { passive: true });
    window.addEventListener('resize', () => {
      if (this.activeTarget) {
        this.position(this.activeTarget);
      }
    });
  }

  /**
   * Bind pointer, click, and keyboard focus interactions to a tooltip trigger element.
   * @param {HTMLElement|SVGElement|null} element
   */
  bindTarget(element) {
    if (!element) return;

    element.addEventListener('pointerdown', () => {
      element.dataset.pointerDown = '1';
    });

    element.addEventListener('pointerenter', (event) => {
      if (event.pointerType === 'mouse' && element.dataset.tooltip) {
        this.show(element);
      }
    });

    element.addEventListener('pointerleave', (event) => {
      if (event.pointerType === 'mouse' && this.activeTarget === element) {
        this.hide();
      }
    });

    element.addEventListener('click', (event) => {
      delete element.dataset.pointerDown;
      if (!element.dataset.tooltip) return;
      event.stopPropagation();
      if (this.activeTarget === element) {
        this.hide();
      } else {
        this.show(element);
      }
    });

    element.addEventListener('focus', () => {
      if (element.dataset.pointerDown === '1') {
        delete element.dataset.pointerDown;
        return;
      }
      if (element.dataset.tooltip) {
        this.show(element);
      }
    });

    element.addEventListener('blur', () => {
      delete element.dataset.pointerDown;
      if (this.activeTarget === element) {
        this.hide();
      }
    });
  }

  /**
   * Update the tooltip copy associated with a target element (and refresh if currently visible).
   * @param {HTMLElement|SVGElement|null} element
   * @param {string} text
   */
  setText(element, text) {
    if (!element) return;
    if (!text) {
      delete element.dataset.tooltip;
      if (this.activeTarget === element) {
        this.hide();
      }
      return;
    }

    element.dataset.tooltip = text;
    element.setAttribute('aria-label', text);

    if (this.activeTarget === element) {
      const tip = document.getElementById(this.tooltipElementId);
      if (tip && tip.textContent !== text) {
        tip.textContent = text;
        this.position(element);
      }
    }
  }

  /**
   * Display and position the floating tooltip anchored to `targetElement`.
   * @param {HTMLElement|SVGElement|null} targetElement
   */
  show(targetElement) {
    const tip = document.getElementById(this.tooltipElementId);
    if (!tip || !targetElement) return;
    const text = targetElement.dataset.tooltip;
    if (!text) return;

    if (this.activeTarget && this.activeTarget !== targetElement) {
      this.activeTarget.classList.remove('tooltip-open');
    }

    this.activeTarget = targetElement;
    targetElement.classList.add('tooltip-open');
    tip.textContent = text;
    tip.classList.add('visible');
    this.position(targetElement);
  }

  /**
   * Hide the currently displayed tooltip and clear active target state.
   */
  hide() {
    const tip = document.getElementById(this.tooltipElementId);
    if (tip) {
      tip.classList.remove('visible');
    }
    if (this.activeTarget) {
      this.activeTarget.classList.remove('tooltip-open');
      this.activeTarget = null;
    }
  }

  /**
   * Position the tooltip above (or below if clipped) the anchor while clamping within viewport margins.
   * @param {HTMLElement|SVGElement} targetElement
   */
  position(targetElement) {
    const tip = document.getElementById(this.tooltipElementId);
    if (!tip || !targetElement) return;

    const anchorRect = targetElement.getBoundingClientRect();
    if (anchorRect.width === 0 && anchorRect.height === 0) {
      this.hide();
      return;
    }

    const margin = 10;
    const gap = 10;
    const tipRect = tip.getBoundingClientRect();

    let left = anchorRect.left + anchorRect.width / 2 - tipRect.width / 2;
    left = Math.max(margin, Math.min(window.innerWidth - tipRect.width - margin, left));

    let top = anchorRect.top - tipRect.height - gap;
    if (top < margin) {
      top = anchorRect.bottom + gap;
    }
    top = Math.max(margin, Math.min(window.innerHeight - tipRect.height - margin, top));

    tip.style.left = `${Math.round(left)}px`;
    tip.style.top = `${Math.round(top)}px`;
  }
}
