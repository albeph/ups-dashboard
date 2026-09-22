# UPS Web Dashboard ⚡

Una dashboard web ultra-leggera, moderna e reattiva per il monitoraggio in tempo reale dei gruppi di continuità (UPS) gestiti tramite **Network UPS Tools (NUT)**.

Progettata con un'architettura **zero-dipendenze**, offre un'impronta di memoria ridottissima (< 15 MB di RAM) ed è pronta per essere eseguita via **Docker** su qualsiasi piattaforma (PC, server, NAS o single-board computer a basso consumo come Raspberry Pi).

---

## ✨ Funzionalità

- **Visualizzazione Istantanea**:
  - **Potenza Attiva (Watt)** e **Carico (%)**
  - **Stato Carica Batteria (%)**
- **Doppia Modalità Grafica (Intercambiabile)**:
  - **Barre di Avanzamento**: barre lineari con gradiente cromatico e percentuale affiancata.
  - **Semicerchio (Gauge SVG)**: indicatore ad arco posizionato alla destra del valore, animato in SVG vettoriale.
  - La preferenza selezionata viene memorizzata automaticamente nel browser (`localStorage`).
- **Autenticazione con Password Opzionale**:
  - Accesso protetto con cookie di sessione crittografici sicuri.
  - Se disabilitata, la dashboard è ad accesso diretto.
- **Ultra-Leggera e Veloce**:
  - Server HTTP e client TCP nativi in Python standard library (nessuna libreria `pip` esterna da compilare o installare).
  - Frontend HTML5 / CSS3 / JavaScript vanilla: nessun framework pesante, zero chiamate a CDN esterni, funzionamento garantito anche in reti LAN isolate/air-gapped.
- **Multi-Architettura**:
  - Compatibile nativamente con `linux/amd64`, `linux/arm64` e `linux/arm/v7`.

---

## 🚀 Avvio Rapido con Docker

### 1. Clona il repository o copia la cartella
```bash
git clone https://github.com/tuo-utente/ups-dashboard.git
cd ups-dashboard
```

### 2. Configura le variabili d'ambiente
Copia il file di esempio `.env.example` in `.env`:
```bash
cp .env.example .env
```

Modifica `.env` con i parametri del tuo server NUT:
```env
NUT_HOST=192.168.1.50     # Indirizzo IP del server NUT
NUT_PORT=3493             # Porta standard NUT
UPS_NAME=ups              # Nome dell'UPS in ups.conf
UPS_NOMINAL_WATTS=500     # Potenza nominale in Watt (se non riportata via realpower)
PORT=8080                 # Porta esposta della dashboard
POLL_INTERVAL=2.0         # Frequenza di aggiornamento (secondi)

# Password opzionale (lascia vuoto per accesso libero)
DASHBOARD_PASSWORD=tua_password_sicura
```

### 3. Avvia il container
```bash
docker compose up -d
```

Apri il browser su:
```
http://<INDIRIZZO_IP_DEL_HOST>:8080
```

---

## ⚙️ Variabili di Configurazione

| Variabile | Default | Descrizione |
| :--- | :--- | :--- |
| `NUT_HOST` | `127.0.0.1` | Hostname o indirizzo IP dove risiede il demone NUT `upsd`. |
| `NUT_PORT` | `3493` | Porta TCP di ascolto del demone NUT. |
| `UPS_NAME` | `ups` | Identificativo dell'UPS configurato nel server NUT. |
| `UPS_NOMINAL_WATTS` | `500` | Potenza nominale in Watt, usata per il calcolo della potenza reale nel caso in cui l'UPS non fornisca il campo `ups.realpower`. |
| `PORT` | `8080` | Porta TCP su cui il container accetta connessioni web HTTP. |
| `POLL_INTERVAL` | `2.0` | Secondi di intervallo tra le letture in background via socket TCP da NUT. |
| `DASHBOARD_PASSWORD` | *(vuoto)* | Password di accesso. Se non impostata, l'accesso alla dashboard è pubblico. |

---

## 🛠️ Struttura del Progetto

```
ups-dashboard/
├── Dockerfile              # Immagine Alpine multi-arch ultra-leggera
├── docker-compose.yml      # Configurazione Docker Compose
├── app.py                  # Server HTTP e client TCP NUT (Python standard library)
├── static/
│   └── index.html          # Interfaccia grafica completa (HTML + CSS + SVG + JS vanilla)
├── .env.example            # Template di configurazione
├── .gitignore              # Esclusione credenziali e file temporanei
└── README.md               # Documentazione
```

---

## 🔒 Sicurezza

- Il container viene eseguito con un utente di sistema non-root (`appuser`).
- Il confronto delle password usa algoritmi `constant-time` (`secrets.compare_digest`) per prevenire attacchi di tipo timing.
- I cookie di sessione sono configurati con flag `HttpOnly` e `SameSite=Lax`.

---

## 📄 Licenza

Rilasciato sotto licenza MIT. Libero per uso personale e commerciale.
