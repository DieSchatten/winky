#!/usr/bin/env python3
"""Logik des Verwaltungshelfers ohne root: Gesicht ergänzen (Vorlagen zusammenführen)."""

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
neu, n, belege = v.vorlagen_ergaenzen(alt, 30, gesicht(stark, 0.04, 20, z), S)
pruefe(neu is None and belege < 3, f"ohne erkannte Bilder wird nichts ergänzt ({belege} Belege)")

# 2. Erst ohne, dann mit Brille: beides kommt dazu, die Einlern-Vorlagen bleiben vorn
aufnahme = gesicht(ich, 0.04, 8, z) + gesicht(brille, 0.04, 20, z)
neu, n, belege = v.vorlagen_ergaenzen(alt, 30, aufnahme, S)
pruefe(neu is not None and belege >= 3 and n == 28 and len(neu) == 58 and neu[:30] == alt,
       f"ohne, dann mit Brille: {n} übernommen, {belege} Belege, Einlernen unverändert")
pruefe(v.aehnlichkeit(gesicht(brille, 0.04, 1, z)[0], neu) >= S,
       "danach wird das Gesicht mit Brille erkannt")

# 3. Erst ich, dann setzt sich eine andere Person davor: sie wird nicht übernommen
aufnahme = gesicht(ich, 0.04, 6, z) + gesicht(fremd, 0.04, 20, z)
neu2, n2, _ = v.vorlagen_ergaenzen(alt, 30, aufnahme, S)
pruefe(neu2 is not None and n2 == 6, f"fremdes Gesicht wird verworfen ({n2} übernommen)")
pruefe(v.aehnlichkeit(gesicht(fremd, 0.04, 1, z)[0], neu2) < 0.3,
       "die andere Person bleibt danach fremd")

# 4. Wiederholt ergänzen: nie mehr als 64, Einlernen bleibt, die neue Ergänzung hat Platz
neu3, n3, _ = v.vorlagen_ergaenzen(neu, 30, gesicht(ich, 0.04, 8, z) + gesicht(brille, 0.04, 22, z), S)
pruefe(len(neu3) == 64 and neu3[:30] == alt and n3 >= 17,
       f"zweite Ergänzung: {len(neu3)} Vorlagen, {n3} neu, Einlernen unverändert")
neu4, _, _ = v.vorlagen_ergaenzen(neu3, 30, gesicht(ich, 0.04, 30, z), S)
pruefe(len(neu4) == 64 and neu4[:30] == alt, "dritte Ergänzung: weiterhin höchstens 64")

# 5. Ältere Installation ohne vorlagen_basis: die ersten 30 gelten als Einlernen
neu5, _, _ = v.vorlagen_ergaenzen(alt, None, gesicht(ich, 0.04, 10, z), S)
pruefe(neu5[:30] == alt and len(neu5) == 40, "ohne gespeicherte Basis bleiben die ersten 30")

# 6. Gleichmäßige Auswahl
pruefe(v.gleichmaessig(list(range(10)), 4) == [0, 3, 6, 9] and v.gleichmaessig([1, 2], 5) == [1, 2]
       and v.gleichmaessig([1, 2, 3], 0) == [], "gleichmäßige Auswahl")

print(f"== Verwaltungshelfer: {10 - F}/10 bestanden")
sys.exit(1 if F else 0)
