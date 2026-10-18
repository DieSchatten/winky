# Changes / Änderungen

## 0.15.0 (18.10.2026)

- Lock automatically: choose in Winky (Unlocks) how long the computer stays unlocked without
  input. Automatisch sperren: in Winky (Freigaben) einstellen, wie lange der Rechner ohne
  Eingabe entsperrt bleibt.
- Optional: seal face data in the TPM chip (Advanced → Your data); on the disk it is then
  stored only encrypted, unsealed into memory at startup. Wahlweise Gesichtsdaten im TPM-Chip
  versiegeln (Erweitert → Deine Daten); auf der Festplatte liegen sie dann nur verschlüsselt,
  beim Start werden sie in den Arbeitsspeicher entsiegelt.
- Corrected: TPM sealing (keyring, face data) doesn't protect against a USB stick with Ubuntu
  or a related Linux started on the computer, even with Secure Boot; the app and the docs now
  say so. Richtiggestellt: Die TPM-Versiegelung (Schlüsselbund, Gesichtsdaten) schützt auch
  mit Secure Boot nicht gegen einen USB-Stick mit Ubuntu oder einem verwandten Linux; App und
  Doku sagen das jetzt.
- sudo: just start typing your password while Winky waits for the ✌; the camera turns off,
  stars show your input, and sudo continues right away (before, it was visible and only read
  after the wait). sudo: Passwort einfach lostippen, während Winky aufs ✌ wartet; die Kamera
  geht aus, Sterne zeigen die Eingabe, und sudo geht sofort weiter (bisher war es sichtbar
  und wurde erst nach der Wartezeit gelesen).
- The desktop notice restarts itself after an update instead of running the old version
  until the next login. Der Desktop-Hinweis startet sich nach einem Update selbst neu, statt
  bis zur nächsten Anmeldung in der alten Fassung zu laufen.
- Turning off “Infrared camera only for Winky” gives the camera back to the video group right
  away, not only after a restart. Das Ausschalten von „Infrarot-Kamera nur für Winky“ gibt die
  Kamera sofort wieder an die Gruppe video, nicht erst nach einem Neustart.

## 0.14.0 (16.10.2026)

- Optional: infrared camera only for Winky (Advanced → Camera); other programs can no longer
  switch it on. Wahlweise Infrarot-Kamera nur für Winky (Erweitert → Kamera); andere
  Programme können sie nicht mehr einschalten.

## 0.13.0 (15.10.2026)

- Optional: unlock only with face and ✌ (lock screen and login after startup), so nobody
  gets in by holding the computer up to your face. Wahlweise nur mit Gesicht und ✌
  entsperren (Sperrbildschirm und Anmeldung nach dem Start).
- Add to your face: named additions such as “With glasses”, up to three, each can be deleted;
  only images that match your face are added. Gesicht ergänzen: benannte Ergänzungen wie
  „Mit Brille“, höchstens drei, einzeln löschbar; übernommen wird nur, was zu deinem Gesicht
  passt.
- sudo: missed the ✌? Press Enter without a password and Winky asks again; the terminal says
  so. sudo: ✌ verpasst? Enter ohne Passwort, und Winky fragt noch einmal; das Terminal sagt es.

## 0.12.0 (13.10.2026)

- Calmer app with a sidebar: overview with the Winky icon and status, unlocks, face, history,
  security and advanced settings each on their own page. Ruhigere App mit Seitenleiste:
  Übersicht mit Winky-Symbol und Status, Freigaben, Gesicht, Verlauf, Sicherheit und
  Erweitert auf eigenen Seiten.
- Risky options explain their risk with an info button; login after startup asks again before
  it is turned on. Riskante Optionen erklären ihr Risiko über einen Info-Knopf; die Anmeldung
  nach dem Start fragt vor dem Einschalten nach.
- Round camera view with a progress ring. Rundes Kamerabild mit Fortschrittsring.
- History on its own page with up to 20 entries; it names approved administrator dialogs and
  logins after startup correctly. Verlauf auf eigener Seite mit bis zu 20 Einträgen; er
  benennt freigegebene Administrator-Dialoge und Anmeldungen nach dem Start richtig.

## 0.11.1 (11.10.2026)

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
