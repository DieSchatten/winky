# Entwicklung

## Bauen

Gebaut wird nur im Container (`Containerfile`, Ubuntu 24.04, per Digest festgeschrieben),
ohne Netz. Fremddateien (ONNX Runtime, Erkennungsmodelle) lädt
`scripts/abhaengigkeiten.sh` einmal nach `vendor/` und prüft sie per SHA-256.

```bash
./scripts/paket-bauen.sh
```

Das Skript prüft die AppStream-Beschreibung, baut, führt Komponenten- und PAM-Tests aus und
bricht bei einem Fehler ab, bevor es `bau/winky_<version>_amd64.deb` zusammenstellt. Commit
und Bauzeit landen in `/usr/share/winky/version.json` und erscheinen in der App unter
„Erweitert“.

## Übersetzungen

Grundsprache ist Englisch, Übersetzungen liegen in `po/<sprache>.po` (gettext, Domäne
`winky`). Der Paketbau erzeugt die Vorlage `po/winky.pot` aus App, Hinweisen und
Verwaltungshelfer und bricht ab, wenn eine Sprache unvollständig ist. Neue Texte in eine
.po-Datei übernehmen und eine neue Sprache anfangen:

```bash
podman run --rm -v "$PWD":/src:Z -w /src localhost/winky-bau:2 ./scripts/uebersetzungen.sh aktualisieren
cp po/winky.pot po/fr.po   # neue Sprache, dann Kopf und Übersetzungen ausfüllen
```

Das PAM-Modul (drei Terminalmeldungen), die Polkit-Aktionen, die Desktop-Dateien und die
Store-Beschreibung tragen Englisch und Deutsch direkt in sich.

## Veröffentlichen

1. Version in `CMakeLists.txt` erhöhen, `CHANGELOG.md` ergänzen, `./scripts/paket-bauen.sh`
   und die Systemtests.
2. Release auf GitHub mit der .deb-Datei.
3. Paketquelle (APT, GitHub Pages, Zweig `gh-pages`) bauen und unterschreiben; gpg fragt nach
   dem Passwort des Signaturschlüssels:

   ```bash
   ./scripts/paketquelle.sh
   ```

   Der Inhalt von `bau/paketquelle` ersetzt den Zweig `gh-pages` (ein Commit, ohne alte
   Versionen). Die Quelle enthält AppStream-Daten (DEP-11) samt Symbolen; damit findet die
   Software-Verwaltung Winky mit Beschreibung und Suchbegriffen. Das Paket bringt Quelle und
   Schlüssel (`packaging/winky.sources`, `packaging/winky-archive-keyring.gpg`) selbst mit.

## Aufbau

| Teil | Ort | Aufgabe |
|---|---|---|
| PAM-Modul | `src/pam/pam_winky.c` | klein, nur libc und libpam; Freigabeliste, Zeitlimit, fragt den Prüfdienst |
| Prüfdienst | `src/daemon/` | `winky-matcher`, je Anfrage per Socket gestartet, als `_winky` in einer systemd-Sandbox (Bewertung 1,0); Kamera, Erkennung, Entscheidung, Sperrzähler |
| Erkennungskern | `src/core/`, `src/capture/` | YuNet (Gesichtssuche mit 5 Punkten), 5-Punkt-Ausrichtung, SFace (Vergleich, 128 Werte), MediaPipe-Handzeichen, V4L2-Infrarot |
| Verwaltungshelfer | `src/verwalten/winky-verwalten` | root über Polkit: als `winky-gesicht` mit dem eigenen Passwort, als `winky-verwalten` mit dem Administratorpasswort |
| Polkit-Prüfung | `src/polkit/winky_polkit_pruefung.c` | für die Polkit-Regeln (KeePassXC, Administrator-Dialoge), nur libc |
| Hinweise | `src/hinweis/winky-hinweis` | Hinweisfenster mit großem ✌ zu jeder Anfrage (sudo, KeePassXC), ohne Fokus über XWayland; Benachrichtigung bei Fehlschlag (Autostart) |
| App | `src/app/` | GTK4/libadwaita: Assistent, Startseite, Kamera, Sicherheit, Erweitert |
| Protokoll | `src/protokoll/protokoll.h` | Nachrichten zwischen PAM-Modul, Helfer und Prüfdienst |

Dateien auf dem System:

- `/etc/winky/winky.conf`: Strenge (`schwelle`), Kamera, Blinkprüfung, sudo; root-eigen.
- `/etc/winky/sudo-ein`, `/etc/winky/disabled`: Schalter für sudo mit ✌ und Notschalter.
- `/var/lib/winky/<uid>/vorlagen.bin`: Merkmalsvektoren je Benutzer, root:_winky 0640.
- `/var/lib/winky/<uid>/geste-ok`: bestandener ✌-Test.
- `/var/lib/winky/status/<uid>.json`: Stand für die App (Aufnahme, Test, zweite Person).
- `/run/winky/sperre/`: Fehlversuchs- und sudo-Zähler, flüchtig.
- `/run/winky/anfrage/<uid>.json`: laufende Anfrage mit ✌ (Zweck, Befehl, Stand) für das Hinweisfenster.

Das Sicherheitsmodell steht in [SICHERHEIT.md](SICHERHEIT.md).

## Tests

- **Komponenten** (`tests/test_dienst.cc`, 75 Prüfungen): Konfiguration, Vorlagen samt
  Verknüpfungs- und Besitzerangriffen, Entscheidungsregel, Sperrzähler, Gesicht und ✌,
  sudo-Begrenzung. Läuft beim Paketbau.
- **PAM** (`tests/pam_test.py`, 42 Prüfungen): echtes libpam mit pamtester und
  nachgebautem Prüfdienst. Läuft beim Paketbau.
- **App** (`werkzeuge/test/gui_logik_test.py`, 71 Prüfungen): spielt den Assistenten von
  vorn bis hinten durch, dazu Startseite, Erweitert und Fehlerfälle; mit einer Attrappe des
  Helfers, ohne Kamera und ohne root, im GTK-Broadway-Backend:

  ```bash
  gtk4-broadwayd :9 &
  WINKY_ATTRAPPE=1 WINKY_TESTWURZEL=$(mktemp -d) GDK_BACKEND=broadway BROADWAY_DISPLAY=:9 \
    python3 werkzeuge/test/gui_logik_test.py
  ```

- **Hinweise** (`werkzeuge/test/hinweis_test.py`, 12 Prüfungen): welcher Stand der
  Anfragedatei zu welchem Hinweis führt (Fenster, ✓, Benachrichtigung, alte Anfragen).
- **Software-Verwaltung** (`tests/systemtest/store-test.sh`, 29 Prüfungen): Aktualisieren,
  Deinstallieren und Neuinstallieren über PackageKit;
  AppStream-Beschreibung, Icon, Bildschirmfotos.
- **sudo-Kette** (`tests/systemtest/sudo-test.sh`, 56 Prüfungen): echter Prüfdienst, echte
  Kamera, echtes libpam im Wegwerf-System. Einschalten nur mit aktiver Gesichtsentsperrung
  und bestandenem ✌-Test, Zeitlimit, Desktop-Hinweis, gleichzeitige Anfragen, Begrenzung,
  Zurücksetzen per Passwort, ohne Terminal, Schalter aus, su/login/polkit unberührt,
  KeePassXC über das echte Polkit-Prüfprogramm mit und ohne ✌, Rückbau.

Die beiden Systemtests laufen in einem Wegwerf-Container mit systemd
(`tests/systemtest/Containerfile`); der Aufruf steht jeweils am Anfang der Skripte.

## Bildschirmfotos und Icon

Das Icon ist `packaging/icons/io.github.dieschatten.Winky.svg`: ein Schloss, dessen Körper ein
Bildschirm mit zwinkerndem Gesicht ist, daneben eine Hand mit ✌. Die Bildschirmfotos für die
Software-Verwaltung entstehen mit der Attrappe und einem gezeichneten Kamerabild, nie mit
einem echten Gesicht:

```bash
./scripts/bildschirmfotos.sh
```

Mit `WINKY_FOTO_ZIEL=ordner WINKY_FOTO_ALLE=1` nimmt das Skript zusätzlich jeden
Assistentenschritt und „Erweitert“ auf, zur Durchsicht.

## Messwerkzeuge

Nicht im Paket. Das Messwerkzeug `winky-messung` (`werkzeuge/messung/`) und die
Kalibrier-Oberfläche (`werkzeuge/kalibrierung/`) dienen dazu, Entscheidungen mit Messungen zu
belegen. Regel: Kriterien vor der Messung festlegen, Entwicklungs- und Prüfdaten trennen.

```bash
./scripts/kalibrierung.sh
```

Das Werkzeug hat zwei Seiten:

- **Erkennung:** eigene Sitzungen (normal, entsperren, dunkel, nah, fern, seitlich, Brille),
  niemand im Bild, Täuschungsversuche (Handyfoto, Ausdruck) und andere Personen. Die
  Auswertung empfiehlt die Strenge: mindestens 0,08 über dem höchsten Wert einer anderen
  Person, mindestens 70 % der eigenen Bilder darüber, Entscheidung binnen 1,5 s. Ergebnis
  mit SFace (09.10.2026, eine Person): ohne Brille mindestens 0,69 (fern), sonst ab 0,78,
  Median 0,84 bis 0,96; mit Brille, aber ohne Brille eingelernt, Median 0,70 und Minimum
  0,51; Handyfoto und leeres Bild ergaben kein Gesicht; Entscheidung nach etwa 0,4 s,
  seitlich 1,2 s. Andere Personen und ein Ausdruck fehlen noch, die Vorgabe 0,65 ist
  deshalb vorläufig. Neu messen lohnt sich bei einem anderen Modell oder einer anderen
  Kameraklasse.
- **Handzeichen ✌:** Bestätigen wie im echten Einsatz mit Rückmeldung, im Dunkeln, mit
  Abstand, dazu Tippen und Alltag ohne Zeichen. Ergebnis 09.10.2026: 11 von 12 erkannt
  (92 %), Median 0,99 s, 0 Fehlalarme, also machbar nach der vorab festgelegten Regel
  (`werkzeuge/kalibrierung/auswerten_hand.py`).

Verworfen wurden vorher Zwinkern (zu personenabhängig, Prüfrunde 72 % erkannt und 5
Fehlalarme), „Daumen hoch“ und „Nase antippen“ (die Handflächensuche findet Faust und
Handrücken im Infrarot-Bild nicht). Code und Messdaten dazu sind entfernt bzw. archiviert,
nachzulesen in der Git-Historie.

Messdaten (Kennzahlen als CSV, keine Bilder) liegen unter `~/.local/share/winky/messungen`
und gehören nicht ins Repo. Ältere Messreihen lassen sich nach
`~/.local/share/winky/messungen-archiv/` verschieben, dann zeigt das Werkzeug sie nicht mehr.

Die MediaPipe-Modelle wurden mit `scripts/mediapipe-umwandeln.sh` von TFLite nach ONNX
umgewandelt; Herkunft, Prüfsummen und Abgleich stehen in `modelle/HERKUNFT.md`.

## Sonstiges

- `werkzeuge/test/gui-broadway.sh`: startet die App mit Attrappe im Browser
  (http://localhost:8087), zum Ausprobieren ohne Kamera.
