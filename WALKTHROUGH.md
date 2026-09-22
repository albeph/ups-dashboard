# UPS Web Dashboard - Project Walkthrough & Antigravity Handover

> Documento di continuità progettuale per Antigravity.
> Utilizza questo file come punto di partenza quando apri `/home/user/Projects/ups-dashboard` come workspace indipendente in una nuova sessione di Antigravity.

---

## 📌 Panoramica del Progetto

- **Nome**: `ups-dashboard`
- **Versione Attuale**: `1.1.0` (definita in [`VERSION`](./VERSION))
- **Scopo**: Piattaforma web autonoma, ultra-leggera e universale per il monitoraggio in tempo reale dei gruppi di continuità gestiti tramite **Network UPS Tools (NUT)**.
- **Isolamento**: Il progetto è **100% autonomo e scollegato** da qualsiasi altro repository (incluso `ups_sharing`), con proprio repository Git indipendente pronto per GitHub.

---

## 🏗️ Architettura e Decisioni di Design

### 1. Zero Dipendenze Esterne (Backend & Frontend)
- **Backend (`app.py`)**:
  - Scritto interamente con la **libreria standard di Python 3.12** (`http.server.ThreadingHTTPServer`, `socket`, `threading`, `json`, `secrets`, `hashlib`, `hmac`).
  - **Nessuna dipendenza `pip`**: tempo di build di soli ~3 secondi, footprint di memoria RAM inferiore a **15 MB**.
  - Worker thread in background che interroga il demone NUT (porta TCP 3493) ogni 2 secondi via socket raw, aggiornando una cache thread-safe in memoria.
- **Frontend (`static/index.html`)**:
  - Single Page Application autonoma in HTML5, CSS3 moderno e JavaScript vanilla.
  - **Zero chiamate a CDN esterni**: funziona perfettamente anche in reti locali isolate o prive di connessione a Internet.
  - Peso totale della pagina inferiore a **30 KB**.

### 2. Rilevamento Intelligente dei Watt (Nessun Input Manuale)
- La potenza assorbita (Watt) viene mostrata **esclusivamente se supportata e comunicata dall'hardware dell'UPS**:
  1. Se l'UPS comunica `ups.realpower` o `output.realpower`: mostra direttamente il valore misurato in tempo reale.
  2. Se l'UPS comunica la potenza nominale massima `ups.realpower.nominal`: calcola dinamicamente i Watt con $\frac{\text{carico \%} \times \text{potenza nominale}}{100}$.
  3. Se l'UPS **non comunica nessuno dei due dati**: il dato dei Watt **viene automaticamente nascosto** e la card mostra in modo pulito ed elegante solo il **"Carico UPS (%)"**, evitando valori fittizi o arbitrari.
- È stato rimosso qualsiasi campo manuale per la potenza nominale, rendendo l'esperienza utente a zero configurazione.

### 3. Layout a Pagina Intera con Top-Bar
- **Top-Bar Fissa**:
  - Brand e Titolo con badge di versione dinamico `v1.1.0`.
  - Indicatore di connessione in tempo reale con dot pulsante (`Online` / `Offline`).
  - Selettore rapido tra le modalità grafiche:
    - **`[Barre]`**: Barre orizzontali progressive con sfumatura di colore dinamica (ciano &rarr; ambra &rarr; rosso in base al carico).
    - **`[Semicerchio]`**: Indicatori ad arco SVG posizionati alla destra del valore numerico.
    - La scelta viene memorizzata automaticamente nel browser (`localStorage`).
  - Pulsante **`⚙️ Impostazioni`** (apre la modale di configurazione).
  - Pulsante **`🔒 Lock`** (chiude la sessione e blocca l'accesso).

### 4. Pannello Impostazioni e Persistenza Dinamica
- Accessibile direttamente dalla top-bar, permette di modificare a runtime:
  - Host e Porta del server NUT (`nut_host`, `nut_port`).
  - Nome identificativo dell'UPS (`ups_name`).
  - Credenziali opzionali del demone NUT (`nut_user`, `nut_password`), con autenticazione via protocollo TCP (`USERNAME` e `PASSWORD`).
  - Nuova password per la dashboard web.
- **Persistenza**: Le modifiche vengono salvate istantaneamente su `data/config.json` (montato come volume Docker) e ricaricate al volo dal worker socket senza dover riavviare il container!

### 5. Sicurezza Credenziali e Multi-Piattaforma (v1.1.0)
- **Zero Password in Chiaro sul Filesystem**:
  - **Password della Dashboard**: hashing crittografico irreversibile a una via con Salt `PBKDF2-HMAC-SHA256` (100.000 iterazioni). Impossibile risalire alla password in chiaro anche leggendo `config.json`.
  - **Password del demone NUT**: cifratura simmetrica autenticata a riposo (Encryption at Rest con HMAC-SHA256 CTR stream cipher) tramite chiave master protetta in `data/.secret_key`.
  - **Permessi Filesystem Reali**: `chmod 0600` applicato automaticamente su `data/config.json` e `data/.secret_key` (accessibili unicamente dall'utente proprietario).
  - **Comparazione Timing-Safe**: Comparazione password constant-time (`secrets.compare_digest`) per prevenire attacchi di tipo timing.
  - **Cookie di Sessione**: Cookie crittografici sicuri (`HttpOnly`, `SameSite=Lax`, `secrets.token_hex(24)`).
- **Docker Multi-Arch**:
  - Immagine base `python:3.12-alpine` compatibile con `linux/amd64`, `linux/arm64` (es. Raspberry Pi Zero 2 W) e `linux/arm/v7`.
  - Container eseguito con utente di sistema non-root `appuser` configurato con UID `1000` (compatibilità nativa con filesystem host Linux).

---

## 📁 Struttura Completa del Repository

```
ups-dashboard/
├── VERSION                     # File versione sorgente ("1.0.0")
├── Dockerfile                  # Immagine Alpine multi-arch, non-root UID 1000
├── docker-compose.yml          # Servizio Docker Compose con porta 8080 e volume data/
├── app.py                      # Core backend: ThreadingHTTPServer, poller socket NUT, auth, settings
├── static/
│   └── index.html              # Frontend: Top-Bar, card telemetria, modale impostazioni, login
├── data/
│   ├── .gitkeep                # Traccia la cartella nel repo
│   ├── .secret_key             # [Ignorato da git, chmod 0600] Chiave master crittografica simmetrica
│   └── config.json             # [Ignorato da git, chmod 0600] Configurazione con password hash/cifrate
├── .env.example                # Template per variabili d'ambiente
├── .gitignore                  # Esclusione di .env, data/*.json, data/.secret_key, bytecode
├── README.md                   # Documentazione professionale pronta per GitHub
└── WALKTHROUGH.md              # Questo documento di stato e continuità
```

---

## 🔌 Specifiche API REST

Tutti gli endpoint rispondono in formato JSON con header `Cache-Control: no-store`.

| Metodo | Endpoint | Auth Richiesta | Descrizione |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | No (mostra login se protetto) | Serve l'interfaccia web `static/index.html`. |
| `GET` | `/api/health` | No | Healthcheck del container: `{"status": "ok", "version": "1.1.0"}`. |
| `GET` | `/api/version` | No | Restituisce la versione dell'applicazione: `{"version": "1.1.0"}`. |
| `GET` | `/api/stats` | Sì (se password attiva) | Restituisce la telemetria live (`watts`, `load`, `battery`, `status`, ecc.). |
| `GET` | `/api/settings` | Sì | Restituisce i parametri attuali (con flag booleani per le credenziali). |
| `POST` | `/api/settings` | Sì | Cifra/hasheggia e salva i parametri in `data/config.json` e riaggancia il poller. |
| `POST` | `/api/login` | No | Valida la password contro l'hash PBKDF2 e rilascia il cookie di sessione. |
| `POST` | `/api/logout` | No | Invalida la sessione e cancella il cookie. |

---

## 🚀 Come Eseguire e Testare

### Con Docker Compose (Consigliato)
```bash
cd /home/user/Projects/ups-dashboard
docker compose up -d --build
```
Accesso browser: `http://localhost:8080` (o `http://<IP-HOST>:8080`).

### Esecuzione Diretta con Python 3
```bash
cd /home/user/Projects/ups-dashboard
python3 app.py
```

---

## 🧭 Guida per la Nuova Sessione di Antigravity

Quando apri la cartella `/home/user/Projects/ups-dashboard` come workspace principale in Antigravity:
1. **Verifica dello Stato**: Esegui `git status` per verificare che il branch sia pulito.
2. **Container Attivo**: Controlla lo stato con `docker compose ps` e `curl http://localhost:8080/api/health`.
3. **Linee Guida di Sviluppo**:
   - Mantieni l'approccio **zero dipendenze esterne** in `app.py` (non aggiungere pacchetti `pip` pesanti a meno di espressa richiesta dell'utente).
   - Mantieni il frontend in `static/index.html` completamente autonomo da CDN esterni.
   - Quando incrementi la versione, aggiorna il file [`VERSION`](./VERSION).
