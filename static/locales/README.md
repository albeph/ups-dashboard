# Guida all'Aggiunta di Nuove Lingue / How to Add New Languages

Questa cartella contiene i file di localizzazione (i18n) per **UPS Dashboard**.

The UPS Dashboard features an automatic internationalization system based on JSON translation files located in this directory (`static/locales/`).

---

## 🚀 Come Funziona il Sistema i18n / How It Works

1. **Rilevamento Automatico (Auto-Discovery)**:
   - Il backend Python scansiona automaticamente la cartella `static/locales/` alla ricerca di file `.json`.
   - Ogni file valido viene registrato e reso disponibile nelle impostazioni della dashboard (nella scheda **Aspetto**).
   - Non è necessario modificare il codice sorgente né ricompilare: basta aggiungere il file `.json` e riavviare o ricaricare!

2. **Scelta della Lingua**:
   - Di default, la lingua viene rilevata automaticamente dalle impostazioni del browser (`navigator.language`).
   - Se la lingua del browser non è disponibile tra i file di traduzione, il sistema effettua automaticamente il **fallback su Inglese (`en`)**.
   - L'utente può forzare manualmente la lingua desiderata dal menu delle impostazioni; la preferenza viene salvata in `localStorage`.

3. **Fallback a livello di chiave**:
   - Se una stringa o una chiave non è tradotta nel file JSON di una nuova lingua, viene mostrato il valore predefinito in lingua inglese.

---

## 📁 Convenzione Nomi File / File Naming Convention

Il nome del file deve corrispondere al codice lingua ISO 639-1 (a due lettere, minuscolo):
- `it.json` -> Italiano
- `en.json` -> English
- `de.json` -> Deutsch
- `fr.json` -> Français
- `es.json` -> Español
- `pt.json` -> Português

---

## 🛠️ Struttura di un File di Traduzione / JSON Schema

Ogni file `.json` deve contenere il blocco `_meta` seguito dalle varie sezioni di traduzione:

```json
{
  "_meta": {
    "code": "fr",
    "name": "Français",
    "flag": "🇫🇷"
  },
  "topbar": {
    "brand_title": "UPS Dashboard",
    "status_online": "En ligne",
    "status_offline": "Hors ligne",
    "status_battery": "Sur batterie (OB)",
    "btn_settings": "Paramètres",
    "btn_settings_title": "Paramètres du serveur NUT et du tableau de bord",
    "btn_lock": "Verrouiller",
    "btn_lock_title": "Verrouiller la session"
  },
  "cards": {
    "power_title_watts": "Puissance & Charge",
    "power_title_load": "Charge UPS",
    "load_normal": "Normale",
    "load_high": "Élevée",
    "load_overload": "Surcharge",
    "voltage_label": "Tension",
    "battery_title": "État de la Batterie",
    "battery_charged": "Chargée",
    "battery_medium": "Moyenne",
    "battery_critical": "Critique",
    "power_feed_label": "Alimentation",
    "feed_online": "Secteur électrique",
    "feed_battery": "Batteria",
    "feed_bypass": "Bypass",
    "feed_disconnected": "Déconnecté"
  },
  "subbar": {
    "target_nut": "Cible NUT",
    "server_unreachable": "• Serveur inaccessible",
    "waiting_data": "En attente de données...",
    "last_update": "Dernière mise à jour : ",
    "error_prefix": "Erreur : ",
    "nut_unreachable": "Serveur NUT inaccessible"
  },
  "modal": {
    "title": "Paramètres du tableau de bord",
    "tab_status": "État",
    "tab_nut": "Serveur NUT",
    "tab_appearance": "Apparence",
    "tab_security": "Sécurité",
    "btn_cancel": "Annuler",
    "btn_save": "Enregistrer les modifications"
  },
  "tab_status": {
    "card_conn_title": "Connexion au Serveur NUT",
    "card_ups_title": "État Opérationnel de l'UPS",
    "field_host_port": "Hôte & Port",
    "field_ups_id": "Identifiant UPS",
    "field_last_sync": "Dernière Synchro",
    "field_feed": "Alimentation",
    "field_model": "Modèle Détecté",
    "field_max_watts": "Puissance Maximale",
    "field_metrics": "Charge / Batterie",
    "field_refresh_rate": "Fréquence d'actualisation",
    "field_voltage": "Tension Secteur",
    "conn_online": "EN LIGNE",
    "conn_offline": "HORS LIGNE",
    "status_online": "EN LIGNE (OL)",
    "status_battery": "SUR BATTERIE (OB)",
    "status_offline": "HORS LIGNE",
    "waiting": "En attente...",
    "model_generic": "Non détecté ou générique",
    "metrics_unit": "{load}% charge • {batt}% batterie"
  },
  "tab_nut": {
    "section_conn_status": "État Actuel de la Connexion",
    "status_waiting": "En attente de vérification...",
    "status_connected": "Serveur Connecté",
    "status_not_connected": "Serveur Déconnecté",
    "status_unreachable": "Inaccessible",
    "section_params": "Paramètres de Connexion",
    "label_host": "Hôte ou IP",
    "ph_host": "ex. 192.168.1.50",
    "label_port": "Port TCP",
    "ph_port": "3493",
    "label_ups_name": "Nom de l'UPS",
    "ph_ups_name": "ups",
    "section_credentials": "Identifiants Démon NUT (Optionnel)",
    "label_nut_user": "Utilisateur NUT",
    "ph_nut_user": "ex. upsmon",
    "label_nut_pwd": "Mot de passe NUT",
    "ph_nut_pwd_set": "•••••••• (déjà défini)",
    "ph_nut_pwd_unset": "Aucun mot de passe défini",
    "section_polling": "Fréquence de Rafraîchissement",
    "label_polling": "Intervalle d'interrogation",
    "unit_sec": "sec",
    "desc_polling": "Intervalle en secondes entre les requêtes vers le serveur NUT et le rafraîchissement d'affichage (défaut : 2s)."
  },
  "tab_appearance": {
    "section_style": "Style des Jauges de Télémétrie",
    "mode_bars_title": "Barres Horizontales",
    "mode_bars_desc": "Affichage linéaire et compact avec barres de progression à gradient dynamique.",
    "mode_gauge_title": "Demi-cercle (Jauge)",
    "mode_gauge_desc": "Tableau de bord visuel avec cadrans circulaires SVG inspirés des compteurs analogiques.",
    "mode_note": "Le mode choisi est appliqué immédiatement et mémorisé dans le navigateur.",
    "section_lang": "Langue de l'Interface",
    "lang_auto": "🌐 Automatique (Détectée par le navigateur)",
    "lang_desc": "Sélectionnez la langue préférée ou conservez la détection automatique du navigateur."
  },
  "tab_security": {
    "section_auth_status": "État de l'Authentification",
    "status_protected_strong": "Accès Protégé",
    "status_protected_desc": " : Le tableau de bord nécessite une authentification par mot de passe.",
    "status_open_strong": "Accès Libre",
    "status_open_desc": " : Aucun mot de passe configuré pour le tableau de bord.",
    "section_update_pwd": "Mettre à jour le Mot de Passe",
    "label_new_pwd": "Nouveau Mot de Passe",
    "ph_new_pwd": "Laisser vide pour conserver l'actuel",
    "pwd_note": "Chiffrement irréversible avec PBKDF2-HMAC-SHA256 (100 000 itérations)."
  },
  "lock_screen": {
    "title": "Accès Protégé",
    "desc": "Entrez le mot de passe pour déverrouiller le tableau de bord",
    "ph_pwd": "Mot de passe...",
    "btn_login": "Se connecter",
    "err_wrong_pwd": "Mot de passe incorrect",
    "err_conn": "Erreur de connexion au serveur"
  },
  "toasts": {
    "saving": "Enregistrement en cours...",
    "saved": "Paramètres enregistrés avec succès !",
    "err_required_fields": "Veuillez renseigner l'Hôte, le Port et le Nom de l'UPS dans l'onglet Serveur NUT.",
    "err_invalid_poll": "Intervalle de rafraîchissement invalide (minimum 0.5 secondes).",
    "err_network": "Erreur réseau lors de l'enregistrement des paramètres",
    "err_prefix": "Erreur : ",
    "alert_load_fail": "Impossible de charger les paramètres : "
  },
  "ups_status_map": {
    "OL": "Secteur électrique",
    "OB": "Sur batterie (OB)",
    "LB": "Batterie basse (LB)",
    "HB": "Batterie haute (HB)",
    "RB": "Remplacer batterie (RB)",
    "CHRG": "En charge (CHRG)",
    "DISCHRG": "En décharge (DISCHRG)",
    "BYPASS": "Bypass actif",
    "CAL": "Étalonnage en cours",
    "OFF": "Éteint",
    "OVER": "Surcharge",
    "TRIM": "Compensation surtension (Trim)",
    "BOOST": "Compensation sous-tension (Boost)"
  }
}
```

---

## 📝 Guida Passo-Passo per Contribuire / Step-by-Step Guide

1. Copia uno dei file esistenti come base (es. `cp en.json es.json`).
2. Aggiorna l'oggetto `_meta` con il codice lingua, nome localizzato ed emoji della bandiera:
   ```json
   "_meta": {
     "code": "es",
     "name": "Español",
     "flag": "🇪🇸"
   }
   ```
3. Traduci tutte le stringhe mantenendo intatti i segnaposto come `{load}`, `{batt}` o tag HTML.
4. Salva il file come codifica **UTF-8** (senza BOM).
5. Ricarica la pagina: la nuova lingua comparirà immediatamente nel menu a tendina delle impostazioni!
