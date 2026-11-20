/**
 * Selection-safe DOM mutation and HTML sanitization helpers.
 *
 * Periodic telemetry polling must avoid overwriting DOM nodes whose content
 * has not changed or that overlap the user's active text selection.
 */
export class DomHelper {
  /**
   * Resolve either a DOM element reference or an element ID string.
   * @param {HTMLElement|string|null} elOrId
   * @returns {HTMLElement|null}
   */
  static resolve(elOrId) {
    return typeof elOrId === 'string' ? document.getElementById(elOrId) : elOrId;
  }

  /**
   * Check whether a DOM node currently intersects the user's non-collapsed text selection.
   * @param {Node|null} node
   * @returns {boolean}
   */
  static isNodeSelected(node) {
    if (!node) return false;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.rangeCount === 0) return false;
    try {
      const range = selection.getRangeAt(0);
      if (typeof range.intersectsNode === 'function') {
        return range.intersectsNode(node);
      }
    } catch {
      // Ignore exotic detached or SVG node range exceptions.
    }
    return false;
  }

  /**
   * Update an element's textContent only when the text changed and is not selected.
   * @param {HTMLElement|string|null} elOrId
   * @param {unknown} text
   */
  static setText(elOrId, text) {
    const el = DomHelper.resolve(elOrId);
    if (!el) return;
    const value = String(text ?? '');
    if (el.textContent === value) return;
    if (DomHelper.isNodeSelected(el)) return;
    el.textContent = value;
  }

  /**
   * Update an element's className only when it differs from the target value.
   * @param {HTMLElement|string|null} elOrId
   * @param {string} className
   */
  static setClass(elOrId, className) {
    const el = DomHelper.resolve(elOrId);
    if (!el) return;
    if (el.className !== className) {
      el.className = className;
    }
  }

  /**
   * Update a single inline CSS style property only when its value changed.
   * @param {HTMLElement|string|null} elOrId
   * @param {string} prop
   * @param {string} value
   */
  static setStyle(elOrId, prop, value) {
    const el = DomHelper.resolve(elOrId);
    if (!el) return;
    if (el.style[prop] !== value) {
      el.style[prop] = value;
    }
  }

  /**
   * Escape HTML metacharacters to prevent XSS when injecting dynamic values into HTML.
   * @param {unknown} value
   * @returns {string}
   */
  static escapeHtml(value) {
    if (!value) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}
