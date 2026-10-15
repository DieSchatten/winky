#!/usr/bin/env python3
"""Logik des Verwaltungshelfers ohne root: Gesicht ergänzen (benannte Gruppen)."""

import importlib.machinery
import importlib.util
import math
import random
import sys
from pathlib import Path

PROJEKT = Path(__file__).resolve().parents[2]
lader = importlib.machinery.SourceFileLoader("verwalten", str(PROJEKT / "src/verwalten/winky-verwalten"))
v = importlib.util.module_from_spec(importlib.util.spec_from_loader("verwalten", lader))
lader.exec_module(v)

F = 0


def pruefe(bedingung, name):
    global F
    print(("ok      " if bedingung else "FEHLER  ") + name)
    F += 0 if bedingung else 1


def norm(x):
    n = math.sqrt(sum(a * a for a in x))
    return [a / n for a in x]


def gesicht(mitte, streuung, n, zufall):
    """n Merkmale um eine Mitte; streuung bestimmt die Ähnlichkeit untereinander."""
    return [norm([m + zufall.gauss(0, streuung) for m in mitte]) for _ in range(n)]


z = random.Random(7)
ich = norm([z.gauss(0, 1) for _ in range(128)])
fremd = norm([z.gauss(0, 1) for _ in range(128)])
# Mit Brille: dasselbe Gesicht, aber merklich verschoben
brille = norm([a + 0.12 * z.gauss(0, 1) for a in ich])
alt = gesicht(ich, 0.04, 30, z)
S = 0.65

w_ich = v.aehnlichkeit(gesicht(ich, 0.04, 1, z)[0], alt)
w_brille = v.aehnlichkeit(gesicht(brille, 0.04, 1, z)[0], alt)
w_fremd = v.aehnlichkeit(gesicht(fremd, 0.04, 1, z)[0], alt)
pruefe(w_ich > S and S - 0.20 <= w_brille < S and w_fremd < 0.3,
       f"Testdaten: ich {w_ich:.2f}, mit Brille {w_brille:.2f}, fremd {w_fremd:.2f}")

# 1. Stark verändert und nie sicher erkannt: nichts wird übernommen (nicht nachweisbar ich)
stark = norm([a + 0.16 * z.gauss(0, 1) for a in ich])
auswahl, belege = v.ergaenzung_auswaehlen(alt, gesicht(stark, 0.04, 20, z), S)
pruefe(auswahl is None and belege < 3, f"ohne erkannte Bilder wird nichts ergänzt ({belege} Belege)")

# 2. Erst ohne, dann mit Brille: höchstens 11 Bilder kommen dazu, danach wird die Brille erkannt
auswahl, belege = v.ergaenzung_auswaehlen(alt, gesicht(ich, 0.04, 8, z) + gesicht(brille, 0.04, 20, z), S)
pruefe(auswahl is not None and len(auswahl) == 11 and belege >= 3,
       f"ohne, dann mit Brille: {len(auswahl or [])} Bilder, {belege} Belege")
pruefe(v.aehnlichkeit(gesicht(brille, 0.04, 1, z)[0], alt + auswahl) >= S,
       "danach wird das Gesicht mit Brille erkannt")

# 3. Erst ich, dann setzt sich eine andere Person davor: sie wird nicht übernommen
auswahl2, _ = v.ergaenzung_auswaehlen(alt, gesicht(ich, 0.04, 6, z) + gesicht(fremd, 0.04, 20, z), S)
pruefe(auswahl2 is not None and len(auswahl2) == 6, f"fremdes Gesicht wird verworfen ({len(auswahl2)} übernommen)")
pruefe(v.aehnlichkeit(gesicht(fremd, 0.04, 1, z)[0], alt + auswahl2) < 0.3,
       "die andere Person bleibt danach fremd")

# 4. Drei benannte Ergänzungen: höchstens 63 Vorlagen, eine mittlere lässt sich gezielt löschen
g1, g2, g3 = (gesicht(ich, 0.04, 11, z) for _ in range(3))
voll = alt + g1 + g2 + g3
status = {"vorlagen_basis": 30, "ergaenzungen": [
    {"id": 11, "name": "Mit Brille", "anzahl": 11}, {"id": 12, "name": "Licht", "anzahl": 11},
    {"id": 13, "name": "Bart", "anzahl": 11}]}
basis, liste = v.gruppen(status, len(voll))
rest, bleibt = v.zusammensetzen(voll, basis, liste, 12)
pruefe(len(voll) <= v.VORLAGEN_MAX and rest == alt + g1 + g3 and [e["id"] for e in bleibt] == [11, 13],
       f"drei Ergänzungen ({len(voll)} Vorlagen), „Licht“ gelöscht, die anderen unverändert")

# 5. Ältere Stände ohne Namen: alles nach der Basis ist eine Ergänzung, die ersten 30 bleiben
basis, liste = v.gruppen({}, 40)
pruefe(basis == 30 and len(liste) == 1 and liste[0]["anzahl"] == 10 and liste[0]["name"] == "",
       "ohne gespeicherte Gruppen: eine namenlose Ergänzung nach den ersten 30")
basis, liste = v.gruppen({"vorlagen_basis": 30, "ergaenzungen": [{"id": 1, "anzahl": 5}]}, 40)
pruefe(len(liste) == 1 and liste[0]["anzahl"] == 10, "unstimmige Gruppenliste wird nicht geglaubt")

# 6. Gleichmäßige Auswahl
pruefe(v.gleichmaessig(list(range(10)), 4) == [0, 3, 6, 9] and v.gleichmaessig([1, 2], 5) == [1, 2]
       and v.gleichmaessig([1, 2, 3], 0) == [], "gleichmäßige Auswahl")

print(f"== Verwaltungshelfer: {10 - F}/10 bestanden")
sys.exit(1 if F else 0)
