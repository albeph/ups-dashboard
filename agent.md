# Agent Guidelines — UPS Web Dashboard

This file summarizes the architecture, constraints, and checklists any AI agent should follow when working on `ups-dashboard`.

## 1. Project Overview & Core Constraints

`ups-dashboard` is an ultra-lightweight, zero-dependency web dashboard + PWA for monitoring UPS devices managed by **Network UPS Tools (NUT)**.

Non-negotiable design constraints:
- **Zero Python external dependencies**: backend must use Python standard library only (`python:3.12-alpine`, target memory footprint < 15 MB). Do not add `pip` packages.
- **Zero frontend frameworks or external CDNs**: frontend is modular vanilla HTML/CSS/ES6 JS under `image/static/` and must work in isolated/air-gapped LANs with no build step.
- **English-only source code & comments**: all code comments, docstrings, log messages, and backend defaults must be written in English.
- **Vendor-neutral codebase**: never hardcode personal hardware brands, personal IPs, or personal credentials in source files, tests, or documentation.
- **Preserve standby / idle polling suspension**: `NutPoller` + `ActivityTracker` (`image/dashboard/collector.py`) suspend NUT polling automatically when no browser clients are active (and the browser pauses polling when `document.hidden` is true).
  - **Never** add continuous backend loops, background state trackers, or server-side timers that prevent standby or bloat the image.
  - Derived UI timers and view-only state (e.g. live blackout duration counter) belong **strictly on the client (browser)** and must pause when `document.hidden` is true.

## 2. Repository Layout

- `docs/ARCHITECTURE.md` — Dedicated technical architecture guide.
- `README.md` — User-focused project overview, features, and usage guide.
- `image/app.py` — Entrypoint starting `DashboardApplication` via `run_server()`.
- `image/VERSION` — Canonical application version string (SemVer).
- `image/Dockerfile` — Multi-arch Alpine image running as non-root `appuser` (UID `1000`).
- `image/dashboard/`
  - `constants.py` — Defaults, `resolve_data_dir()`, and `get_app_version()`.
  - `nut.py` — `NutClient`, `NutProtocolParser`, `NutMetrics`, `NutProtocolError`.
  - `collector.py` — `NUTDataCache`, `ActivityTracker` (standby/wake), `NutPoller`.
  - `config.py` — `ConfigManager` (persistent `data/config.json`, env defaults, legacy migration, `0600` permissions).
  - `security.py` — `KeyManager`, `PasswordHasher` (PBKDF2-HMAC-SHA256), `SecretCipher` (CTR + HMAC-SHA256), `SessionManager`.
  - `router.py` — `Response`, `StaticFileServer`, `LocaleRegistry`, `SettingsValidator`, `Router`.
  - `server.py` — `DashboardHTTPServer`, `DashboardHandler`, `DashboardApplication`, `build_app()`, `run_server()`.
- `image/static/`
  - `index.html` — Semantic HTML5 shell (no inline CSS or JS).
  - `css/styles.css` — Vanilla CSS stylesheet.
  - `js/` — Modular vanilla ES6 classes (`app.js`, `api.js`, `auth.js`, `blackout.js`, `dom.js`, `i18n.js`, `pwa.js`, `settings.js`, `telemetry.js`, `tooltip.js`).
  - `sw.js` — Service Worker (`CACHE_NAME` dynamically receives `image/VERSION` from `StaticFileServer`).
  - `manifest.json`, icons — PWA assets.
  - `locales/en.json`, `locales/it.json`, `locales/README.md` — Auto-discovered localization files (`en` is fallback).
- `tests/` — Standard library `unittest` suite (`test_nut.py`, `test_collector.py`, `test_config.py`, `test_security.py`, `test_api.py`).
- `data/` — Runtime persistent files (`config.json`, `.secret_key`, `.env`, `.env.example`). Treat runtime files as sensitive user data.

## 3. NUT Telemetry Rules

- Query all required NUT variables over the **same TCP socket connection** inside `NutClient.fetch_metrics()`, then send `LOGOUT`.
- Always handle unsupported/missing NUT variables gracefully: parse to `None` on the backend and render `--` or hide optional indicators in the UI.
- Detect UPS status flags by splitting `ups_status_raw` on whitespace (`OL`, `OB`, `LB`, `CHRG`, `DISCHRG`, `BYPASS`, etc.), not loose substring checks.

## 4. Frontend & UX Conventions

- **Dual display modes**: The dashboard supports both **Horizontal Bars** (`#*-view-bars`) and **Semicircle SVG Gauge** (`#*-view-gauge`). Any visual addition to Load or Battery metrics must work in **both** modes.
- **Selection-safe updates**: Always use `DomHelper.setText`, `DomHelper.setClass`, and `DomHelper.setStyle` inside `TelemetryRenderer` so periodic polling does not clear active user text selection.
- **Desktop + Mobile tooltips**: `.dashboard-panel` uses `overflow: hidden`. Always use `TooltipManager` (`#ui-tooltip`), which clamps to viewport bounds and supports hover, touch tap, and keyboard focus.
- **Internationalization (i18n)**:
  - Every visible string or tooltip must have keys in both `image/static/locales/en.json` and `image/static/locales/it.json`, plus an updated schema entry in `image/static/locales/README.md` and English fallback text in HTML/JS.
  - Keep placeholder tokens (`{pct}`, `{ups_rt}`, `{low_rt}`, `{load}`, `{batt}`) identical across all locale files.

## 5. Security & Secrets

- **Never** log, print, hardcode, or commit secrets from `data/config.json`, `data/.secret_key`, or `data/.env`.
- Maintain strict permissions (`0600`) on config/key files, constant-time secret comparison, CRLF stripping on NUT/config inputs, `HttpOnly`/`SameSite=Lax` cookies, and HTTP security headers in `server.py`.

## 6. Release & Version Bump Checklist

`image/VERSION` is the **single source of truth** for the application version:
- Never hardcode version numbers in `constants.py`, `sw.js`, or `index.html`.
- When releasing a new version, update **only** `image/VERSION`. `StaticFileServer` automatically injects it into `/`, `/sw.js`, `/api/version`, and `/api/stats`.

## 7. Verification Commands

Run the full test suite before finishing any change:
```bash
python3 -m unittest discover -s tests -v
```

Validate locale JSON syntax:
```bash
python3 -c 'import json; [json.load(open(p, encoding="utf-8")) for p in ("image/static/locales/en.json", "image/static/locales/it.json")]'
```
