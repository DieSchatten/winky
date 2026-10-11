# Changes / Änderungen

## 0.11.1

- Switches react only to real changes; the keyring dialog no longer opens twice.
  Schalter reagieren nur auf echte Änderungen; der Schlüsselbund-Dialog öffnet nicht mehr doppelt.
- Tested on two laptops, including a Microsoft Surface Laptop 4.
  An zwei Laptops getestet, darunter ein Microsoft Surface Laptop 4.

## 0.11.0 (10.10.2026)

- Optional: login after startup with your face (keyring stays locked).
  Wahlweise Anmeldung nach dem Start mit dem Gesicht (Schlüsselbund bleibt zu).
- Adjustable time for the ✌ (5 to 30 seconds for sudo); the ✌ window shows “You are
  approving:” with the full command or action.
  Einstellbare Zeit für das ✌; das ✌-Fenster zeigt „Du gibst frei:“ mit Befehl oder Aktion.
- Administrator dialogs now work inside the password dialog itself (PAM `polkit-1`): one
  switch instead of five groups; background permission checks never reach Winky. Earlier
  groups are switched over automatically.
  Administrator-Dialoge laufen im Passwortdialog selbst: ein Schalter statt fünf Gruppen.
- Status messages at the login screen. Statusmeldungen an der Anmeldemaske.
- Check with a second person: asks first whether the person is ready; recognizes when it was
  you; only offers stricter settings that still recognize you. Prüfung mit zweiter Person:
  erst Rückfrage, erkennt „das warst du“, strenger nur, wenn du danach noch erkannt wirst.
- Clear notice with “Log out now” if the desktop can’t show its password dialog.
  Klarer Hinweis mit „Jetzt abmelden“, wenn der Desktop keinen Passwortdialog zeigen kann.
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
