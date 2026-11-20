/**
 * REST API client encapsulating all HTTP communication with the Python backend.
 */
export class ApiClient {
  /**
   * Fetch live UPS telemetry from `GET /api/stats`.
   * @returns {Promise<{unauthorized: boolean, data: Record<string, any>|null}>}
   */
  async fetchStats() {
    const response = await fetch('/api/stats');
    if (response.status === 401) {
      return { unauthorized: true, data: null };
    }
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return { unauthorized: false, data: await response.json() };
  }

  /**
   * Fetch non-sensitive settings and diagnostics from `GET /api/settings`.
   * @returns {Promise<{unauthorized: boolean, data: Record<string, any>|null}>}
   */
  async fetchSettings() {
    const response = await fetch('/api/settings');
    if (response.status === 401) {
      return { unauthorized: true, data: null };
    }
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return { unauthorized: false, data: await response.json() };
  }

  /**
   * Save updated configuration settings via `POST /api/settings`.
   * @param {Record<string, any>} payload
   * @returns {Promise<{ok: boolean, data: Record<string, any>}>}
   */
  async saveSettings(payload) {
    const response = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return { ok: response.ok, data: await response.json() };
  }

  /**
   * Authenticate with the dashboard password via `POST /api/login`.
   * @param {string} password
   * @returns {Promise<{ok: boolean, data: Record<string, any>}>}
   */
  async login(password) {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    return { ok: response.ok, data: await response.json() };
  }

  /**
   * Terminate the active authenticated session via `POST /api/logout`.
   */
  async logout() {
    await fetch('/api/logout', { method: 'POST' });
  }

  /**
   * Retrieve the auto-discovered localization list from `GET /api/locales`.
   * @returns {Promise<Record<string, any>|null>}
   */
  async fetchLocales() {
    const response = await fetch('/api/locales');
    if (!response.ok) return null;
    return response.json();
  }
}
