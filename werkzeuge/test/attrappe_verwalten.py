#!/usr/bin/env python3
"""Attrappe von winky-verwalten / winky-gesicht für Oberflächentests: ohne root und Kamera,
schreibt nach WINKY_TESTWURZEL statt ins System, gleiches Protokoll.

Aufruf: attrappe_verwalten.py --rolle gesicht|verwalten BEFEHL [WERT]
Umgebung: WINKY_ATTRAPPE_PASSWORT=abbrechen (abgebrochene Passwortabfrage),
WINKY_ATTRAPPE_FREMD=WERT (höchster Wert der Gegenprobe), WINKY_ATTRAPPE_BILD=DATEI (Kamerabild
aus werkzeuge/bildschirmfotos/illustration.py), WINKY_ATTRAPPE_DAUER=SEKUNDEN (Einlernen, Testen).
"""

import json
import os
import select
import sys
import time
from pathlib import Path

W = Path(os.environ["WINKY_TESTWURZEL"])
UID = os.getuid()
GESICHT_BEFEHLE = {"status", "kameras", "einlernen", "testen", "gegenprobe", "geste-testen",
                   "entfernen"}
KAMERA = {"geraet": "/dev/video2", "pfad": "/dev/v4l/by-path/test-usb-0:1:1.2-video-index0",
          "name": "Test-Kamera: IR Camera", "breite": 640, "hoehe": 360, "blinkt": True,
          "hell": 74.9, "dunkel": 0.0}


def p(pfad):
    ziel = W / pfad.lstrip("/")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    return ziel


def aus(art, d):
    print(f"{art} {json.dumps(d)}", flush=True)


def fertig(ok, **d):
    d["ok"] = ok
    aus("ERGEBNIS", d)
    sys.exit(0 if ok else 1)


def abgebrochen():
    r, _, _ = select.select([sys.stdin], [], [], 0)
    return bool(r) and not os.read(sys.stdin.fileno(), 10)


def kamerabild():
    datei = os.environ.get("WINKY_ATTRAPPE_BILD")
    if not datei:
        return 320, 180, bytes([90]) * (320 * 180 * 3)
    roh = Path(datei).read_bytes()
    kopf, daten = roh.split(b"\n", 1)
    b, h = (int(t) for t in kopf.split())
    return b, h, daten


def strom(modus, sekunden, wert=0.9, geste=False):
    sekunden = float(os.environ.get("WINKY_ATTRAPPE_DAUER", sekunden))
    b, h, bild = kamerabild()
    t0 = time.monotonic()
    i = 0
    while time.monotonic() - t0 < sekunden:
        if abgebrochen():
            fertig(False, fehler="abgebrochen", abgebrochen=True)
        i += 1
        st = {"modus": modus, "t": round(time.monotonic() - t0, 1), "dauer": sekunden,
              "gesicht": True, "grund": "ok", "gesammelt": i, "wert": wert}
        if geste:
            st.update(modus="geste", hand=i > 3, geste="Victory" if i > 3 else None,
                      zeichen=i > 3, gesichter=1, gesicht_erkannt=i > 1)
        aus("STATUS", st)
        sys.stdout.buffer.write(f"BILD {b} {h} {len(bild)}\n".encode() + bild)
        sys.stdout.buffer.flush()
        time.sleep(0.13)


def konfig():
    try:
        return p("/etc/winky/winky.conf").read_text()
    except FileNotFoundError:
        return "schwelle = 0.65\nkamera =\n"


def _schluessel(zeile):
    return zeile.split("=", 1)[0].strip() if "=" in zeile else None


def setze(schluessel, wert):
    zeilen = [z for z in konfig().splitlines() if _schluessel(z) != schluessel]
    zeilen.append(f"{schluessel} = {wert}")
    p("/etc/winky/winky.conf").write_text("\n".join(zeilen) + "\n")


def wert_von(schluessel):
    for z in konfig().splitlines():
        if _schluessel(z) == schluessel:
            return z.split("=", 1)[1].strip()
    return ""


def lese_status():
    try:
        return json.loads(p(f"/var/lib/winky/status/{UID}.json").read_text())
    except (FileNotFoundError, ValueError):
        return {}


def schreibe_status(d):
    p(f"/var/lib/winky/status/{UID}.json").write_text(json.dumps(d))


def main():
    args = sys.argv[1:]
    rolle = "verwalten"
    if args[:1] == ["--rolle"]:
        rolle, args = args[1], args[2:]
    befehl = args[0]
    if os.environ.get("WINKY_ATTRAPPE_PASSWORT") == "abbrechen":
        sys.exit(126)  # wie pkexec, wenn die Passwortabfrage abgebrochen wird
    if rolle == "gesicht" and befehl not in GESICHT_BEFEHLE:
        fertig(False, fehler="Dafür ist das Administratorpasswort nötig (winky-verwalten)")
    schwelle = float(wert_von("schwelle") or 0.65)

    if befehl == "kameras":
        fertig(True, kameras=[KAMERA], empfohlen=KAMERA["pfad"])
    if befehl == "kamera":
        if args[1] not in ("auto", KAMERA["pfad"], KAMERA["geraet"]):
            fertig(False, fehler="Keine passende IR-Kamera gefunden")
        setze("kamera", KAMERA["pfad"])
        setze("blinkpruefung", "ja")
        fertig(True, kamera=KAMERA)
    if befehl == "einlernen":
        if not wert_von("kamera"):
            fertig(False, fehler="Noch keine Kamera eingerichtet")
        strom("einlernen", 1.5)
        schreibe_status({"vorlagen": 30, "eingelernt": int(time.time())})
        fertig(True, vorlagen=30)
    if befehl == "testen":
        strom("testen", 1.0)
        st = lese_status()
        st.update(test_ok=int(time.time()) + 1, test_wert=0.91)
        schreibe_status(st)
        v = p("/verlauf.json")
        alt = json.loads(v.read_text()) if v.exists() else []
        v.write_text(json.dumps([{"zeit": time.time(), "status": "treffer", "wert": 0.91,
                                  "dauer_ms": 420, "grund": ""}] + alt))
        fertig(True, status="treffer", wert=0.91, dauer_ms=420)
    if befehl == "gegenprobe":
        fremd = float(os.environ.get("WINKY_ATTRAPPE_FREMD", "0.31"))
        for rest in (3, 2, 1):
            aus("STATUS", {"modus": "countdown", "rest": rest})
            time.sleep(0.05)
        strom("testen", 1.0, wert=fremd)
        st = lese_status()
        ok = fremd < schwelle - 0.10
        st.update(gegenprobe_zeit=int(time.time()), gegenprobe_wert=fremd, gegenprobe_ok=ok)
        schreibe_status(st)
        if not ok:
            fertig(False, fehler="Die andere Person kam zu nah an die Schwelle", wert=fremd,
                   status="kein_treffer")
        fertig(True, status="kein_treffer", wert=fremd)
    if befehl == "geste-testen":
        strom("geste", 1.2, geste=True)
        st = lese_status()
        st.update(geste_ok=int(time.time()) + 1)
        schreibe_status(st)
        fertig(True, status="treffer", wert=0.9, dauer_ms=1100)
    if befehl == "sudo":
        if args[1] == "an":
            if "pam_winky" not in p("/etc/pam.d/common-auth").read_text():
                fertig(False, fehler="Zuerst die Gesichtsentsperrung am Sperrbildschirm einschalten")
            if not lese_status().get("geste_ok"):
                fertig(False, fehler="Zuerst Gesicht und ✌ erfolgreich testen")
            setze("sudo", "ja")
            p("/etc/winky/sudo-ein").write_text("an\n")
        else:
            setze("sudo", "nein")
            p("/etc/winky/sudo-ein").unlink(missing_ok=True)
        fertig(True)
    if befehl == "anmeldung":
        if args[1] == "an":
            if "pam_winky" not in p("/etc/pam.d/common-auth").read_text():
                fertig(False, fehler="Zuerst die Gesichtsentsperrung am Sperrbildschirm einschalten")
            p("/etc/winky/anmeldung-ein").write_text("an\n")
        else:
            p("/etc/winky/anmeldung-ein").unlink(missing_ok=True)
        fertig(True)
    if befehl in ("freigabe-an", "freigabe-aus"):
        gruppen = [g for g in (wert_von("freigaben") or "").split(",") if g and g != args[1]]
        if befehl == "freigabe-an":
            if "pam_winky" not in p("/etc/pam.d/common-auth").read_text():
                fertig(False, fehler="Zuerst die Gesichtsentsperrung am Sperrbildschirm einschalten")
            if not lese_status().get("geste_ok"):
                fertig(False, fehler="Zuerst Gesicht und ✌ erfolgreich testen")
            gruppen.append(args[1])
        setze("freigaben", ",".join(gruppen))
        fertig(True)
    if befehl == "schwelle":
        w = round(float(args[1]), 2)
        if not 0.40 <= w <= 0.95:
            fertig(False, fehler="Schwelle muss zwischen 0,40 und 0,95 liegen")
        setze("schwelle", f"{w:.2f}")
        fertig(True, schwelle=w)
    if befehl == "aktivieren":
        st = lese_status()
        if not wert_von("kamera"):
            fertig(False, fehler="Zuerst die Kamera einrichten")
        if not st.get("vorlagen"):
            fertig(False, fehler="Zuerst das Gesicht einlernen")
        if st.get("test_ok", 0) < st.get("eingelernt", 0) or not st.get("test_ok"):
            fertig(False, fehler="Zuerst die Erkennung erfolgreich testen")
        p("/etc/pam.d/common-auth").write_text(
            "auth [success=2 default=ignore] pam_winky.so services=gdm-password\n")
        fertig(True)
    if befehl == "keepassxc":
        if args[1] in ("geste-an", "geste-aus"):
            setze("keepassxc_geste", "ja" if args[1] == "geste-an" else "nein")
            fertig(True)
        if args[1] == "an":
            st = lese_status()
            if not st.get("test_ok"):
                fertig(False, fehler="Zuerst die Erkennung erfolgreich testen")
            if wert_von("keepassxc_geste") != "nein" and not st.get("geste_ok"):
                fertig(False, fehler="Zuerst Gesicht und ✌ testen")
            setze("keepassxc", "ja")
        else:
            setze("keepassxc", "nein")
        fertig(True)
    if befehl == "deaktivieren":
        p("/etc/winky/sudo-ein").unlink(missing_ok=True)
        p("/etc/winky/anmeldung-ein").unlink(missing_ok=True)
        p("/etc/pam.d/common-auth").write_text("auth [success=1 default=ignore] pam_unix.so\n")
        fertig(True)
    if befehl == "pausieren":
        p("/etc/winky/disabled").write_text("x")
        fertig(True)
    if befehl == "fortsetzen":
        p("/etc/winky/disabled").unlink(missing_ok=True)
        fertig(True)
    if befehl == "entfernen":
        p(f"/var/lib/winky/status/{UID}.json").unlink(missing_ok=True)
        fertig(True)
    fertig(False, fehler="unbekannter Befehl")


if __name__ == "__main__":
    main()
