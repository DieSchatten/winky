#!/usr/bin/env python3
"""Ablauftest der Hand-Messseite mit der Attrappe (ohne Kamera).

Aufruf (braucht ein GTK-Display, z. B. Broadway):
  WINKY_ATTRAPPE=1 WINKY_MESSUNGEN=/tmp/m GDK_BACKEND=broadway BROADWAY_DISPLAY=:19 \\
    python3 werkzeuge/test/hand_gui_test.py
"""
import json
import os
import sys
import time
from pathlib import Path

assert os.environ.get("WINKY_ATTRAPPE") == "1", "nur mit Attrappe ausführen"
P = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(P / "werkzeuge/kalibrierung"))
sys.path.insert(0, str(P / "src/app"))
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib  # noqa: E402

import hand  # noqa: E402
import kalibrierung  # noqa: E402

for s in hand.SCHRITTE:
    s["dauer"], s["countdown"] = 6, 1
    if s["signale"]:
        s["signale"], s["signal_dauer"] = [1, 3.5], 1.5
F, GEPRUEFT = [], []


def pruefe(b, t):
    GEPRUEFT.append(t)
    print(("ok    " if b else "FEHLER") + "  " + t, flush=True)
    b or F.append(t)


def warte(sek, bed=lambda: False):
    ctx = GLib.MainContext.default()
    ende = time.monotonic() + sek
    while time.monotonic() < ende and not bed():
        ctx.iteration(False)
        time.sleep(0.01)
    return bed()


def los(app):
    f = kalibrierung.Fenster(app)
    f.set_default_size(1180, 860)
    f.present()
    warte(1)
    h = f.hand
    pruefe(f.stapel.get_visible_child_name() == "erkennung", "Erkennung ist die erste Seite")
    namen = []
    kind = f.stapel.get_first_child()
    while kind is not None:
        namen.append(f.stapel.get_page(kind).get_name())
        kind = kind.get_next_sibling()
    pruefe(namen == ["erkennung", "hand"], "nur noch Erkennung und Handzeichen ✌, kein Zwinkern")
    f.stapel.set_visible_child_name("hand")
    warte(0.3)
    pruefe(h.schritt_aktuell["id"] == "bestaetigen", "erster Schritt: Bestätigen wie später")
    gezeigt, bestaetigt = [], []
    alt = h._signal_zeigen

    def merke(*a):
        r = alt(*a)
        gezeigt.append(h.vorschau.label.get_label())
        return r
    h._signal_zeigen = merke
    h.starten()
    warte(15, lambda: (bestaetigt.append(1) if h.vorschau.label.get_label() == hand.ERKANNT and
                       h.vorschau.label.get_visible() else None,
                       h.lauf is None and h.countdown_id is None and h.csv("bestaetigen").exists())[1])
    pruefe(gezeigt == ["Victory ✌", "Victory ✌"], f"Aufforderungen „Victory ✌“ ({gezeigt})")
    pruefe(len(bestaetigt) > 0, "„✓ Erkannt“ erscheint, sobald die Regel greift")
    pruefe(len(json.loads(h.signal_datei("bestaetigen").read_text())) == 2, "Zeitpunkte gespeichert")
    pruefe("Bildern mit Hand" in h.ergebnis.get_label(), "Ergebnistext nennt Bilder mit Hand")
    warte(2)
    pruefe(h.schritt_aktuell["id"] == "tippen", "weiter zum nächsten offenen Schritt")
    # Tippen: Satz und Eingabefeld, Kamerabild ausgeblendet, Fokus im Feld
    h._liste_aufbauen(auswahl="tippen")
    warte(0.2)
    pruefe(h.s_tippkarte.get_visible() and "sudo" in h.s_lesetext.get_label(), "Tippsatz und Eingabefeld sichtbar")
    h.starten()
    warte(5, lambda: h.lauf is not None and h.start_unix is not None)
    warte(0.5)
    pruefe(not h.vorschau.get_visible() and h.s_tippfeld.has_focus(), "beim Tippen Kamerabild aus, Fokus im Feld")
    warte(12, lambda: h.lauf is None)
    pruefe(h.vorschau.get_visible() and h.csv("tippen").exists(), "nach dem Tippen gespeichert, Kamerabild wieder da")
    # Alltag: Aufgaben wechseln
    h._liste_aufbauen(auswahl="alltag")
    warte(0.2)
    h.starten()
    gesehen = set()
    warte(14, lambda: (gesehen.add(h.vorschau.label.get_label()), h.lauf is None and h.start_unix is not None)[1])
    pruefe(len(gesehen & set(hand.ALLTAG)) >= 7, f"Alltagsaufgaben erscheinen ({len(gesehen & set(hand.ALLTAG))})")
    # Rest durchlaufen und auswerten
    for s in hand.SCHRITTE:
        if s["optional"] or h.csv(s["id"]).exists():
            continue
        h._liste_aufbauen(auswahl=s["id"])
        warte(0.1)
        h.starten()
        warte(15, lambda: h.lauf is None and h.countdown_id is None and h.csv(s["id"]).exists())
    h._liste_aufbauen(auswahl="auswertung")
    warte(0.5)
    txt = h.a_text.get_buffer().props.text
    pruefe("Victory" in txt and "Daumen hoch" not in txt, "Auswertung zeigt das Victory-Verfahren")
    f.close()
    app.quit()
    return False


app = Adw.Application(application_id="io.github.dieschatten.HandTest")
app.connect("activate", lambda a: GLib.idle_add(lambda: los(a) and False))
app.run([])
if not GEPRUEFT:
    F.append("Oberfläche ist nicht gestartet")
print(f"\n{len(F)} Fehler")
sys.exit(1 if F else 0)
