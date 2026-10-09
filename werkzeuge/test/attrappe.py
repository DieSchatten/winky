#!/usr/bin/env python3
"""Attrappe des Messwerkzeugs für Oberflächentests ohne Kamera: spricht das Vorschau-Protokoll
von bau/winky-messung (BILD/STATUS auf stdout), schreibt CSV- und Vorlagendateien im echten Format.
"""

import json
import os
import random
import signal
import sys
import time

stop = False


def beenden(*_):
    global stop
    stop = True


signal.signal(signal.SIGTERM, beenden)
signal.signal(signal.SIGINT, beenden)

KOPF = ("name,bild,t_ms,seq,hell,beleuchtet,blinkt,gesichter,det_conf,x1,y1,x2,y2,breite,"
        "punkte_min,neigung,drehung,augenabstand,gesicht_hell,gesicht_sat,gesicht_dunkel,"
        "brauchbar,grund,det_ms,emb_ms,wert_top3,wert_max,wert2_top3,wert2_max")


def arg(name, vorgabe=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a else vorgabe


def bild(i, gesicht=True):
    w, h = 320, 180
    zeile = bytearray()
    for y in range(h):
        for x in range(w):
            v = (x // 4 + y // 4 + i * 3) % 90 + 20
            zeile += bytes((v, v, v))
    if gesicht:
        x1, y1 = 120 + int(10 * (i % 6)), 50
        for x in range(x1, x1 + 70):
            for y in (y1, y1 + 1, y1 + 80, y1 + 81):
                p = (y * w + x) * 3
                zeile[p:p + 3] = bytes((60, 220, 90))
        for y in range(y1, y1 + 82):
            for x in (x1, x1 + 1, x1 + 68, x1 + 69):
                p = (y * w + x) * 3
                zeile[p:p + 3] = bytes((60, 220, 90))
    sys.stdout.buffer.write(f"BILD {w} {h} {len(zeile)}\n".encode())
    sys.stdout.buffer.write(zeile)
    sys.stdout.flush()


def status(d):
    sys.stdout.write("STATUS " + json.dumps(d) + "\n")
    sys.stdout.flush()


def main():
    befehl = sys.argv[1]
    dauer = float(arg("--dauer", "10"))
    time.sleep(0.6)  # Containerstart nachahmen
    t0 = time.monotonic()
    i = 0
    zeilen = []
    haende = []
    while time.monotonic() - t0 < dauer:
        if stop:
            print("Abgebrochen.", file=sys.stderr)
            return 3
        i += 1
        t = time.monotonic() - t0
        wert = round(random.uniform(0.85, 0.95), 4)
        bild(i)
        modus = {"vorschau": "vorschau", "einlernen": "einlernen"}.get(befehl, "messen")
        if befehl == "hand":
            hoch = 3.2 <= t % 4 < 4.4 if t > 3 else False   # alle 4 s kurz ein Victory
            haende.append((int(time.time() * 1000), hoch))
            status({"modus": "hand", "t": round(t, 1), "dauer": dauer, "gesicht": True,
                    "hand": hoch, "geste": "Victory" if hoch else None,
                    "sicherheit": 0.92 if hoch else None, "victory": 0.92 if hoch else None,
                    "presence": 0.98 if hoch else None, "daumen_hoch": None,
                    "regel_hoch": False, "finger_nase": None})
        else:
            status({"modus": modus, "t": round(t, 1), "dauer": dauer, "gesicht": True,
                    "grund": "ok", "beleuchtet": i, "brauchbar": i, "bilder": 2 * i,
                    "wert": wert, "wert2": wert - 0.03})
        zeilen.append(f"{arg('--name', 'x')},{2 * i - 1},{t * 1000 + 160:.1f},{2 * i},70.0,1,1,1,"
                      f"0.850,240,100,380,262,140.0,0.700,1.0,0.500,66.0,160.0,0.0010,0.0,1,ok,"
                      f"37.0,4.5,{wert:.4f},{wert + 0.01:.4f},{wert - 0.03:.4f},{wert - 0.02:.4f}")
        zeilen.append(f"{arg('--name', 'x')},{2 * i},{t * 1000 + 227:.1f},{2 * i + 1},0.0,0,1"
                      + "," * 22)
        time.sleep(0.133)

    if befehl == "hand" and arg("--csv"):
        kopf = ("name,bild,unix_ms,t_ms,seq,hell,beleuchtet,gesichter,augenabstand,hand,palm,"
                "presence,verfolgt,rechts,p_keine,p_faust,p_offen,p_zeigen,p_runter,p_hoch,"
                "p_victory,p_love,regel_hoch,daumen_winkel,daumen_oben,daumen_lang,streck_zeige,"
                "streck_mittel,streck_ring,streck_klein,finger_nase,det_ms,palm_ms,hand_ms,geste_ms")
        with open(arg("--csv"), "w") as f:
            f.write(f"# name={arg('--name')}\n# art=hand\n{kopf}\n")
            for k, (unix_ms, hoch) in enumerate(haende):
                if hoch:
                    f.write(f"{arg('--name')},{k},{unix_ms},{k * 133},{k},70,1,1,62,1,0.9,0.98,1,0.9,"
                            "0.02,0.01,0.01,0.01,0.01,0.01,0.92,0.01,0,10,0.3,0.8,1.1,1.1,1.1,1.1,"
                            "3.5,30,5,10,1\n")
                else:
                    f.write(f"{arg('--name')},{k},{unix_ms},{k * 133},{k},70,1,1,62,0,0.1"
                            + "," * 21 + "30,5,0,0\n")
        return 0
    if befehl == "einlernen":
        pfad = arg("--vorlagen")
        for p in (pfad, pfad + ".mbf"):
            with open(p, "wb") as f:
                f.write(b"WINKYM" + os.urandom(64))
        print(f"Gespeichert: 30 Vorlagen (Attrappe), {i} brauchbare Bilder", file=sys.stderr)
    elif befehl == "messen" and arg("--csv"):
        with open(arg("--csv"), "w") as f:
            f.write(f"# name={arg('--name')}\n# vorlagen_id={arg('--vorlagen-id', '')}\n"
                    f"# kamera_start_ms=120\n# modelle_laden_ms=95\n{KOPF}\n")
            f.write("\n".join(zeilen) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
