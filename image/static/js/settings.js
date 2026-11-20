import { DurationFormatter } from './blackout.js';
import { DomHelper } from './dom.js';
import { TelemetryRenderer } from './telemetry.js';

/**
 * Controls the tabbed Settings modal (Status, NUT Server, Appearance, Security).
 */
export class SettingsModalController {
  static TABS = ['status', 'nut', 'appearance', 'security'];

  /**
   * @param {import('./api.js').ApiClient} apiClient
   * @param {import('./i18n.js').I18nManager} i18n
   * @param {TelemetryRenderer} renderer
   * @param {import('./tooltip.js').TooltipManager} tooltips
   * @param {{ onUnauthorized: () => void, onSettingsSaved: (pollInterval: number) => void }} callbacks
   */
  constructor(apiClient, i18n, renderer, tooltips, callbacks) {
    this.api = apiClient;
    this.i18n = i18n;
    this.renderer = renderer;
    this.tooltips = tooltips;
    this.callbacks = callbacks;
    this.lastSettingsData = null;
  }

  /**
   * Bind all modal DOM event listeners (tabs, presets, mode cards, language select, form submit).
   */
  init() {
    document.getElementById('btn-open-settings')?.addEventListener('click', () => this.open());
    document.getElementById('btn-close-settings')?.addEventListener('click', () => this.close());
    document.getElementById('btn-cancel-settings')?.addEventListener('click', () => this.close());

    SettingsModalController.TABS.forEach((tab) => {
      document
        .getElementById(`tab-btn-${tab}`)
        ?.addEventListener('click', () => this.switchTab(tab));
    });

    const pollInput = document.getElementById('cfg-poll-interval');
    pollInput?.addEventListener('input', (event) => {
      this.setPollIntervalValue(event.target.value, false);
    });

    document.querySelectorAll('.preset-btn[data-poll-preset]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.setPollIntervalValue(btn.dataset.pollPreset, true);
      });
    });

    document.getElementById('opt-mode-bars')?.addEventListener('click', () => {
      this.tooltips.hide();
      this.renderer.setDisplayMode('bars', true);
    });
    document.getElementById('opt-mode-gauge')?.addEventListener('click', () => {
      this.tooltips.hide();
      this.renderer.setDisplayMode('gauge', true);
    });

    document.getElementById('cfg-language')?.addEventListener('change', (event) => {
      this.i18n.setLanguage(event.target.value, true);
    });

    document.getElementById('settings-form')?.addEventListener('submit', (event) => {
      this.handleSubmit(event);
    });
  }

  /**
   * Return True if the settings modal overlay is currently visible.
   * @returns {boolean}
   */
  isOpen() {
    const modal = document.getElementById('settings-modal');
    return Boolean(modal && modal.classList.contains('active'));
  }

  /**
   * Re-populate modal content using the last fetched payload (e.g. after changing language).
   */
  refreshLanguage() {
    if (this.lastSettingsData && this.isOpen()) {
      this.populate(this.lastSettingsData);
    }
  }

  /**
   * Fetch current settings and diagnostics from the backend and open the modal.
   */
  async open() {
    const toast = document.getElementById('settings-toast');
    if (toast) toast.innerText = '';

    try {
      const result = await this.api.fetchSettings();
      if (result.unauthorized) {
        this.callbacks.onUnauthorized();
        return;
      }

      const cfg = result.data;
      document.getElementById('cfg-nut-pwd').value = '';
      document.getElementById('cfg-dash-pwd').value = '';

      this.populate(cfg);
      this.switchTab('status');

      DomHelper.setText(
        'info-target-server',
        `${this.i18n.t('subbar.target_nut', 'Target NUT')}: ${cfg.nut_host}:${cfg.nut_port} (${cfg.ups_name})`
      );
      document.getElementById('settings-modal')?.classList.add('active');
    } catch (err) {
      alert(this.i18n.t('toasts.alert_load_fail', 'Unable to load settings: ') + err.message);
    }
  }

  /**
   * Hide the settings modal overlay.
   */
  close() {
    document.getElementById('settings-modal')?.classList.remove('active');
  }

  /**
   * Activate a specific modal tab pane and scroll its button into view on narrow viewports.
   * @param {'status'|'nut'|'appearance'|'security'} tabName
   */
  switchTab(tabName) {
    SettingsModalController.TABS.forEach((tab) => {
      const button = document.getElementById(`tab-btn-${tab}`);
      const pane = document.getElementById(`tab-pane-${tab}`);
      const isActive = tab === tabName;
      if (button) {
        button.classList.toggle('active', isActive);
        if (isActive) {
          button.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
        }
      }
      if (pane) {
        pane.style.display = isActive ? 'block' : 'none';
      }
    });
  }

  /**
   * Sync the polling interval input and highlight the matching preset button.
   * @param {string|number} seconds
   * @param {boolean} [updateInput=true]
   */
  setPollIntervalValue(seconds, updateInput = true) {
    const parsed = parseFloat(String(seconds));
    if (updateInput && !Number.isNaN(parsed)) {
      const input = document.getElementById('cfg-poll-interval');
      if (input) input.value = String(parsed);
    }
    document.querySelectorAll('.preset-btn[data-poll-preset]').forEach((btn) => {
      btn.classList.toggle('active', parseFloat(btn.dataset.pollPreset) === parsed);
    });
  }

  /**
   * Populate all four settings tabs from the `/api/settings` JSON payload.
   * @param {Record<string, any>} cfg
   */
  populate(cfg) {
    this.lastSettingsData = cfg;
    const isOnline = cfg.server_status === 'online';
    const statusFlags = TelemetryRenderer.parseStatusFlags(cfg.ups_status_raw);
    const isBattery = statusFlags.includes('OB');
    const pollSec = cfg.poll_interval || 2.0;

    this.populateNutFormFields(cfg, pollSec);
    this.populateStatusTab(cfg, isOnline, isBattery, statusFlags, pollSec);
    this.populateNutBanner(cfg, isOnline);
    this.populateSecurityBanner(cfg);

    const langSelect = document.getElementById('cfg-language');
    if (langSelect) {
      langSelect.value = this.i18n.currentSetting;
    }

    this.renderer.setDisplayMode(this.renderer.currentMode, false);
  }

  /**
   * Populate connection form inputs in the NUT Server tab.
   * @param {Record<string, any>} cfg
   * @param {number} pollSec
   */
  populateNutFormFields(cfg, pollSec) {
    document.getElementById('cfg-host').value = cfg.nut_host || '';
    document.getElementById('cfg-port').value = cfg.nut_port || 3493;
    document.getElementById('cfg-ups-name').value = cfg.ups_name || 'ups';
    document.getElementById('cfg-nut-user').value = cfg.nut_user || '';
    this.setPollIntervalValue(pollSec, true);

    const nutPwdInput = document.getElementById('cfg-nut-pwd');
    if (nutPwdInput) {
      nutPwdInput.placeholder = cfg.has_nut_password
        ? this.i18n.t('tab_nut.ph_nut_pwd_set', '•••••••• (already set)')
        : this.i18n.t('tab_nut.ph_nut_pwd_unset', 'No password set');
    }
  }

  /**
   * Populate read-only NUT connection and UPS operational diagnostics in the Status tab.
   * @param {Record<string, any>} cfg
   * @param {boolean} isOnline
   * @param {boolean} isBattery
   * @param {string[]} statusFlags
   * @param {number} pollSec
   */
  populateStatusTab(cfg, isOnline, isBattery, statusFlags, pollSec) {
    DomHelper.setClass('stat-pill-conn', isOnline ? 'status-pill online' : 'status-pill offline');
    DomHelper.setText(
      'stat-pill-conn',
      isOnline
        ? this.i18n.t('tab_status.conn_online', 'ONLINE')
        : this.i18n.t('tab_status.conn_offline', 'OFFLINE')
    );

    DomHelper.setText('stat-val-target', `${cfg.nut_host}:${cfg.nut_port}`);
    DomHelper.setText('stat-val-ups', cfg.ups_name || 'ups');

    const syncTime = cfg.last_update
      ? new Date(cfg.last_update * 1000).toLocaleTimeString()
      : this.i18n.t('tab_status.waiting', 'Waiting...');
    DomHelper.setText('stat-val-sync', syncTime);

    const errBox = document.getElementById('stat-box-error');
    if (errBox) {
      if (!isOnline && cfg.error_message) {
        errBox.style.display = 'flex';
        DomHelper.setText('stat-msg-error', cfg.error_message);
      } else {
        errBox.style.display = 'none';
      }
    }

    if (!isOnline) {
      DomHelper.setClass('stat-pill-mode', 'status-pill offline');
      DomHelper.setText('stat-pill-mode', this.i18n.t('tab_status.status_offline', 'OFFLINE'));
    } else if (isBattery) {
      DomHelper.setClass('stat-pill-mode', 'status-pill warning');
      DomHelper.setText(
        'stat-pill-mode',
        this.i18n.t('tab_status.status_battery', 'ON BATTERY (OB)')
      );
    } else {
      DomHelper.setClass('stat-pill-mode', 'status-pill online');
      DomHelper.setText('stat-pill-mode', this.i18n.t('tab_status.status_online', 'ONLINE (OL)'));
    }

    let feedText = this.i18n.t('cards.feed_online', 'Utility Power');
    if (!isOnline) {
      feedText = this.i18n.t('subbar.nut_unreachable', 'NUT server unreachable');
    } else if (isBattery) {
      feedText = this.i18n.t('cards.feed_battery', 'Battery');
    } else if (statusFlags.includes('BYPASS')) {
      feedText = this.i18n.t('cards.feed_bypass', 'Bypass');
    }
    DomHelper.setText('stat-val-mode', feedText);

    DomHelper.setText(
      'stat-val-model',
      cfg.ups_model || this.i18n.t('tab_status.model_generic', 'Not detected or generic')
    );
    DomHelper.setText('stat-val-maxwatts', isOnline && cfg.nominal_watts ? `${cfg.nominal_watts} W` : '--');

    const metricsTpl = this.i18n.t('tab_status.metrics_unit', '{load}% load • {batt}% battery');
    const metricsStr = isOnline
      ? metricsTpl.replace('{load}', String(cfg.load || 0)).replace('{batt}', String(cfg.battery || 0))
      : '--';
    DomHelper.setText('stat-val-metrics', metricsStr);
    DomHelper.setText('stat-val-poll', `${pollSec}s`);

    if (isOnline && cfg.voltage !== null && cfg.voltage !== undefined) {
      const value = Number(cfg.voltage);
      DomHelper.setText('stat-val-voltage', `${value % 1 === 0 ? Math.round(value) : value.toFixed(1)} V`);
    } else {
      DomHelper.setText('stat-val-voltage', isOnline ? '-- V' : '--');
    }

    if (isOnline && cfg.battery_charge_low !== null && cfg.battery_charge_low !== undefined) {
      DomHelper.setText('stat-val-charge-low', `${Math.round(Number(cfg.battery_charge_low))}%`);
    } else {
      DomHelper.setText('stat-val-charge-low', '--');
    }

    if (isOnline && cfg.battery_runtime_low !== null && cfg.battery_runtime_low !== undefined) {
      DomHelper.setText(
        'stat-val-runtime-low',
        DurationFormatter.formatThreshold(Number(cfg.battery_runtime_low))
      );
    } else {
      DomHelper.setText('stat-val-runtime-low', '--');
    }
  }

  /**
   * Render the connection status banner inside the NUT Server tab.
   * @param {Record<string, any>} cfg
   * @param {boolean} isOnline
   */
  populateNutBanner(cfg, isOnline) {
    const banner = document.getElementById('nut-status-banner');
    if (!banner) return;

    if (isOnline) {
      banner.className = 'security-status protected';
      banner.style.color = '#34d399';
      banner.style.borderColor = 'rgba(52, 211, 153, 0.3)';
      banner.innerHTML = `
        <span class="status-dot"></span>
        <span><strong>${DomHelper.escapeHtml(this.i18n.t('tab_nut.status_connected', 'Server Connected'))}</strong>: ${DomHelper.escapeHtml(cfg.nut_host)}:${DomHelper.escapeHtml(cfg.nut_port)} (${DomHelper.escapeHtml(cfg.ups_name)})</span>
      `;
    } else {
      banner.className = 'security-status';
      banner.style.color = '#ef4444';
      banner.style.borderColor = 'rgba(239, 68, 68, 0.3)';
      banner.innerHTML = `
        <span class="status-dot offline"></span>
        <span><strong>${DomHelper.escapeHtml(this.i18n.t('tab_nut.status_not_connected', 'Server Disconnected'))}</strong>: ${DomHelper.escapeHtml(cfg.error_message || this.i18n.t('tab_nut.status_unreachable', 'Unreachable'))}</span>
      `;
    }
  }

  /**
   * Render the authentication protection status banner inside the Security tab.
   * @param {Record<string, any>} cfg
   */
  populateSecurityBanner(cfg) {
    const badge = document.getElementById('security-status-badge');
    if (!badge) return;

    if (cfg.has_dashboard_password) {
      badge.className = 'security-status protected';
      badge.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
        </svg>
        <span><strong>${DomHelper.escapeHtml(this.i18n.t('tab_security.status_protected_strong', 'Protected Access'))}</strong>${DomHelper.escapeHtml(this.i18n.t('tab_security.status_protected_desc', ': Dashboard requires password authentication.'))}</span>
      `;
    } else {
      badge.className = 'security-status';
      badge.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line>
        </svg>
        <span><strong>${DomHelper.escapeHtml(this.i18n.t('tab_security.status_open_strong', 'Open Access'))}</strong>${DomHelper.escapeHtml(this.i18n.t('tab_security.status_open_desc', ': No password configured for the dashboard.'))}</span>
      `;
    }
  }

  /**
   * Validate inputs and submit updated settings to `POST /api/settings`.
   * @param {SubmitEvent} event
   */
  async handleSubmit(event) {
    event.preventDefault();
    const toast = document.getElementById('settings-toast');
    const setToast = (color, message) => {
      if (!toast) return;
      toast.style.color = color;
      toast.innerText = message;
    };

    setToast('#38bdf8', this.i18n.t('toasts.saving', 'Saving settings...'));

    const host = document.getElementById('cfg-host').value.trim();
    const port = parseInt(document.getElementById('cfg-port').value, 10);
    const upsName = document.getElementById('cfg-ups-name').value.trim();

    if (!host || Number.isNaN(port) || !upsName) {
      this.switchTab('nut');
      setToast(
        '#ef4444',
        this.i18n.t('toasts.err_required_fields', 'Please fill in Host, Port and UPS Name in NUT Server tab.')
      );
      return;
    }

    const pollInterval = parseFloat(document.getElementById('cfg-poll-interval').value);
    if (Number.isNaN(pollInterval) || pollInterval < 0.5) {
      this.switchTab('nut');
      setToast(
        '#ef4444',
        this.i18n.t('toasts.err_invalid_poll', 'Invalid update interval (minimum 0.5 seconds).')
      );
      return;
    }

    const payload = {
      nut_host: host,
      nut_port: port,
      ups_name: upsName,
      nut_user: document.getElementById('cfg-nut-user').value.trim(),
      poll_interval: pollInterval,
    };

    const nutPwd = document.getElementById('cfg-nut-pwd').value;
    if (nutPwd) payload.nut_password = nutPwd;

    const dashPwd = document.getElementById('cfg-dash-pwd').value;
    if (dashPwd) payload.new_dashboard_password = dashPwd;

    try {
      const { ok, data } = await this.api.saveSettings(payload);
      if (ok && data.success) {
        setToast('#10b981', this.i18n.t('toasts.saved', 'Settings saved successfully!'));
        DomHelper.setText(
          'info-target-server',
          `${this.i18n.t('subbar.target_nut', 'Target NUT')}: ${payload.nut_host}:${payload.nut_port} (${payload.ups_name})`
        );
        this.callbacks.onSettingsSaved(pollInterval);
        setTimeout(() => {
          this.close();
        }, 1200);
      } else {
        setToast(
          '#ef4444',
          this.i18n.t('toasts.err_prefix', 'Error: ') + (data.error || 'Save failed')
        );
      }
    } catch {
      setToast('#ef4444', this.i18n.t('toasts.err_network', 'Network error while saving settings'));
    }
  }
}
