# Sicherheit von Winky

**Deutsch** · [English](SECURITY.md)

Winky ist ein **Komfort** für die Bildschirmsperre, kein Ersatz für ein gutes Passwort und
keine Festplattenverschlüsselung. Diese Seite beschreibt ehrlich, wogegen Winky schützt,
wogegen nicht, und welche Risiken in der Benutzung und in der Technik selbst stecken.

Stand: Version 0.15.0. Winky wurde von einer Einzelperson mit KI-Unterstützung entwickelt
und ist **nicht unabhängig geprüft**. Die Erkennung wurde an einem Laptop mit einer
Windows-Hello-Kamera mit der eigenen und einer weiteren Person gemessen und an einem
Microsoft Surface Laptop 4 ausprobiert.

## Kurz gesagt

- Das Gesicht öffnet nur die **Bildschirmsperre einer laufenden Sitzung**. Bei su, SSH und
  der Konsole gilt immer das Passwort, nach dem Einschalten des Rechners und in grafischen
  Administrator-Dialogen ebenso, außer du schaltest sie eigens frei.
- **sudo im Terminal** lässt sich wahlweise mit Gesicht **und** dem Handzeichen ✌
  bestätigen. Das ist ausgeschaltet, bis ein Administrator es einschaltet.
- **Das Passwort funktioniert immer.** Erkennt Winky dich nicht, erscheint spätestens nach
  drei Sekunden (Sperrbildschirm) bzw. nach der eingestellten Zeit für das ✌ (8 bis 30
  Sekunden, sudo) die gewohnte Abfrage.
- Das Sicherheitsniveau entspricht etwa **Windows Hello ohne erweiterten
  Täuschungsschutz**: Fotos auf Bildschirmen scheitern. Einen gezielt gemachten
  Infrarot-Ausdruck oder eine Maske hält Winky nicht sicher auf.

## Wogegen Winky schützt und wogegen nicht

| Lage | Was passiert | Bewertung |
|---|---|---|
| Jemand setzt sich an deinen gesperrten Rechner | Sein Gesicht passt nicht, nach drei Sekunden kommt das Passwortfeld. | geschützt, solange die Person dir nicht sehr ähnlich sieht |
| Foto oder Video von dir auf Handy oder Bildschirm | Bildschirme sind im Infrarot-Bild schwarz. In der Messung wurde ein Handyfoto gar nicht als Gesicht erkannt. | geschützt |
| Ausdruck deines Gesichts, der im Infrarot sichtbar ist, oder eine Maske | Nicht getestet. Winky hat keine echte Lebenderkennung. | **nicht sicher geschützt** |
| Zwilling oder sehr ähnliches Geschwister | Kein Gesichtssystem unterscheidet das zuverlässig. | **nicht geschützt** |
| Jemand hält dir den Rechner vors Gesicht oder du schläfst | Winky prüft nicht, ob du einverstanden bist oder die Augen offen hast. | ab Werk **nicht geschützt**; geschützt mit „Entsperren nur mit ✌“ (sudo braucht das ✌ immer) |
| Rechner wird ausgeschaltet gestohlen | Winky spielt keine Rolle. Ohne verschlüsselte Festplatte sind die Daten offen. | Sache der Festplattenverschlüsselung |
| Rechner wird gesperrt, aber eingeschaltet gestohlen | Der Dieb braucht dein Gesicht (oder siehe Ausdruck/Maske). | wie oben |
| Fernzugriff (SSH) | Winky ist nicht beteiligt, es gilt das Passwort bzw. der SSH-Schlüssel. | unverändert |
| Andere Benutzer am selben Rechner | Jeder hat nur sein eigenes Gesicht; einlernen geht nur mit dem eigenen Passwort. | geschützt |
| Schadprogramm, das unter deinem Konto läuft | Es kann sudo-Anfragen auslösen, bekommt aber ohne dein ✌ nichts. Details unten. | weitgehend geschützt, mit Restrisiko |

## Risiken in der Benutzung

Das hast du selbst in der Hand:

1. **Nicht gesperrter Rechner.** Winky schützt nur, was gesperrt ist. Gewöhn dir Super+L
   an und stell eine kurze automatische Sperre ein (in Winky unter Freigaben).
2. **Ähnliche Menschen im Haushalt.** Mach die Prüfung mit einer zweiten Person, am
   besten mit dem ähnlichsten Familienmitglied. Ist das Ergebnis knapp, stell Winky
   strenger ein oder nutz nur das Passwort. Zwillinge sollten Winky nicht nutzen.
3. **Strenge herabsetzen.** Eine niedrigere Schwelle macht Winky bequemer, aber andere
   Gesichter kommen leichter durch. In der Messung lag die eigene Person ohne Brille über
   0,69, meist zwischen 0,84 und 0,96; eine andere Person kam höchstens auf 0,24, weit unter
   der Vorgabe 0,65. Das ist eine Stichprobe, keine Statistik. Umso
   wichtiger ist die Prüfung mit einer zweiten Person (Punkt 2): Sie zeigt für deinen
   Haushalt, ob der Abstand reicht.
4. **Reflexhaftes ✌.** Die sudo-Bestätigung schützt nur, wenn du ✌ ausschließlich für
   Befehle zeigst, die du selbst gerade getippt hast. Erscheint eine Winky-Meldung, die du
   nicht erwartest: kein ✌, einfach ignorieren.
5. **Erzwungenes Entsperren.** Wer dich zwingen kann, in die Kamera zu schauen, öffnet
   die Bildschirmsperre. Gegen jemanden, der dir einfach den Rechner vors Gesicht hält,
   schalte „Entsperren nur mit ✌“ ein. Gegen echten Zwang hilft nur, Winky auszuschalten
   (Pause oder Deinstallieren).
6. **KeePassXC mit dem Gesicht.** Standardmäßig verlangt Winky für KeePassXC Gesicht
   **und** ✌, wie bei sudo. Schaltest du das ✌ ab, öffnet dein Gesicht allein die
   Passwort-Datenbank: Wer an deinem entsperrten Rechner auf „Entsperren“ klickt, während
   du davor sitzt, käme dann ohne dein Zutun hinein. Nach jedem Neustart von KeePassXC
   gilt wieder das Master-Passwort. Funktioniert nur ab KeePassXC 2.8.
7. **Datensicherungen.** Die Gesichtsdaten liegen unter `/var/lib/winky`. Sichert ein
   Backup-Programm das Systemverzeichnis (z. B. Timeshift), landen sie mit in der
   Sicherung; im TPM-Chip versiegelt (siehe 12) nur verschlüsselt.
8. **Veraltete Version.** Winky bringt seine Erkennungslaufzeit (ONNX Runtime) selbst
   mit. Deren Fehlerkorrekturen kommen nur mit einer neuen Winky-Version, nicht über die
   normalen Ubuntu-Updates.
9. **Anmeldung nach dem Start mit dem Gesicht** (ab Werk aus). Wer dein Gesicht täuschen
   kann, kommt dann auch nach einem Neustart hinein, nicht nur in die gesperrte Sitzung. Der
   Schlüsselbund bleibt zu, weil ihn nur das Passwort öffnet. Ohne verschlüsselte Festplatte
   ist das zusätzliche Risiko klein: Wer den Rechner hat, kann die Festplatte ohnehin lesen.
10. **Schlüsselbund-Passwort im TPM-Chip** (experimentell, ab Werk aus). Dein
    Anmeldepasswort liegt versiegelt auf dem Rechner und ist dort wiederherstellbar. Der
    TPM-Chip prüft nur den Secure-Boot-Zustand (PCR 7), nicht welches System läuft: Wer das
    Gerät in der Hand hat, kann es von einem USB-Stick mit Ubuntu oder einem verwandten Linux
    starten und das Passwort dort entsiegeln, ohne Secure Boot noch leichter. Damit hat er das
    Passwort selbst, das viele auch anderswo nutzen. Ein BIOS-Passwort, das den Start von USB
    sperrt, hilft. Winky gibt es nur direkt nach einer erkannten Gesichtsanmeldung heraus,
    prüft es vorher gegen `/etc/shadow` und verwirft es nach einer Passwortänderung.
11. **Administrator-Dialoge mit ✌.** Wirkt wie sudo mit ✌: Ein Schadprogramm unter deinem
    Konto kann so einen Dialog öffnen, und ein ✌ im falschen Moment gibt ihn frei, mit vollen
    Administratorrechten. Was angefragt wird, zeigt der Dialog selbst; zeig ✌ nur für Dialoge,
    die du selbst ausgelöst hast. Berechtigungsabfragen im Hintergrund erreichen Winky nie.
12. **Gesichtsdaten im TPM-Chip** (freiwillig, ab Werk aus). Auf der Festplatte liegen die
    Gesichtsdaten dann nur verschlüsselt (`systemd-creds`, Hostschlüssel und TPM-Chip, PCR 7).
    Das hilft, wenn die Festplatte in einem anderen Rechner oder von Windows auf demselben
    Rechner gelesen wird. Gegen einen USB-Stick mit Ubuntu oder einem verwandten Linux, der
    auf diesem Rechner gestartet wird, hilft es nicht (siehe 10); dagegen helfen nur eine
    verschlüsselte Festplatte oder ein BIOS-Passwort, das den Start von USB sperrt. Nach einem
    BIOS- oder Firmware-Update oder einer Änderung an Secure Boot lassen sich die Daten nicht
    mehr entsiegeln: Die Gesichtsentsperrung pausiert dann, bis du dein Gesicht neu aufnimmst,
    das Passwort geht weiter. Beim Einschalten wird die bisherige unverschlüsselte Datei
    gelöscht; auf SSDs lassen sich Reste nicht ausschließen.

## Risiken in der Technik selbst

Das lässt sich durch Bedienung nicht abstellen:

1. **Keine Lebenderkennung.** Winky nutzt nur die Infrarot-Kamera. Bildschirme und
   Handyfotos sind dort unsichtbar. Blinkt der Infrarot-Strahler, muss das Hell-Dunkel-Muster
   der Bilder passen; das ist eine Plausibilitätsprüfung gegen untergeschobene Bilder, keine
   Lebenderkennung. Ein im Infrarot sichtbarer Ausdruck oder eine Maske wurden nicht
   getestet und könnten durchkommen.
2. **Erkennungsfehler sind möglich.** Gesichtssuche (YuNet) und Gesichtsvergleich (SFace)
   sind kleine Modelle. Wie oft ein fremdes Gesicht durchgeht, ist nicht
   statistisch belegt, nur an wenigen Personen gemessen.
3. **Neuer Code in der Anmeldung.** Das PAM-Modul `pam_winky.so` steht in
   `common-auth` und läuft damit in jedem Anmeldeprogramm mit, als root. Es ist deshalb
   klein gehalten (nur libc und libpam), prüft zuerst eine feste Liste erlaubter Dienste
   (Sperrbildschirm `gdm-password`, `sudo`) und gibt bei allem Unerwarteten „nicht
   zuständig“ zurück; dann folgt die normale Passwortabfrage. Ein Programmierfehler in
   diesem Modul könnte trotzdem die Anmeldung stören oder im schlimmsten Fall ausnutzbar
   sein.
4. **Der Prüfdienst entscheidet.** Kamera, Erkennungsmodelle und Entscheidung laufen im
   Dienst `winky-matcher` als eigener Benutzer `_winky` ohne root-Rechte, ohne Netz und
   ohne Zugriff auf persönliche Ordner (systemd-Sandbox, `systemd-analyze security`: 1,0).
   Wer diesen Dienst übernimmt, könnte „erkannt“ melden und damit die Sperre öffnen und,
   falls eingeschaltet, sudo bestätigen. Angreifbar ist er nur über die Kamerabilder.
5. **Kamera-Attrappe.** Wer den Rechner öffnet und statt der eingebauten Kamera ein Gerät
   anschließt, das aufgezeichnete Infrarot-Bilder deines Gesichts abspielt, kann
   entsperren. Winky nutzt den festen Anschluss der eingebauten Kamera, ein einfach
   eingesteckter USB-Stick genügt dafür nicht.
6. **sudo mit ✌ und Schadprogramme.** Ein Programm unter deinem Konto kann sudo in einem
   eigenen, unsichtbaren Terminal starten. Dann geht die Kamera an und eine Meldung mit dem
   Befehl erscheint. Ohne dein ✌ passiert nichts. Abgesichert ist außerdem:
   - Zwei Anfragen zur selben Zeit werden beide abgebrochen. Ein Schadprogramm kann sich
     also nicht an deine eigene Bestätigung anhängen.
   - Nach drei unbestätigten Anfragen gilt zehn Minuten lang nur das Passwort.
   - Das ✌ muss neben dem erkannten Gesicht zu sehen sein, genau ein Gesicht im Bild.

   Ein Restrisiko bleibt: Startet ein Schadprogramm seine Anfrage direkt nach deiner eigenen,
   während deine Hand noch oben ist, könnte dein ✌ ihr gelten. Die Kamera braucht dafür
   aber erst eine knappe Sekunde zum Starten, und die Meldung zeigt den fremden Befehl.

   Zum Vergleich: Gegen ein Schadprogramm unter deinem Konto ist auch das sudo-Passwort
   schwach. Es kann zum Beispiel `sudo` in deiner Shell-Konfiguration umbiegen und das
   Passwort mitlesen. Mit ✌ gibt es kein Passwort zu stehlen, und die Meldung zeigt den
   tatsächlich ausgeführten Befehl.
7. **Hinweise lassen sich fälschen.** Jedes Programm kann Fenster und Desktop-Meldungen
   anzeigen, auch ein gefälschtes Winky-Hinweisfenster mit harmlosem Befehl. Das echte
   erscheint dann trotzdem. Im Zweifel: kein ✌.
8. **Sichtbarkeit der sudo-Befehle.** Der Befehl einer laufenden sudo-Anfrage steht für die
   Desktop-Meldung in `/run/winky/anfrage/<uid>.json` und im Systemprotokoll. Andere
   Benutzer desselben Rechners können ihn lesen. Über die Prozessliste sehen sie laufende
   sudo-Befehle ohnehin, und sudo protokolliert Befehle selbst auch.
9. **Biometrische Daten.** Gespeichert werden keine Bilder, sondern Merkmalsvektoren
   (je Person 30 Zahlenreihen mit je 128 Werten). Sie liegen nur für das System
   lesbar unter `/var/lib/winky/<uid>/` (root:_winky 0640). Auf einer unverschlüsselten
   Festplatte kann sie jeder mit physischem Zugriff lesen; im TPM-Chip versiegelt wird das
   schwerer, aber nicht unmöglich (Risiken in der Benutzung, 12). Aus solchen Vektoren lassen sich nach
   Forschungsergebnissen grob gesichtsähnliche Bilder zurückrechnen; als Ersatz für dein
   echtes Gesicht vor der Kamera taugen sie nicht direkt.
10. **Kamera an bei jedem Versuch.** Bei jedem Entsperrversuch und jeder sudo-Anfrage geht
    die Infrarot-Kamera für einige Sekunden an. Bilder werden nur im Speicher ausgewertet,
    nie gespeichert. Während der Einrichtung zeigt die App das Kamerabild an. Unabhängig von
    Winky kann normalerweise jedes Programm unter deinem Konto die Kameras einschalten; unter
    Erweitert lässt sich die Infrarot-Kamera Winky vorbehalten (eine udev-Regel nimmt dem
    angemeldeten Benutzer den Zugriff).
11. **Fremde Modelle.** Die Erkennungsmodelle stammen aus fremden Quellen (OpenCV Zoo,
    Google MediaPipe). Sie sind per Prüfsumme festgeschrieben, die Herkunft muss man aber
    diesen Quellen glauben.

## Eingebaute Schutzmaßnahmen

- **Freigabeliste im PAM-Modul:** nur Sperrbildschirm (erkannt am GDM-Merkmal für die
  Wiederanmeldung) und, wenn eingeschaltet, sudo. Kein Fernzugriff (`PAM_RHOST`), nicht für
  root, Notschalter `/etc/winky/disabled`, Deckel zu = sofort Passwort.
- **Feste Zeitgrenzen:** 3 Sekunden am Sperrbildschirm, höchstens 30 Sekunden für sudo,
  höchstens 9 Sekunden über Polkit. Kein `fork`,
  keine Abhängigkeit von Dateien im Home-Verzeichnis.
- **Passwort statt ✌:** Die erste Taste schaltet die Kamera aus; das Passwort erscheint nur
  als Sterne und geht an die normale Passwortprüfung. Das Terminal wird auf
  jedem Weg wiederhergestellt, auch bei Strg+C.
- **Abgeschotteter Prüfdienst:** startet nur bei Bedarf, prüft den Aufrufer über den
  Socket und logind (lokale, aktive, grafische Sitzung an seat0).
- **Root-eigene Daten:** Konfiguration, Vorlagen, Schalter und Freigaben werden ohne
  Verknüpfungen geöffnet und auf Besitzer, Rechte und Größe geprüft.
- **Infrarot-Kamera nur für Winky (freiwillig):** Eine udev-Regel nimmt dem angemeldeten
  Benutzer den Zugriff auf genau diese Kamera und gibt sie dem Prüfdienst. Abgelehnt, wenn ein
  anderer Knoten am selben Anschluss Farbbilder liefert; bei einem Fehlschlag bleibt der
  vorherige Zustand. Die App prüft, ob der Schutz wirkt. Deinstallieren gibt die Kamera wieder
  frei.
- **Gesichtsdaten im TPM-Chip (freiwillig):** für alle Benutzer oder für keinen versiegelt;
  scheitert es bei einem, bleibt der vorherige Zustand. Beim Start entsiegelt ein kleiner
  abgeschotteter Dienst die Daten in den Arbeitsspeicher (`/run/winky/vorlagen`); der
  Prüfdienst liest dann nur diese Kopie und greift nie auf die Festplatte zurück. Klappt das
  Entsiegeln nicht, bittet die App um eine neue Aufnahme.
- **Gesicht ergänzen nur mit dir im Bild:** Eine Ergänzung wird nur gespeichert, wenn Winky
  dich in der Aufnahme mindestens dreimal an der eingestellten Schwelle erkennt. Bilder, die
  mehr als 0,20 darunter liegen, werden verworfen; setzt sich zwischendurch jemand anderes vor
  die Kamera, landet er nicht in deinen Daten. Höchstens drei benannte Ergänzungen mit je bis
  zu 11 Bildern; die ursprüngliche Aufnahme bleibt immer erhalten.
- **Fehlversuche:** Nach fünf erkannten, aber fremden Gesichtern bleibt das Gesicht bis zur
  nächsten Passwortanmeldung gesperrt. sudo: nach drei unbestätigten Anfragen zehn Minuten.
- **Schrittweise Freigabe:** Einschalten erst nach erfolgreichem Test; gesperrt, wenn die
  Prüfung mit einer zweiten Person zu knapp war. sudo mit ✌ zusätzlich nur mit
  Administratorpasswort und eigenem bestandenem ✌-Test je Person.
- **Rückbau:** Abschalten über `pam-auth-update`; vor jedem Einschalten wird
  `common-auth` gesichert. Deinstallieren entfernt alles samt Gesichtsdaten.
- **Tests:** Komponenten, PAM mit echtem libpam, die App mit einer Attrappe sowie das
  ganze Paket in Wegwerf-Systemen. Siehe [ENTWICKLUNG.md](ENTWICKLUNG.md).

## Empfehlungen

1. Festplatte verschlüsseln. Winky schützt nur die laufende Sitzung.
2. Prüfung mit einer zweiten Person machen, mit dem ähnlichsten Menschen im Haushalt.
3. Die Strenge nicht unter die Vorgabe senken.
4. sudo mit ✌ nur einschalten, wenn du die Meldungen ernst nimmst.
5. Bildschirm beim Weggehen sperren und eine kurze automatische Sperre einstellen (Winky:
   Freigaben → Automatisch sperren).
6. Winky-Updates einspielen.

## Datenschutz

- Kein Netzwerkzugriff, keine Telemetrie. Der Prüfdienst läuft ohne Netz.
- Gespeichert werden je Person: Merkmalsvektoren, Zeitpunkt und Ergebnis der Tests (für
  die App) und der bestandene ✌-Test. Keine Bilder.
- Das Systemprotokoll enthält je Versuch Zeitpunkt, Ergebnis, Ähnlichkeitswert und bei sudo
  die Befehlszeile.
- Deinstallieren löscht die Gesichtsdaten aller Benutzer.

## Nutzung auf eigenes Risiko

Die Nutzung von Winky erfolgt auf eigenes Risiko. Diese Seite beschreibt die bekannten Grenzen
nach bestem Wissen; vollständig ist eine solche Liste nie.

## Fehler melden

Winky wird so bereitgestellt, wie es ist; Pflege und Korrekturen sind nicht zugesagt. Fehler,
auch Sicherheitsprobleme, gern als Issue auf der
[Projektseite](https://github.com/DieSchatten/winky/issues), mit Version, Distribution und
einer Beschreibung, wie sich der Fehler zeigen lässt. Eine vertrauliche Meldestelle gibt es
nicht. Nach der MIT-Lizenz darf jeder Winky selbst weiterentwickeln.
