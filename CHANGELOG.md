# Changes / Änderungen

## 0.11.0 (10.10.2026)

- Optional: login after startup with your face (keyring stays locked).
  Wahlweise Anmeldung nach dem Start mit dem Gesicht (Schlüsselbund bleibt zu).
- Adjustable time for the ✌ (5 to 30 seconds for sudo); the ✌ window shows “You are
  approving:” with the full command or action.
  Einstellbare Zeit für das ✌; das ✌-Fenster zeigt „Du gibst frei:“ mit Befehl oder Aktion.
- Experimental: after a face login, also unlock the keyring with the login password sealed
  in the TPM chip. Experimentell: Schlüsselbund nach Gesichtsanmeldung entsperren, Passwort
  versiegelt im TPM-Chip.
- “About Winky” with version; release notes in the software manager.
  „Über Winky“ mit Version; Versionshinweise in der Software-Verwaltung.

## 0.10.0 (10.10.2026)

- Administrator dialogs (Polkit) with face and ✌, five groups to turn on separately: updates,
  software, downloaded packages, programs as administrator, all others.
  Administrator-Dialoge mit Gesicht und ✌, fünf einzeln schaltbare Gruppen.
- Pause now also applies to KeePassXC. Die Pause gilt jetzt auch für KeePassXC.

## 0.9.0 (10.10.2026)

- English and German, depending on the system language: app, ✌ notice, terminal messages,
  password dialogs, software manager description.
  Englisch und Deutsch je nach Systemsprache.
- Own package source: updates and search ("Windows Hello", "face unlock") through the
  software manager. Eigene Paketquelle für Updates und Suche in der Software-Verwaltung.

## 0.8.1 (10.10.2026)

- Updating no longer asks about the settings file; your settings are kept.
  Beim Aktualisieren fragt apt nicht mehr nach der Einstellungsdatei.

## 0.8.0 (09.10.2026)

- First public version. Erste öffentliche Version.
