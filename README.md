# UPS Web Dashboard ⚡

A lightweight, responsive web dashboard and Progressive Web App (PWA) for monitoring Uninterruptible Power Supplies (UPS) managed by **Network UPS Tools (NUT)**.

Built with **zero external dependencies** on both the backend and frontend, it runs cleanly on low-power single-board computers, NAS devices, and full servers with a minimal memory footprint (< 15 MB RAM) and full support for isolated/air-gapped LANs.

---

## Features

- **Real-Time Telemetry**:
  - **Active Power (Watts)** and **UPS Load (%)** with automatic wattage estimation when only nominal power is exposed by the UPS.
  - **Battery Charge (%)** with visual shutdown-threshold marker (`battery.charge.low`).
  - **Mains Voltage (V)** and **Power Source** indicator (Utility Power, On Battery, Bypass).
  - **Outage Insights**: When on battery power, displays a live **Blackout Duration** counter and **Remaining Time** (UPS estimated runtime minus configured low-runtime threshold).
- **Dual Visualization Modes**:
  - **Horizontal Bars**: Clean linear progress bars with dynamic severity colors.
  - **Semicircle Gauge**: Animated SVG arc dials inspired by analog meters.
  - Switchable at any time from the Settings modal and remembered per browser.
- **In-App Configuration**:
  - Update NUT host, port, UPS identifier, optional NUT credentials, polling interval, display mode, language, and dashboard password directly from the Web UI.
- **Optional Password Protection**:
  - Protect access with a password lock screen or leave open for direct LAN viewing.
- **Installable PWA & Mobile Friendly**:
  - Responsive layout for desktop and mobile devices, installable as a standalone web app on iOS, Android, and desktop browsers.
- **Multi-Language Support (i18n)**:
  - Automatic browser language detection with built-in English and Italian translations, plus auto-discovery for community translation files.
- **Demand-Driven Standby**:
  - Automatically suspends NUT polling when no browser tabs are open or visible, and resumes immediately on demand.

---

## Quick Start (Docker Compose)

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/ups-dashboard.git
cd ups-dashboard
```

### 2. Configure environment variables

Copy the example configuration file if `data/.env` does not exist yet:

```bash
cp data/.env.example data/.env
```

Edit `data/.env` to match your NUT server:

```env
NUT_HOST=192.168.1.50     # Hostname or IP of your NUT server
NUT_PORT=3493             # Standard NUT TCP port
UPS_NAME=ups              # UPS name configured in NUT's ups.conf
PORT=8080                 # Host port exposed by the dashboard
POLL_INTERVAL=2.0         # Refresh interval in seconds

# Optional dashboard password (leave unset for open access)
# DASHBOARD_PASSWORD=change_me
```

### 3. Start the container

```bash
docker compose up -d --build
```

Open your browser at:

```text
http://<HOST_IP>:8080
```

---

## Configuration Reference

Settings can be provided through environment variables in `data/.env` or updated live from **Settings → NUT Server** / **Security** in the web interface. Changes saved from the UI are persisted in `data/config.json`.

| Variable | Default | Description |
| :--- | :--- | :--- |
| `NUT_HOST` | `127.0.0.1` | Hostname or IP address of the NUT `upsd` daemon. |
| `NUT_PORT` | `3493` | TCP port of the NUT `upsd` daemon. |
| `UPS_NAME` | `ups` | UPS identifier configured in NUT's `ups.conf`. |
| `NUT_USER` | *(empty)* | Optional username for authenticated NUT connections. |
| `NUT_PASSWORD` | *(empty)* | Optional password for authenticated NUT connections. |
| `NUT_PASSWORD_FILE` | *(empty)* | Optional path to a file containing the NUT password (useful with Docker secrets). |
| `PORT` | `8080` | TCP port where the dashboard HTTP server listens. |
| `POLL_INTERVAL` | `2.0` | Polling interval in seconds (minimum `0.5`). |
| `DASHBOARD_PASSWORD` | *(empty)* | Optional password to protect web access (accepts plaintext or pre-computed `pbkdf2:sha256:...` hash). |

---

## Running Locally (Without Docker)

Requires **Python 3.10+** (standard library only — no `pip install` needed):

```bash
NUT_HOST=127.0.0.1 UPS_NAME=ups python3 image/app.py
```

Then open `http://localhost:8080`.

---

## Adding Translations

Localization files live in `image/static/locales/` and are automatically discovered at startup. See the [Localization Guide](image/static/locales/README.md) to contribute a new language.

---

## Architecture & Development

For a full technical overview — including system architecture, OOP design, standby/wake lifecycle, NUT protocol handling, security model, and REST API specification — see the dedicated [Architecture Guide](docs/ARCHITECTURE.md).

Run the test suite with:

```bash
python3 -m unittest discover -s tests -v
```

---

## License

Released under the [MIT License](LICENSE).
