# Localization Guide (i18n)

This directory (`image/static/locales/`) stores JSON translation files for **UPS Web Dashboard**.

---

## How Auto-Discovery Works

1. **Automatic Registration**:
   - The Python backend (`LocaleRegistry`) scans `image/static/locales/` for all `*.json` files.
   - Each valid file is automatically exposed via `GET /api/locales` and appears in **Settings → Appearance → Interface Language**.
   - No backend or frontend code changes are required to add a new language.

2. **Language Selection & Fallback**:
   - By default (`auto`), the UI detects the browser language (`navigator.language`).
   - If the detected language is unavailable, the dashboard falls back to **English (`en`)**.
   - Users can override the language manually in Settings; the preference is persisted in `localStorage`.

3. **Per-Key Fallback**:
   - If an individual key is missing from a locale file, `I18nManager` automatically falls back to the corresponding English string in `en.json`.

---

## File Naming Convention

Use the lowercase two-letter **ISO 639-1** language code:

- `en.json` — English (canonical fallback)
- `it.json` — Italiano
- `de.json` — Deutsch
- `fr.json` — Français
- `es.json` — Español
- `pt.json` — Português

---

## Translation JSON Schema

Every locale file must define a `_meta` header followed by the UI translation sections. Preserve all placeholder tokens (`{pct}`, `{ups_rt}`, `{low_rt}`, `{load}`, `{batt}`) and HTML formatting tags verbatim.

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
    "feed_battery": "Batterie",
    "feed_bypass": "Bypass",
    "feed_disconnected": "Déconnecté",
    "blackout_duration_label": "Durée de la coupure",
    "remaining_time_label": "Temps restant",
    "shutdown_threshold_tooltip": "Seuil d'arrêt pour toutes les machines ({pct}%)",
    "remaining_time_tooltip": "Calculé à partir du temps estimé par l'UPS ({ups_rt}) moins le seuil d'autonomie minimale ({low_rt}). Cette durée est indicative : le système peut s'éteindre plus tôt si la batterie descend sous le pourcentage configuré.",
    "remaining_time_tooltip_no_low": "Temps estimé par l'UPS ({ups_rt}) — aucun seuil d'autonomie minimale configuré. Cette durée est indicative : le système peut s'éteindre plus tôt si la batterie descend sous le pourcentage configuré."
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
    "field_charge_low": "Seuil de Charge Basse",
    "field_runtime_low": "Seuil d'Autonomie Basse",
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
    "lang_desc": "Sélectionnez la langue préférée ou conservez la détection automatique du navigateur.",
    "section_pwa": "Application Web (PWA)",
    "pwa_title": "Application Mobile & Bureau",
    "btn_install": "Installer",
    "pwa_desc": "Installez le tableau de bord comme application plein écran : sur <strong>iOS (Safari)</strong> appuyez sur Partager ⎋ puis <em>\"Sur l'écran d'accueil\"</em> ; sur <strong>Android (Chrome)</strong> ouvrez le menu ⋮ puis sélectionnez <em>\"Installer l'application\"</em>."
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

## Step-by-Step Contribution Guide

1. Copy the English reference pack:
   ```bash
   cp image/static/locales/en.json image/static/locales/es.json
   ```
2. Update the `_meta` object with the ISO 639-1 code, native language name, and flag emoji.
3. Translate all string values while keeping placeholders (e.g. `{pct}`, `{load}`, `{batt}`) and inline HTML tags intact.
4. Save the file using **UTF-8** encoding (without BOM) and validate JSON syntax:
   ```bash
   python3 -m json.tool image/static/locales/es.json > /dev/null
   ```
5. Reload the dashboard — the new language will automatically appear in the language dropdown.
