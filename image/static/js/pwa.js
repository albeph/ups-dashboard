/**
 * Manages Progressive Web App (PWA) install prompts and Service Worker registration.
 */
export class PwaManager {
  constructor() {
    this.deferredPrompt = null;
  }

  /**
   * Listen for install prompt availability and register `/sw.js` on page load.
   */
  init() {
    const installBtn = document.getElementById('btn-install-pwa');

    window.addEventListener('beforeinstallprompt', (event) => {
      event.preventDefault();
      this.deferredPrompt = event;
      if (installBtn) {
        installBtn.style.display = 'inline-flex';
      }
    });

    installBtn?.addEventListener('click', () => this.triggerInstall());

    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch((err) => {
          console.debug('Service Worker registration note:', err);
        });
      });
    }
  }

  /**
   * Present the browser's native PWA installation prompt when available.
   */
  async triggerInstall() {
    if (!this.deferredPrompt) return;
    this.deferredPrompt.prompt();
    const choice = await this.deferredPrompt.userChoice;
    if (choice && choice.outcome === 'accepted') {
      const installBtn = document.getElementById('btn-install-pwa');
      if (installBtn) installBtn.style.display = 'none';
    }
    this.deferredPrompt = null;
  }
}
