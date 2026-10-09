#!/usr/bin/env python3
"""Prüft die Auswertung der ✌-Messung mit künstlichen Daten, deren Ergebnis feststeht."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kalibrierung"))
import auswerten_hand as ah  # noqa: E402

FEHLER = []
KOPF = ("name,bild,unix_ms,t_ms,seq,hell,beleuchtet,gesichter,augenabstand,hand,palm,presence,"
        "verfolgt,rechts,p_keine,p_faust,p_offen,p_zeigen,p_runter,p_hoch,p_victory,p_love,"
        "regel_hoch,daumen_winkel,daumen_oben,daumen_lang,streck_zeige,streck_mittel,streck_ring,"
        "streck_klein,finger_nase,det_ms,palm_ms,hand_ms,geste_ms")
T0 = 1_760_000_000_000
BILD_MS = 133
SIG = [3000, 9000, 15000, 21000]


def pruefe(bed, text):
    print(("ok    " if bed else "FEHLER") + "  " + text)
    if not bed:
        FEHLER.append(text)


def schreibe(o, sid, dauer_s, zustand, signale=None):
    """zustand(t) -> None (keine Hand) oder dict mit geste, regel, nase, presence."""
    zeilen = [f"# name={sid}", KOPF]
    for i in range(int(dauer_s * 1000 / BILD_MS)):
        t = i * BILD_MS
        z = zustand(t)
        if z is None:
            zeilen.append(f"{sid},{i},{T0 + t},{t},{i},70,1,1,62,0,0.1" + "," * 21 + "30,5,0,0")
            continue
        p = [0.01] * 8
        p[{"hoch": 5, "runter": 4, "victory": 6, "offen": 2, "zeigen": 3, "keine": 0}[z.get("geste", "keine")]] = 0.9
        nase = z.get("nase")
        zeilen.append(f"{sid},{i},{T0 + t},{t},{i},70,1,1,62,1,0.9,{z.get('presence', 0.98)},1,0.9,"
                      + ",".join(f"{v}" for v in p)
                      + f",{1 if z.get('regel') else 0},10,0.3,0.8,1.1,1.1,1.1,1.1,"
                      + (f"{nase}" if nase is not None else "") + ",30,5,10,1")
    (o / f"{sid}.csv").write_text("\n".join(zeilen) + "\n")
    if signale is not None:
        (o / f"{sid}.signale.json").write_text(json.dumps([T0 + s for s in signale]))


def zeichen(geste="victory", bilder=6, kurz=()):
    """Ab 0,8 s nach jedem Hinweis `bilder` Bilder lang das Zeichen."""
    def z(t):
        for k, s in enumerate(SIG):
            n = 2 if k in kurz else bilder
            if s + 800 <= t < s + 800 + n * BILD_MS:
                return {"geste": geste}
        return None
    return z


def main():
    with tempfile.TemporaryDirectory() as tmp:
        o = Path(tmp)
        # Bestätigen und Dunkel sauber, mit Abstand ein Zeichen nur 2 Bilder lang
        for sid in ("bestaetigen", "dunkel", "weit"):
            schreibe(o, sid, 34, zeichen(kurz=(1,) if sid == "weit" else ()), SIG)
        schreibe(o, "tippen", 30, lambda t: None)
        # Alltag: Winken (offene Hand), Zählen mit kurzem V über 2 Bilder = kein Fehlalarm
        schreibe(o, "alltag", 45, lambda t: {"geste": "offen"} if 20000 <= t < 25000 else
                 ({"geste": "victory"} if 41000 <= t < 41000 + 2 * BILD_MS else None))
        text, erg = ah.auswertung(o)
        v = erg[0]
        pruefe(abs(v["quote"] - 11 / 12) < 1e-9 and v["fa"] == 0 and v["ok"],
               "11/12 (ein Zeichen nur 2 Bilder), kurzes V beim Zählen kein Fehlalarm → machbar")
        pruefe(len(erg) == 1 and v["verfahren"] == "Victory ✌", "nur noch das Verfahren ✌")
        # Zählen mit längerem V = Fehlalarm
        schreibe(o, "alltag", 45, lambda t: {"geste": "victory"} if 41000 <= t < 42000 else None)
        v = ah.auswertung(o)[1][0]
        pruefe(v["fa"] == 1 and not v["ok"], "längeres V beim Zählen ist ein Fehlalarm")
        schreibe(o, "alltag", 45, lambda t: None)
        # Hand unsicher (presence < 0,5) zählt nicht
        schreibe(o, "dunkel", 34, lambda t: {"geste": "victory", "presence": 0.3}
                 if any(s + 800 <= t < s + 1600 for s in SIG) else None, SIG)
        text, erg = ah.auswertung(o)
        pruefe("dunkel         0/4 erkannt" in text and not erg[0]["ok"],
               "unsichere Hand (presence < 0,5) zählt nicht")
        schreibe(o, "dunkel", 34, zeichen(), SIG)
        # Fehlender Schritt ohne Handzeichen verhindert „machbar“
        (o / "tippen.csv").unlink()
        text, erg = ah.auswertung(o)
        pruefe(not erg[0]["ok"] and "tippen         fehlt" in text, "ohne Schritt „Tippen“ kein „machbar“")
        schreibe(o, "tippen", 30, lambda t: None)
        # Erst nach 4 s erkannt: zählt, aber der Median über 1,5 s verhindert „machbar“
        spaet = lambda t: {"geste": "victory"} if any(s + 4000 <= t < s + 4800 for s in SIG) else None
        for sid in ("bestaetigen", "dunkel", "weit"):
            schreibe(o, sid, 34, spaet, SIG)
        v = ah.auswertung(o)[1][0]
        pruefe(v["quote"] == 1.0 and v["fa"] == 0 and not v["ok"],
               "spät erkannt zählt, aber der Median über 1,5 s verhindert „machbar“")
        for sid in ("bestaetigen", "dunkel", "weit"):
            schreibe(o, sid, 34, zeichen(), SIG)
        text, erg = ah.auswertung(o)
        pruefe(erg[0]["ok"] and abs(erg[0]["median"] - 800) < 150, "schnell erkannt → machbar, Median 0,8 s")
        print()
        print(text)
    print(f"\n{len(FEHLER)} Fehler")
    return 1 if FEHLER else 0


if __name__ == "__main__":
    sys.exit(main())
