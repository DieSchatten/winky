# Änderungen

## 0.8.0

- Erste öffentliche Version.
- Eigenständig: Gesichtssuche und Gesichtsvergleich mit freien Modellen aus dem OpenCV Zoo,
  YuNet (MIT) und SFace (Apache-2.0), mit neu geschriebenem eigenem Code für Suche,
  Ausrichtung und Vorverarbeitung. Das bisherige Vergleichsmodell war nur für
  nicht-kommerzielle Zwecke freigegeben.
- Beim Aktualisieren werden alte Gesichtsdaten gelöscht; jede Person nimmt ihr Gesicht neu
  auf.
- KeePassXC standardmäßig nur mit Gesicht **und** ✌ (abschaltbar), mit Desktop-Meldung,
  Begrenzung und Abbruch bei gleichzeitigen Anfragen wie bei sudo. Getestet mit KeePassXC
  2.8.0 Beta 1. Deutlicher Hinweis in der App, dass das erst ab KeePassXC 2.8 geht.
- Großes Hinweisfenster mit ✌ oben in der Bildschirmmitte statt der leicht übersehenen
  Benachrichtigung, für sudo und KeePassXC. Es nimmt nie den Tastaturfokus.
- Herausgeber steht an einer Stelle (AUTHORS); Messwerkzeuge finden die Infrarot-Kamera
  selbst.

## 0.7.0 (09.10.2026)

- App neu aufgebaut für Menschen ohne Technikwissen: Ein Assistent führt in sechs Schritten
  durch die Einrichtung (Kamera, Gesicht aufnehmen, Ausprobieren, zweite Person, Einschalten,
  Terminal). Danach zeigt die Startseite nur noch Schalter und „Ausprobieren“; Zahlen und
  Technik stehen unter „Erweitert“, Erklärungen und Notausschalter unter „Sicherheit und
  Hilfe“.
- Prüfung mit einer zweiten Person: 5 Sekunden Countdown nach der Passworteingabe, um aus
  dem Bild zu gehen. Ist die Person zu ähnlich, stellt ein Knopf Winky passend strenger ein.
- Wird die Strenge über den eigenen Testwert gestellt, verlangt die App erneutes
  Ausprobieren.
- Icon mit Hand und ✌.
- Dokumentation: README für Anwender, SICHERHEIT.md mit Bedrohungsmodell und Risiken,
  ENTWICKLUNG.md, dieses Änderungsprotokoll.
- Messwerkzeug heißt jetzt `winky-messung`; das Augenmodell der verworfenen Zwinker-Messung
  liegt nur noch bei den Werkzeugen.

## 0.6.0 (09.10.2026)

- sudo im Terminal wahlweise mit Gesicht und Handzeichen ✌ bestätigen (MediaPipe Gesture
  Recognizer). Nur lokale Terminals, Einschalten mit Administratorpasswort und eigenem
  ✌-Test, Desktop-Meldung mit dem Befehl, Begrenzung auf drei unbestätigte Anfragen,
  gleichzeitige Anfragen brechen beide ab.

## 0.5.1 (08.10.2026)

- Schlichteres Icon in einem Farbton.

## 0.5.0 (08.10.2026)

- Neuer Name Winky, Icon, Bildschirmfotos für die
  Software-Verwaltung, MIT-Lizenz.

## 0.4.1 (08.10.2026)

- In der Software-Verwaltung sichtbar und deinstallierbar.

## 0.4.0 (07.10.2026)

- KeePassXC-Schnellentsperren per Gesicht vorbereitet (Polkit-Regel nur für
  `org.keepassxc.KeePassXC.unlockDatabase`).

## 0.3.0 (07.10.2026)

- App für den Alltag und andere Rechner: Kamera-Autoerkennung, Vorgabe-Strenge 0,65,
  Gegenprobe, eigenes Gesicht mit eigenem Passwort, Systemeinstellungen mit
  Administratorpasswort.

## 0.2.0 (07.10.2026)

- Erste vollständige Fassung: PAM-Modul, abgeschotteter Prüfdienst, Verwaltungshelfer,
  App, Debian-Paket.

## Machbarkeitsmessung (06.10.2026)

- Messwerkzeug für die Gesichtserkennung im Infrarot-Bild, Vergleich zweier
  Erkennungsmodelle.
