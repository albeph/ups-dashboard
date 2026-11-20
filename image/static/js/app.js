import { ApiClient } from './api.js';
import { AuthController } from './auth.js';
import { BlackoutTracker } from './blackout.js';
import { I18nManager } from './i18n.js';
import { PwaManager } from './pwa.js';
import { SettingsModalController } from './settings.js';
import { TelemetryRenderer } from './telemetry.js';
import { TooltipManager } from './tooltip.js';

/**
 * Main frontend orchestrator wiring all dashboard controllers and managing the polling lifecycle.
 */
export class DashboardApp {
  constructor() {
    this.api = new ApiClient();
    this.i18n = new I18nManager(this.api);
    this.tooltips = new TooltipManager();
    this.blackoutTracker = new BlackoutTracker();
    this.renderer = new TelemetryRenderer(this.i18n, this.tooltips, this.blackoutTracker);
    this.pwa = new PwaManager();

    this.pollIntervalMs = 2000;
    this.pollTimerId = null;

    this.auth = new AuthController(this.api, this.i18n, {
      onLoginSuccess: () => {
        this.pollStats();
        this.restartPolling(this.pollIntervalMs / 1000);
      },
      onLogout: () => {
        this.stopPolling();
      },
    });

    this.settings = new SettingsModalController(
      this.api,
      this.i18n,
      this.renderer,
      this.tooltips,
      {
        onUnauthorized: () => {
          this.stopPolling();
          this.auth.showLockScreen();
        },
        onSettingsSaved: (pollIntervalSec) => {
          this.restartPolling(pollIntervalSec);
          setTimeout(() => this.pollStats(), 1200);
        },
      }
    );
  }

  /**
   * Initialize all UI controllers, load locales, and begin live telemetry polling.
   */
  async start() {
    this.tooltips.init();
    this.renderer.init();
    this.auth.init();
    this.settings.init();
    this.pwa.init();

    this.i18n.onChange(() => {
      this.renderer.rerender();
      this.settings.refreshLanguage();
    });

    this.bindVisibilityLifecycle();

    await this.i18n.init();
    await this.pollStats();
    this.restartPolling(this.pollIntervalMs / 1000);
  }

  /**
   * Fetch the latest telemetry snapshot and update the UI or trigger authentication lock.
   */
  async pollStats() {
    try {
      const result = await this.api.fetchStats();
      if (result.unauthorized) {
        this.stopPolling();
        this.auth.showLockScreen();
        return;
      }

      const data = result.data;
      this.auth.hideLockScreen();

      if (data.poll_interval && typeof data.poll_interval === 'number') {
        const expectedMs = Math.round(data.poll_interval * 1000);
        if (expectedMs !== this.pollIntervalMs) {
          this.restartPolling(data.poll_interval);
        }
      }

      this.renderer.render(data);
    } catch {
      this.renderer.render({ status: 'offline', watts: null, load: 0, battery: 0 });
    }
  }

  /**
   * Start or reschedule the periodic telemetry polling interval.
   * @param {number} seconds
   */
  restartPolling(seconds) {
    const parsed = parseFloat(String(seconds));
    if (!Number.isNaN(parsed) && parsed >= 0.5) {
      this.pollIntervalMs = Math.round(parsed * 1000);
    }
    this.stopPolling();
    if (!document.hidden && !this.auth.isLocked()) {
      this.pollTimerId = setInterval(() => this.pollStats(), this.pollIntervalMs);
    }
  }

  /**
   * Halt periodic telemetry polling.
   */
  stopPolling() {
    if (this.pollTimerId) {
      clearInterval(this.pollTimerId);
      this.pollTimerId = null;
    }
  }

  /**
   * Pause polling and client-side timers when the tab is hidden so the backend can enter standby.
   */
  bindVisibilityLifecycle() {
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        this.stopPolling();
        this.blackoutTracker.pause();
        this.tooltips.hide();
      } else if (!this.auth.isLocked()) {
        this.pollStats();
        if (!this.pollTimerId) {
          this.pollTimerId = setInterval(() => this.pollStats(), this.pollIntervalMs);
        }
        this.blackoutTracker.resume();
      }
    });
  }
}

// Bootstrap the application once the DOM is ready.
const app = new DashboardApp();
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => app.start());
} else {
  app.start();
}
