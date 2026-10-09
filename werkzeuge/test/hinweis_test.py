#!/usr/bin/env python3
"""Test des Hinweisprogramms (src/hinweis/winky-hinweis) ohne Prüfdienst und ohne root.

Prüft, welcher Stand der Anfragedatei zu welchem Hinweis führt; notify-send und das Fenster
werden nur mitgeschrieben, mit DISPLAY wird das Fenster zusätzlich unsichtbar aufgebaut.

Aufruf: python3 werkzeuge/test/hinweis_test.py
"""

import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ORDNER = tempfile.mkdtemp(prefix="winky-hinweis-")
os.environ["WINKY_ANFRAGE_ORDNER"] = ORDNER
os.environ["LANGUAGE"] = "de"   # die Prüfungen vergleichen deutsche Texte (bau/locale)
PROJEKT = Path(__file__).resolve().parents[2]
lader = importlib.machinery.SourceFileLoader("hinweis", str(PROJEKT / "src/hinweis/winky-hinweis"))
spec = importlib.util.spec_from_loader("hinweis", lader)
h = importlib.util.module_from_spec(spec)
lader.exec_module(h)

FEHLER = []


def pruefe(bed, text):
    print(("ok    " if bed else "FEHLER") + "  " + text, flush=True)
    if not bed:
        FEHLER.append(text)


class FensterAttrappe:
    def __init__(self, sichtbar=True):
        self.sichtbar = sichtbar
        self.ereignisse = []

    def zeigen(self, zweck, befehl, beginn):
        self.ereignisse.append(("zeigen", zweck, befehl))
        return self.sichtbar

    def bestaetigt(self):
        self.ereignisse.append(("bestaetigt",))
        return self.sichtbar

    def schliessen(self):
        self.ereignisse.append(("schliessen",))


meldungen = []


class Ergebnis:
    stdout = "7\n"


h.subprocess.run = lambda args, **kw: (meldungen.append(args), Ergebnis())[1]


def anfrage(stand, zweck="sudo", befehl="sudo apt update", alter=0):
    daten = {"zeit": int(time.time()) - alter, "stand": stand, "befehl": befehl,
             "terminal": "/dev/pts/1" if zweck == "sudo" else "", "zweck": zweck}
    Path(ORDNER, f"{os.getuid()}.json").write_text(json.dumps(daten))


def lauf(hinweis, *args, **kw):
    meldungen.clear()
    hinweis.fenster.ereignisse.clear()
    anfrage(*args, **kw)
    hinweis._lesen()
    return hinweis.fenster.ereignisse, list(meldungen)


hinweis = h.Hinweis()
hinweis.fenster = FensterAttrappe()

fenster, melde = lauf(hinweis, "wartet", "keepassxc", "KeePassXC entsperren", alter=1)
pruefe(fenster == [("zeigen", "keepassxc", "")] and not melde,
       "KeePassXC wartet: großes Fenster, keine zusätzliche Benachrichtigung")
fenster, melde = lauf(hinweis, "bestaetigt", "keepassxc", "KeePassXC entsperren", alter=0)
pruefe(fenster == [("bestaetigt",)] and not melde, "bestätigt: ✓ im Fenster")
fenster, melde = lauf(hinweis, "wartet", alter=3)
pruefe(fenster == [("zeigen", "sudo", "sudo apt update")], "sudo wartet: Fenster nennt den Befehl")
fenster, melde = lauf(hinweis, "nicht_bestaetigt", alter=2)
pruefe(("schliessen",) in fenster and melde and "nicht per ✌" in melde[0][-2],
       "nicht bestätigt: Fenster zu, Benachrichtigung")
fenster, melde = lauf(hinweis, "abgebrochen", "keepassxc", alter=4)
pruefe(melde and "--urgency=critical" in melde[0] and "abgebrochen" in melde[0][-2],
       "Abbruch: dringende Benachrichtigung")
fenster, melde = lauf(hinweis, "wartet", alter=300)
pruefe(not fenster and not melde, "alte Anfragen (etwa nach dem Anmelden) werden nicht gemeldet")

hinweis.fenster = FensterAttrappe(sichtbar=False)
fenster, melde = lauf(hinweis, "wartet", "keepassxc", alter=5)
pruefe(melde and "KeePassXC wartet auf ✌" in melde[0], "ohne X-Anzeige: Benachrichtigung statt Fenster")

if os.environ.get("DISPLAY"):
    f = h.Fenster()
    if f.gtk:
        karte = f.inhalt("keepassxc", "")
        pruefe(f.zeichen.get_label().startswith("✌") and f.titel.get_label() ==
               "KeePassXC entsperren", "Fensterinhalt: großes ✌ und Titel")
        pruefe(not f.fenster, "nichts wird angezeigt, solange keine Anfrage da ist")

print(f"\n{len(FEHLER)} Fehler")
sys.exit(1 if FEHLER else 0)
