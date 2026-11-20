import { DomHelper } from './dom.js';

/**
 * Utility formatters for blackout elapsed timers, estimated battery runtime, and shutdown thresholds.
 */
export class DurationFormatter {
  /**
   * Format an elapsed duration as `MM:SS` or `H:MM:SS`.
   * @param {number} totalSeconds
   * @returns {string}
   */
  static formatClock(totalSeconds) {
    const sec = Math.max(0, Math.floor(totalSeconds));
    const hours = Math.floor(sec / 3600);
    const minutes = Math.floor((sec % 3600) / 60);
    const seconds = sec % 60;
    const mm = String(minutes).padStart(2, '0');
    const ss = String(seconds).padStart(2, '0');
    return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`;
  }

  /**
   * Format a duration into a compact human-readable label (e.g. `45s`, `12m 30s`, `1h 05m`).
   * @param {number} totalSeconds
   * @returns {string}
   */
  static formatHuman(totalSeconds) {
    const sec = Math.max(0, Math.round(totalSeconds));
    if (sec < 60) return `${sec}s`;

    const hours = Math.floor(sec / 3600);
    const minutes = Math.floor((sec % 3600) / 60);
    const seconds = sec % 60;
    if (hours > 0) {
      return minutes > 0 ? `${hours}h ${String(minutes).padStart(2, '0')}m` : `${hours}h`;
    }
    return seconds > 0 ? `${minutes}m ${String(seconds).padStart(2, '0')}s` : `${minutes} min`;
  }

  /**
   * Format a NUT low-runtime threshold showing both human units and raw seconds.
   * @param {number} totalSeconds
   * @returns {string}
   */
  static formatThreshold(totalSeconds) {
    const sec = Math.max(0, Math.round(totalSeconds));
    if (sec < 60) return `${sec}s`;
    if (sec % 60 === 0) {
      return `${sec / 60} min (${sec}s)`;
    }
    return `${DurationFormatter.formatHuman(sec)} (${sec}s)`;
  }
}

/**
 * Client-side live blackout duration counter.
 *
 * Runs strictly in the browser (never preventing backend NUT standby) and persists
 * the blackout start timestamp in `sessionStorage` so page reloads preserve continuity.
 */
export class BlackoutTracker {
  static STORAGE_KEY = 'ups_blackout_state_v1';
  static MAX_RESUME_GAP_MS = 120_000;

  constructor() {
    this.startedAtMs = null;
    this.timerId = null;
  }

  /**
   * Synchronize tracker state with the latest UPS online and discharge status.
   * @param {boolean} isOnline
   * @param {boolean} isDischarging
   * @param {string} upsKey - Unique target identifier (`host:port:ups`).
   */
  sync(isOnline, isDischarging, upsKey) {
    const card = document.getElementById('subcard-blackout');

    if (!isOnline) {
      this.pause();
      if (card) card.classList.remove('visible');
      return;
    }

    if (!isDischarging) {
      this.reset();
      if (card) card.classList.remove('visible');
      return;
    }

    const now = Date.now();
    if (this.startedAtMs === null) {
      const restored = this.restoreStartTimestamp(upsKey, now);
      this.startedAtMs = restored !== null ? restored : now;
    }

    this.persistState(upsKey, now);

    if (card) card.classList.add('visible');
    this.render();
    if (!this.timerId && !document.hidden) {
      this.timerId = setInterval(() => this.render(), 1000);
    }
  }

  /**
   * Pause the 1-second UI tick (e.g. when the browser tab becomes hidden).
   */
  pause() {
    if (this.timerId) {
      clearInterval(this.timerId);
      this.timerId = null;
    }
  }

  /**
   * Resume the 1-second UI tick if a blackout is currently being tracked.
   */
  resume() {
    if (this.startedAtMs !== null && !this.timerId) {
      this.render();
      this.timerId = setInterval(() => this.render(), 1000);
    }
  }

  /**
   * Clear tracked blackout state and remove persisted session data.
   */
  reset() {
    this.startedAtMs = null;
    this.pause();
    try {
      sessionStorage.removeItem(BlackoutTracker.STORAGE_KEY);
    } catch {
      // Ignore storage restrictions in private browsing modes.
    }
  }

  /**
   * Render the elapsed blackout time into the blackout card badge.
   */
  render() {
    if (this.startedAtMs === null) return;
    const elapsedSeconds = (Date.now() - this.startedAtMs) / 1000;
    DomHelper.setText('subbox-blackout-val', DurationFormatter.formatClock(elapsedSeconds));
  }

  /**
   * Restore a recent blackout start timestamp from sessionStorage if it matches the same UPS.
   * @param {string} upsKey
   * @param {number} nowMs
   * @returns {number|null}
   */
  restoreStartTimestamp(upsKey, nowMs) {
    try {
      const raw = sessionStorage.getItem(BlackoutTracker.STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (
        parsed &&
        parsed.upsKey === upsKey &&
        typeof parsed.startedAt === 'number' &&
        typeof parsed.lastSeen === 'number' &&
        nowMs - parsed.lastSeen < BlackoutTracker.MAX_RESUME_GAP_MS
      ) {
        return parsed.startedAt;
      }
    } catch {
      // Ignore corrupted or unavailable sessionStorage entries.
    }
    return null;
  }

  /**
   * Persist current blackout metadata to sessionStorage.
   * @param {string} upsKey
   * @param {number} nowMs
   */
  persistState(upsKey, nowMs) {
    try {
      sessionStorage.setItem(
        BlackoutTracker.STORAGE_KEY,
        JSON.stringify({ upsKey, startedAt: this.startedAtMs, lastSeen: nowMs })
      );
    } catch {
      // Ignore storage quota or privacy-mode errors.
    }
  }
}
