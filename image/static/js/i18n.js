/**
 * Internationalization (i18n) manager with auto-discovered locale packs and English fallback.
 */
export class I18nManager {
  static STORAGE_KEY = 'ups_language';
  static FALLBACK_LOCALE = 'en';

  /**
   * @param {import('./api.js').ApiClient} apiClient
   */
  constructor(apiClient) {
    this.api = apiClient;
    this.currentSetting = localStorage.getItem(I18nManager.STORAGE_KEY) || 'auto';
    this.activeCode = I18nManager.FALLBACK_LOCALE;
    this.availableLocales = [
      { code: 'en', name: 'English', flag: '🇬🇧' },
      { code: 'it', name: 'Italiano', flag: '🇮🇹' },
    ];
    this.loadedLocales = {};
    this.onChangeCallbacks = [];
  }

  /**
   * Register a callback invoked whenever the active language changes.
   * @param {() => void} callback
   */
  onChange(callback) {
    this.onChangeCallbacks.push(callback);
  }

  /**
   * Discover available locale packs from the backend, populate the selector, and apply the active language.
   */
  async init() {
    try {
      const data = await this.api.fetchLocales();
      if (data && Array.isArray(data.locales) && data.locales.length > 0) {
        this.availableLocales = data.locales;
      }
    } catch (err) {
      console.warn('Using built-in fallback locales list:', err);
    }

    this.populateLanguageSelect();
    await this.setLanguage(this.currentSetting, false);
  }

  /**
   * Populate the `<select id="cfg-language">` dropdown with auto-detection and discovered locales.
   */
  populateLanguageSelect() {
    const select = document.getElementById('cfg-language');
    if (!select) return;

    select.innerHTML = '';

    const autoOption = document.createElement('option');
    autoOption.value = 'auto';
    autoOption.setAttribute('data-i18n', 'tab_appearance.lang_auto');
    autoOption.textContent = '🌐 Automatic (Detected from browser)';
    select.appendChild(autoOption);

    this.availableLocales.forEach((loc) => {
      const option = document.createElement('option');
      option.value = loc.code;
      option.textContent = `${loc.flag} ${loc.name}`;
      select.appendChild(option);
    });

    select.value = this.currentSetting;
  }

  /**
   * Switch the active language, loading required JSON files and refreshing translated DOM nodes.
   * @param {string} langCode - ISO 639-1 code or `'auto'`.
   * @param {boolean} [save=true] - Whether to persist the selection in localStorage.
   */
  async setLanguage(langCode, save = true) {
    if (save) {
      localStorage.setItem(I18nManager.STORAGE_KEY, langCode);
      this.currentSetting = langCode;
    }

    let targetCode = I18nManager.FALLBACK_LOCALE;
    if (langCode === 'auto') {
      const browserLang = this.detectBrowserLanguage();
      const exists = this.availableLocales.some((loc) => loc.code === browserLang);
      targetCode = exists ? browserLang : I18nManager.FALLBACK_LOCALE;
    } else {
      targetCode = langCode;
    }

    this.activeCode = targetCode;

    // Always preload English so individual missing keys fall back cleanly.
    if (!this.loadedLocales[I18nManager.FALLBACK_LOCALE]) {
      await this.loadLocale(I18nManager.FALLBACK_LOCALE);
    }
    if (this.activeCode !== I18nManager.FALLBACK_LOCALE && !this.loadedLocales[this.activeCode]) {
      await this.loadLocale(this.activeCode);
    }

    const select = document.getElementById('cfg-language');
    if (select) {
      select.value = this.currentSetting;
    }

    this.applyTranslations();
    this.onChangeCallbacks.forEach((cb) => cb());
  }

  /**
   * Look up a dot-separated translation key with English fallback and optional default text.
   * @param {string} key
   * @param {string} [fallback='']
   * @returns {string}
   */
  t(key, fallback = '') {
    const val = this.lookup(key);
    return val !== null ? val : (fallback || key);
  }

  /**
   * Translate whitespace-separated NUT status flags (e.g. `"OL CHRG"`) using the active locale map.
   * @param {string} rawStatus
   * @returns {string}
   */
  translateUpsStatus(rawStatus) {
    if (!rawStatus) return this.t('cards.feed_online', 'Utility Power');
    const activeMap = this.loadedLocales[this.activeCode]?.ups_status_map || {};
    const englishMap = this.loadedLocales[I18nManager.FALLBACK_LOCALE]?.ups_status_map || {};
    const merged = Object.assign({}, englishMap, activeMap);

    if (merged[rawStatus]) return merged[rawStatus];
    return rawStatus
      .split(/\s+/)
      .map((token) => merged[token] || token)
      .join(' • ');
  }

  /**
   * Apply active translations to all declarative `data-i18n*` attributes in the document.
   */
  applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const value = this.lookup(el.getAttribute('data-i18n'));
      if (value !== null) el.innerText = value;
    });

    document.querySelectorAll('[data-i18n-html]').forEach((el) => {
      const value = this.lookup(el.getAttribute('data-i18n-html'));
      if (value !== null) el.innerHTML = value;
    });

    document.querySelectorAll('[data-i18n-ph]').forEach((el) => {
      const value = this.lookup(el.getAttribute('data-i18n-ph'));
      if (value !== null) el.placeholder = value;
    });

    document.querySelectorAll('[data-i18n-title]').forEach((el) => {
      const value = this.lookup(el.getAttribute('data-i18n-title'));
      if (value !== null) el.title = value;
    });

    document.documentElement.lang = this.activeCode;
  }

  /**
   * Fetch and cache a locale JSON file using the current application version as cache-buster.
   * @param {string} code
   * @returns {Promise<Record<string, unknown>|null>}
   */
  async loadLocale(code) {
    if (this.loadedLocales[code]) return this.loadedLocales[code];
    try {
      const appVersion = (document.querySelector('meta[name="app-version"]')?.content || '').trim();
      const cacheBust = appVersion && !appVersion.startsWith('__')
        ? `?v=${encodeURIComponent(appVersion)}`
        : '';
      const response = await fetch(`/locales/${code}.json${cacheBust}`, { cache: 'no-cache' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      this.loadedLocales[code] = payload;
      return payload;
    } catch (err) {
      console.warn(`Could not load locale "${code}":`, err);
      return null;
    }
  }

  /**
   * Look up a dot-separated translation key without falling back to the raw key name.
   * @param {string|null} key
   * @returns {string|null}
   */
  lookup(key) {
    if (!key) return null;
    let value = this.traversePath(this.loadedLocales[this.activeCode], key);
    if (value === null) {
      value = this.traversePath(this.loadedLocales[I18nManager.FALLBACK_LOCALE], key);
    }
    return value;
  }

  /**
   * Detect the browser's two-letter ISO 639-1 language code.
   * @returns {string}
   */
  detectBrowserLanguage() {
    const navLang = navigator.language || navigator.userLanguage || I18nManager.FALLBACK_LOCALE;
    return navLang.split('-')[0].toLowerCase();
  }

  /**
   * Traverse a nested object along a dot-delimited path and return a string leaf if present.
   * @param {Record<string, unknown>|undefined} obj
   * @param {string} path
   * @returns {string|null}
   */
  traversePath(obj, path) {
    if (!obj || !path) return null;
    let cursor = obj;
    for (const part of path.split('.')) {
      if (cursor && typeof cursor === 'object' && part in cursor) {
        cursor = cursor[part];
      } else {
        return null;
      }
    }
    return typeof cursor === 'string' ? cursor : null;
  }
}
