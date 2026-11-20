/**
 * Controls the password lock screen overlay, login submission, and session logout.
 */
export class AuthController {
  /**
   * @param {import('./api.js').ApiClient} apiClient
   * @param {import('./i18n.js').I18nManager} i18n
   * @param {{ onLoginSuccess: () => void, onLogout: () => void }} callbacks
   */
  constructor(apiClient, i18n, callbacks) {
    this.api = apiClient;
    this.i18n = i18n;
    this.callbacks = callbacks;
  }

  /**
   * Attach login form and lock button event listeners.
   */
  init() {
    document.getElementById('login-form')?.addEventListener('submit', (event) => {
      this.handleLogin(event);
    });
    document.getElementById('btn-lock')?.addEventListener('click', () => {
      this.logout();
    });
  }

  /**
   * Return True while the password lock screen is blocking the dashboard.
   * @returns {boolean}
   */
  isLocked() {
    const screen = document.getElementById('lock-screen');
    return Boolean(screen && screen.classList.contains('active'));
  }

  /**
   * Reveal the password lock overlay and focus the password input field.
   */
  showLockScreen() {
    document.getElementById('lock-screen')?.classList.add('active');
    const lockBtn = document.getElementById('btn-lock');
    if (lockBtn) lockBtn.style.display = 'none';
    document.getElementById('pwd-field')?.focus();
  }

  /**
   * Dismiss the password lock overlay and clear previous login error messages.
   */
  hideLockScreen() {
    document.getElementById('lock-screen')?.classList.remove('active');
    const errorEl = document.getElementById('login-error');
    if (errorEl) errorEl.innerText = '';
  }

  /**
   * Submit credentials to `/api/login` and unlock the dashboard on success.
   * @param {SubmitEvent} event
   */
  async handleLogin(event) {
    event.preventDefault();
    const pwdField = document.getElementById('pwd-field');
    const errorDiv = document.getElementById('login-error');
    if (errorDiv) errorDiv.innerText = '';

    try {
      const { ok, data } = await this.api.login(pwdField.value);
      if (ok && data.success) {
        pwdField.value = '';
        this.hideLockScreen();
        this.callbacks.onLoginSuccess();
      } else if (errorDiv) {
        errorDiv.innerText = data.error || this.i18n.t('lock_screen.err_wrong_pwd', 'Wrong password');
      }
    } catch {
      if (errorDiv) {
        errorDiv.innerText = this.i18n.t('lock_screen.err_conn', 'Server connection error');
      }
    }
  }

  /**
   * Revoke the active session cookie and lock the dashboard UI.
   */
  async logout() {
    try {
      await this.api.logout();
    } catch {
      // Proceed to lock the UI even if the network request fails.
    }
    this.callbacks.onLogout();
    this.showLockScreen();
  }
}
