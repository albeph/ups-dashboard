import { DurationFormatter } from './blackout.js';
import { DomHelper } from './dom.js';

/**
 * Renders live UPS telemetry across both display modes (Horizontal Bars and Semicircle SVG Gauge).
 *
 * All DOM updates use `DomHelper` so active user text selections are never interrupted
 * during periodic background refreshes.
 */
export class TelemetryRenderer {
  static VIEW_MODE_STORAGE_KEY = 'ups_view_mode';
  static GAUGE_ARC_LENGTH = 110;

  /**
   * @param {import('./i18n.js').I18nManager} i18n
   * @param {import('./tooltip.js').TooltipManager} tooltips
   * @param {import('./blackout.js').BlackoutTracker} blackoutTracker
   */
  constructor(i18n, tooltips, blackoutTracker) {
    this.i18n = i18n;
    this.tooltips = tooltips;
    this.blackoutTracker = blackoutTracker;
    this.currentMode = localStorage.getItem(TelemetryRenderer.VIEW_MODE_STORAGE_KEY) || 'bars';
    this.lastData = null;
  }

  /**
   * Apply initial display mode and register interactive tooltip targets.
   */
  init() {
    this.setDisplayMode(this.currentMode, false);
    this.tooltips.bindTarget(document.getElementById('bar-batt-low-marker'));
    this.tooltips.bindTarget(document.getElementById('gauge-batt-low-marker'));
    this.tooltips.bindTarget(document.getElementById('subcard-runtime'));
  }

  /**
   * Switch between `'bars'` and `'gauge'` visualization styles.
   * @param {'bars'|'gauge'} mode
   * @param {boolean} [save=true]
   */
  setDisplayMode(mode, save = true) {
    this.currentMode = mode === 'gauge' ? 'gauge' : 'bars';
    if (save) {
      localStorage.setItem(TelemetryRenderer.VIEW_MODE_STORAGE_KEY, this.currentMode);
    }

    const isBars = this.currentMode === 'bars';

    const optBars = document.getElementById('opt-mode-bars');
    const optGauge = document.getElementById('opt-mode-gauge');
    if (optBars) optBars.classList.toggle('active', isBars);
    if (optGauge) optGauge.classList.toggle('active', !isBars);

    DomHelper.setStyle('power-view-bars', 'display', isBars ? 'flex' : 'none');
    DomHelper.setStyle('power-view-gauge', 'display', isBars ? 'none' : 'flex');
    DomHelper.setStyle('batt-view-bars', 'display', isBars ? 'flex' : 'none');
    DomHelper.setStyle('batt-view-gauge', 'display', isBars ? 'none' : 'flex');
  }

  /**
   * Split raw whitespace-delimited NUT status tokens into uppercase flags.
   * @param {string|undefined|null} statusRaw
   * @returns {string[]}
   */
  static parseStatusFlags(statusRaw) {
    if (!statusRaw) return [];
    return String(statusRaw).trim().toUpperCase().split(/\s+/);
  }

  /**
   * Determine whether the UPS is actively discharging its battery (`OB` or `DISCHRG`).
   * @param {string[]} flags
   * @returns {boolean}
   */
  static isDischarging(flags) {
    return flags.includes('OB') || flags.includes('DISCHRG');
  }

  /**
   * Re-render the most recent telemetry snapshot (e.g. after a language switch).
   */
  rerender() {
    if (this.lastData) {
      this.render(this.lastData);
    }
  }

  /**
   * Render a complete telemetry payload returned by `/api/stats`.
   * @param {Record<string, any>} data
   */
  render(data) {
    this.lastData = data;
    const isOnline = data.status === 'online';

    if (data.version) {
      DomHelper.setText('badge-version', `v${data.version}`);
    }

    const statusFlags = TelemetryRenderer.parseStatusFlags(data.ups_status_raw);
    const isBattery = statusFlags.includes('OB');
    const isDischarging = TelemetryRenderer.isDischarging(statusFlags);
    const upsKey = `${data.nut_host || ''}:${data.nut_port || ''}:${data.ups_name || ''}`;

    this.renderTargetFooter(data);

    if (!isOnline) {
      this.renderOfflineState(data, upsKey);
      return;
    }

    this.renderHeaderStatus(isBattery);
    this.renderPowerCard(data);
    this.renderBatteryCard(data, statusFlags, isDischarging);
    this.renderVoltageCard(data.voltage);
    this.renderPowerSourceCard(statusFlags, isBattery);

    // Client-side blackout elapsed timer (visible only while discharging)
    this.blackoutTracker.sync(true, isDischarging, upsKey);

    // Remaining runtime estimate minus NUT low-runtime threshold (visible only while discharging)
    this.renderRemainingRuntimeCard(data, isDischarging);

    // Synchronize read-only threshold fields in the Status tab of Settings
    this.syncStatusTabFields(data);

    // Update last refresh timestamp and Lock button visibility
    DomHelper.setText(
      'last-update-time',
      this.i18n.t('subbar.last_update', 'Last updated: ') + new Date().toLocaleTimeString()
    );
    if (data.auth_required) {
      DomHelper.setStyle('btn-lock', 'display', 'flex');
    }
  }

  /**
   * Render the NUT server host/port/ups footer label.
   * @param {Record<string, any>} data
   */
  renderTargetFooter(data) {
    if (data.nut_host && data.nut_port) {
      const upsSuffix = data.ups_name ? ` (${data.ups_name})` : '';
      DomHelper.setText(
        'info-target-server',
        `${this.i18n.t('subbar.target_nut', 'Target NUT')}: ${data.nut_host}:${data.nut_port}${upsSuffix}`
      );
    }
  }

  /**
   * Render disconnected/offline UI state and hide discharge-only widgets.
   * @param {Record<string, any>} data
   * @param {string} upsKey
   */
  renderOfflineState(data, upsKey) {
    DomHelper.setClass('conn-group', 'status-group offline');
    DomHelper.setClass('conn-dot', 'status-dot offline');
    DomHelper.setClass('conn-text', 'status-text offline');
    DomHelper.setText('conn-text', this.i18n.t('topbar.status_offline', 'Offline'));

    const errText = data.error_message
      ? this.i18n.t('subbar.error_prefix', 'Error: ') + data.error_message
      : this.i18n.t('subbar.nut_unreachable', 'NUT server unreachable');
    DomHelper.setText('last-update-time', errText);

    DomHelper.setText('subbox-voltage-val', '-- V');
    DomHelper.setClass('subbox-mode-container', 'subbox-badge offline');
    DomHelper.setText('subbox-mode-text', this.i18n.t('cards.feed_disconnected', 'Disconnected'));
    DomHelper.setClass('subbox-mode-dot', 'status-dot offline');

    this.renderShutdownMarker(false, null, false);
    this.blackoutTracker.sync(false, false, upsKey);

    const runtimeCard = document.getElementById('subcard-runtime');
    if (runtimeCard) {
      runtimeCard.classList.remove('visible');
      this.tooltips.setText(runtimeCard, '');
    }
  }

  /**
   * Update the top-bar online/on-battery status pill.
   * @param {boolean} isBattery
   */
  renderHeaderStatus(isBattery) {
    if (isBattery) {
      DomHelper.setClass('conn-group', 'status-group warning');
      DomHelper.setClass('conn-dot', 'status-dot warning');
      DomHelper.setClass('conn-text', 'status-text warning');
      DomHelper.setText('conn-text', this.i18n.t('topbar.status_battery', 'On Battery (OB)'));
    } else {
      DomHelper.setClass('conn-group', 'status-group');
      DomHelper.setClass('conn-dot', 'status-dot');
      DomHelper.setClass('conn-text', 'status-text');
      DomHelper.setText('conn-text', this.i18n.t('topbar.status_online', 'Online'));
    }
  }

  /**
   * Render active wattage (when supported) and UPS load percentage in both bar and gauge views.
   * @param {Record<string, any>} data
   */
  renderPowerCard(data) {
    const hasWatts = data.watts !== null && data.watts !== undefined;
    if (hasWatts) {
      DomHelper.setText('title-card-power', this.i18n.t('cards.power_title_watts', 'Power & Load'));
      DomHelper.setStyle('wrapper-watts-bars', 'display', 'block');
      DomHelper.setStyle('wrapper-watts-gauge', 'display', 'block');
      DomHelper.setStyle('power-view-gauge', 'justifyContent', 'space-between');
      DomHelper.setText('val-watts-bars', data.watts);
      DomHelper.setText('val-watts-gauge', data.watts);
    } else {
      DomHelper.setText('title-card-power', this.i18n.t('cards.power_title_load', 'UPS Load'));
      DomHelper.setStyle('wrapper-watts-bars', 'display', 'none');
      DomHelper.setStyle('wrapper-watts-gauge', 'display', 'none');
      DomHelper.setStyle('power-view-gauge', 'justifyContent', 'center');
    }

    const load = Math.min(100, Math.max(0, data.load || 0));
    DomHelper.setText('pct-load-bars', `${load}%`);
    DomHelper.setText('pct-load-gauge', `${load}%`);
    DomHelper.setStyle('bar-load-fill', 'width', `${load}%`);

    const arcLoad = document.getElementById('arc-load');
    if (arcLoad) {
      const offset = TelemetryRenderer.GAUGE_ARC_LENGTH * (1 - load / 100);
      arcLoad.style.strokeDashoffset = String(offset);
    }

    let labelText = this.i18n.t('cards.load_normal', 'Normal');
    let accentColor = '#38bdf8';
    let barBackground = 'linear-gradient(90deg, #0284c7, #38bdf8)';

    if (load > 85) {
      labelText = this.i18n.t('cards.load_overload', 'Overload');
      accentColor = '#ef4444';
      barBackground = '#ef4444';
    } else if (load > 60) {
      labelText = this.i18n.t('cards.load_high', 'High');
      accentColor = '#f59e0b';
      barBackground = '#f59e0b';
    }

    DomHelper.setText('label-load-status', labelText);
    DomHelper.setStyle('label-load-status', 'color', accentColor);
    DomHelper.setStyle('bar-load-fill', 'background', barBackground);
    DomHelper.setStyle('arc-load', 'stroke', accentColor);
  }

  /**
   * Render battery charge percentage and shutdown threshold indicator across both display modes.
   * @param {Record<string, any>} data
   * @param {string[]} statusFlags
   * @param {boolean} isDischarging
   */
  renderBatteryCard(data, statusFlags, isDischarging) {
    const battery = Math.min(100, Math.max(0, data.battery || 0));
    DomHelper.setText('val-batt-bars', battery);
    DomHelper.setText('val-batt-gauge', battery);
    DomHelper.setText('pct-batt-bars', `${battery}%`);
    DomHelper.setText('pct-batt-gauge', `${battery}%`);
    DomHelper.setStyle('bar-batt-fill', 'width', `${battery}%`);

    const arcBatt = document.getElementById('arc-batt');
    if (arcBatt) {
      const offset = TelemetryRenderer.GAUGE_ARC_LENGTH * (1 - battery / 100);
      arcBatt.style.strokeDashoffset = String(offset);
    }

    let labelText = this.i18n.t('cards.battery_charged', 'Charged');
    let accentColor = '#34d399';
    let barBackground = 'linear-gradient(90deg, #059669, #34d399)';

    if (battery <= 20) {
      labelText = this.i18n.t('cards.battery_critical', 'Critical');
      accentColor = '#ef4444';
      barBackground = '#ef4444';
    } else if (battery <= 50) {
      labelText = this.i18n.t('cards.battery_medium', 'Medium');
      accentColor = '#f59e0b';
      barBackground = '#f59e0b';
    }

    DomHelper.setText('label-batt-status', labelText);
    DomHelper.setStyle('label-batt-status', 'color', accentColor);
    DomHelper.setStyle('bar-batt-fill', 'background', barBackground);
    DomHelper.setStyle('arc-batt', 'stroke', accentColor);

    // Keep the red shutdown threshold tick permanently visible when off mains or below threshold;
    // otherwise reveal it on card hover/focus to keep normal operation uncluttered.
    const isOffMains = isDischarging || (statusFlags.length > 0 && !statusFlags.includes('OL'));
    const hasChargeLow =
      data.battery_charge_low !== null &&
      data.battery_charge_low !== undefined &&
      !Number.isNaN(Number(data.battery_charge_low));
    const isBelowThreshold =
      (hasChargeLow && battery <= Math.round(Number(data.battery_charge_low))) ||
      statusFlags.includes('LB');

    this.renderShutdownMarker(true, data.battery_charge_low, isOffMains || isBelowThreshold);
  }

  /**
   * Position and configure the red low-battery shutdown threshold marker in bar and SVG gauge views.
   * @param {boolean} isOnline
   * @param {number|null|undefined} chargeLow
   * @param {boolean} alwaysVisible
   */
  renderShutdownMarker(isOnline, chargeLow, alwaysVisible) {
    const barMarker = document.getElementById('bar-batt-low-marker');
    const gaugeMarker = document.getElementById('gauge-batt-low-marker');
    const gaugeLine = document.getElementById('gauge-batt-low-line');
    const gaugeHit = document.getElementById('gauge-batt-low-hit');

    const hasLow =
      isOnline && chargeLow !== null && chargeLow !== undefined && !Number.isNaN(Number(chargeLow));

    if (!hasLow) {
      if (barMarker) {
        barMarker.classList.remove('always-visible');
        DomHelper.setStyle(barMarker, 'display', 'none');
        this.tooltips.setText(barMarker, '');
      }
      if (gaugeMarker) {
        gaugeMarker.classList.remove('always-visible');
        DomHelper.setStyle(gaugeMarker, 'display', 'none');
        this.tooltips.setText(gaugeMarker, '');
      }
      return;
    }

    const pct = Math.min(100, Math.max(0, Math.round(Number(chargeLow))));
    const tipText = this.i18n
      .t('cards.shutdown_threshold_tooltip', 'Shutdown threshold for all machines ({pct}%)')
      .replace('{pct}', String(pct));

    if (barMarker) {
      barMarker.classList.toggle('always-visible', Boolean(alwaysVisible));
      DomHelper.setStyle(barMarker, 'left', `${pct}%`);
      DomHelper.setStyle(barMarker, 'display', 'flex');
      this.tooltips.setText(barMarker, tipText);
    }

    if (gaugeMarker && gaugeLine && gaugeHit) {
      // Map percentage [0..100] along the upper semicircle centered at (50, 55), radius 35.
      const theta = Math.PI * (1 - pct / 100);
      const cosT = Math.cos(theta);
      const sinT = Math.sin(theta);

      gaugeLine.setAttribute('x1', (50 + 31 * cosT).toFixed(2));
      gaugeLine.setAttribute('y1', (55 - 31 * sinT).toFixed(2));
      gaugeLine.setAttribute('x2', (50 + 39 * cosT).toFixed(2));
      gaugeLine.setAttribute('y2', (55 - 39 * sinT).toFixed(2));

      gaugeHit.setAttribute('x1', (50 + 28 * cosT).toFixed(2));
      gaugeHit.setAttribute('y1', (55 - 28 * sinT).toFixed(2));
      gaugeHit.setAttribute('x2', (50 + 42 * cosT).toFixed(2));
      gaugeHit.setAttribute('y2', (55 - 42 * sinT).toFixed(2));

      gaugeMarker.classList.toggle('always-visible', Boolean(alwaysVisible));
      DomHelper.setStyle(gaugeMarker, 'display', 'inline');
      this.tooltips.setText(gaugeMarker, tipText);
    }
  }

  /**
   * Render mains/output voltage in the voltage secondary card.
   * @param {number|null|undefined} voltage
   */
  renderVoltageCard(voltage) {
    if (voltage !== null && voltage !== undefined) {
      const value = Number(voltage);
      const formatted = value % 1 === 0 ? Math.round(value) : value.toFixed(1);
      DomHelper.setText('subbox-voltage-val', `${formatted} V`);
    } else {
      DomHelper.setText('subbox-voltage-val', '-- V');
    }
  }

  /**
   * Render active power feed source (Utility Power / Battery / Bypass).
   * @param {string[]} statusFlags
   * @param {boolean} isBattery
   */
  renderPowerSourceCard(statusFlags, isBattery) {
    if (isBattery) {
      DomHelper.setClass('subbox-mode-container', 'subbox-badge battery');
      DomHelper.setText('subbox-mode-text', this.i18n.t('cards.feed_battery', 'Battery'));
      DomHelper.setClass('subbox-mode-dot', 'status-dot warning');
    } else if (statusFlags.includes('BYPASS')) {
      DomHelper.setClass('subbox-mode-container', 'subbox-badge warning');
      DomHelper.setText('subbox-mode-text', this.i18n.t('cards.feed_bypass', 'Bypass'));
      DomHelper.setClass('subbox-mode-dot', 'status-dot warning');
    } else {
      DomHelper.setClass('subbox-mode-container', 'subbox-badge online');
      DomHelper.setText('subbox-mode-text', this.i18n.t('cards.feed_online', 'Utility Power'));
      DomHelper.setClass('subbox-mode-dot', 'status-dot');
    }
  }

  /**
   * Render estimated usable remaining runtime (`battery.runtime - battery.runtime.low`) while discharging.
   * @param {Record<string, any>} data
   * @param {boolean} isDischarging
   */
  renderRemainingRuntimeCard(data, isDischarging) {
    const runtimeCard = document.getElementById('subcard-runtime');
    const runtimeValEl = document.getElementById('subbox-runtime-val');
    if (!runtimeCard || !runtimeValEl) return;

    if (!isDischarging) {
      runtimeCard.classList.remove('visible');
      this.tooltips.setText(runtimeCard, '');
      return;
    }

    runtimeCard.classList.add('visible');
    const hasRuntime =
      data.battery_runtime !== null &&
      data.battery_runtime !== undefined &&
      !Number.isNaN(Number(data.battery_runtime));
    const hasLowRuntime =
      data.battery_runtime_low !== null &&
      data.battery_runtime_low !== undefined &&
      !Number.isNaN(Number(data.battery_runtime_low));

    if (!hasRuntime) {
      DomHelper.setText(runtimeValEl, '--');
      DomHelper.setClass(runtimeValEl, 'subbox-badge runtime');
      this.tooltips.setText(runtimeCard, '');
      return;
    }

    const totalSec = Math.max(0, Math.round(Number(data.battery_runtime)));
    const lowSec = hasLowRuntime ? Math.max(0, Math.round(Number(data.battery_runtime_low))) : 0;
    const usableSec = Math.max(0, totalSec - lowSec);

    DomHelper.setText(runtimeValEl, DurationFormatter.formatHuman(usableSec));
    DomHelper.setClass(
      runtimeValEl,
      usableSec === 0 ? 'subbox-badge runtime critical' : 'subbox-badge runtime'
    );

    const tooltip = hasLowRuntime
      ? this.i18n
          .t(
            'cards.remaining_time_tooltip',
            'Calculated from UPS estimated runtime ({ups_rt}) minus the low runtime threshold ({low_rt}). This duration is indicative: the system may shut down earlier if the battery drops below the configured low-charge percentage.'
          )
          .replace('{ups_rt}', DurationFormatter.formatHuman(totalSec))
          .replace('{low_rt}', DurationFormatter.formatHuman(lowSec))
      : this.i18n
          .t(
            'cards.remaining_time_tooltip_no_low',
            'UPS estimated runtime ({ups_rt}) — no low runtime threshold configured. This duration is indicative: the system may shut down earlier if the battery drops below the configured low-charge percentage.'
          )
          .replace('{ups_rt}', DurationFormatter.formatHuman(totalSec));

    this.tooltips.setText(runtimeCard, tooltip);
  }

  /**
   * Keep read-only operational fields in the Settings Status tab up to date.
   * @param {Record<string, any>} data
   */
  syncStatusTabFields(data) {
    if (data.nominal_watts) {
      DomHelper.setText('stat-val-maxwatts', `${data.nominal_watts} W`);
    }
    if (data.battery_charge_low !== null && data.battery_charge_low !== undefined) {
      DomHelper.setText('stat-val-charge-low', `${Math.round(Number(data.battery_charge_low))}%`);
    }
    if (data.battery_runtime_low !== null && data.battery_runtime_low !== undefined) {
      DomHelper.setText(
        'stat-val-runtime-low',
        DurationFormatter.formatThreshold(Number(data.battery_runtime_low))
      );
    }
  }
}
