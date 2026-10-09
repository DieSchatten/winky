#!/usr/bin/env python3
"""Wertet die Mess-CSVs der Erkennungsmessung aus und prüft das Entscheidungskriterium.

Gruppen nach Namensanfang der Sitzung:
  ich-...    echte Versuche der eingelernten Person
  fremd-...  andere Personen
  spoof-...  Handyfoto, Ausdruck
  leer-...   niemand vor der Kamera

Entscheidungsregel wie im späteren Prüfdienst: Erfolg, sobald zwei brauchbare
beleuchtete Bilder einen Wert (Mittel der 3 besten Vorlagen) >= Schwelle haben.
Ausgewertet wird das Modell SFace.

Aufruf: auswerten.py [--vorlagen-id ID] ORDNER_ODER_CSV [...]
Mit --vorlagen-id werden Sitzungen übersprungen, die mit anderen Vorlagen
gemessen wurden.
"""

import contextlib
import csv
import io
import math
import statistics
import sys
from pathlib import Path

ABSTAND = 0.08          # Sicherheitsabstand über dem höchsten Fremdwert
MIN_ECHT_ANTEIL = 0.70  # so viele eigene Bilder müssen die Schwelle schaffen
MAX_ENTSCHEIDUNG_MS = 1500
MODELLE = [("SFace", "wert_top3")]


def lade(pfad):
    meta, zeilen = {}, []
    with open(pfad, newline="") as f:
        kopf = None
        for zeile in f:
            if zeile.startswith("#"):
                k, _, v = zeile[1:].strip().partition("=")
                meta[k.strip()] = v.strip()
            elif kopf is None:
                kopf = next(csv.reader([zeile]))
            else:
                zeilen.append(dict(zip(kopf, next(csv.reader([zeile])))))
    return meta, zeilen


def zahl(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def gruppe(name):
    for g in ("ich", "fremd", "spoof", "leer"):
        if name == g or name.startswith(g + "-"):
            return g
    return "sonstig"


def entscheidung_ms(zeilen, spalte, schwelle, noetig=2):
    treffer = 0
    for z in zeilen:
        w = zahl(z.get(spalte))
        if w is not None and w >= schwelle:
            treffer += 1
            if treffer >= noetig:
                return zahl(z["t_ms"])
    return None


def werte(zeilen, spalte):
    return [w for z in zeilen if z.get("brauchbar") == "1"
            for w in [zahl(z.get(spalte))] if w is not None]


def f3(v):
    return f"{v:.3f}" if v is not None else "  -  "


def bewerte(name, spalte, sitzungen):
    """Gibt das Ergebnis als dict zurück und druckt es."""
    echt = [w for s in sitzungen if s["gruppe"] == "ich" for w in werte(s["zeilen"], spalte)]
    if not echt:
        return None
    fremd = [w for s in sitzungen if s["gruppe"] == "fremd" for w in werte(s["zeilen"], spalte)]
    eigene = [s for s in sitzungen if s["gruppe"] == "ich"]
    # Für die Geschwindigkeit zählen nur Sitzungen, in denen man auf den Bildschirm
    # schaut. "Seitlich" ist absichtlich gedreht und prüft nur die Robustheit.
    frontal = [s for s in eigene if not s["name"].startswith("ich-seitlich")]
    personen = sorted({s["name"].split("-")[1] for s in sitzungen if s["gruppe"] == "fremd"})
    echt_sortiert = sorted(echt)
    p05 = echt_sortiert[int(len(echt_sortiert) * 0.05)]
    print(f"\n━━ {name} ━━")
    print(f"Eigene Bilder: {len(echt)}, Werte {min(echt):.3f} bis {max(echt):.3f}, "
          f"Median {statistics.median(echt):.3f}, 5-%-Wert {p05:.3f}")
    for s in sitzungen:
        if s["gruppe"] in ("fremd", "spoof"):
            w = werte(s["zeilen"], spalte)
            print(f"  {s['anzeige']:<28} {len(w):>3} Bilder, höchster Wert {f3(max(w) if w else None)}")
    ergebnis = {"modell": name, "spalte": spalte, "personen": personen, "ok": None,
                "schwelle": None}
    if not fremd:
        print("Entscheidung offen: Es fehlen Messungen mit anderen Personen (fremd-...).")
        print("Zeiten unten mit Beispielschwelle 0,60.")
        schwelle = 0.6
    else:
        # Schwelle mit Abstand zu beiden Seiten: mindestens 0,08 über dem höchsten
        # Fremdwert, sonst die Mitte zwischen Fremd-Höchstwert und eigenem 5-%-Wert.
        mitte = (max(fremd) + p05) / 2
        schwelle = max(max(fremd) + ABSTAND, mitte)
        schwelle = math.ceil(schwelle * 100) / 100
        anteil = sum(w >= schwelle for w in echt) / len(echt)
        langsam = []
        for s in frontal:
            t = entscheidung_ms(s["zeilen"], spalte, schwelle)
            system = t - s["erstes"] if t is not None and s["erstes"] is not None else None
            if system is None or system > MAX_ENTSCHEIDUNG_MS:
                langsam.append(s["name"])
        durch = [s["name"] for s in sitzungen if s["gruppe"] in ("fremd", "spoof")
                 and entscheidung_ms(s["zeilen"], spalte, schwelle) is not None]
        print(f"Höchster Fremdwert {max(fremd):.3f}, Abstand zu deinem niedrigsten Wert "
              f"{min(echt) - max(fremd):.3f}")
        print(f"Empfohlene Schwelle {schwelle:.2f}: {anteil:.0%} deiner Bilder liegen darüber "
              f"(nötig {MIN_ECHT_ANTEIL:.0%})")
        print(f"Entscheidung ab Blick zum Bildschirm bis {MAX_ENTSCHEIDUNG_MS} ms: "
              f"{len(frontal) - len(langsam)} von {len(frontal)} Sitzungen"
              + (f" (zu langsam: {', '.join(langsam)})" if langsam else ""))
        if len(personen) < 2:
            print(f"Hinweis: erst {len(personen)} andere Person gemessen. Weitere, vor allem "
                  "ähnlich aussehende Verwandte, machen die Aussage belastbarer.")
        ok = anteil >= MIN_ECHT_ANTEIL and not durch and not langsam
        print("ERGEBNIS:", "WEITER (Kriterium erfüllt)" if ok else "nicht erfüllt")
        print(f"EMPFEHLUNG: schwelle={schwelle:.2f}")
        if durch:
            print("  Durchgekommen wären:", ", ".join(durch))
        ergebnis.update(ok=ok, schwelle=schwelle, anteil=anteil, langsam=langsam, durch=durch)
    print("Entscheidungszeit (2 Bilder über Schwelle), ab Start und ab Blick zum Bildschirm:")
    for s in eigene:
        t = entscheidung_ms(s["zeilen"], spalte, schwelle)
        if t is None:
            text = "nie"
        else:
            ab = f", ab Blick {int(t - s['erstes'])} ms" if s["erstes"] is not None else ""
            text = f"{int(t)} ms{ab}"
        print(f"  {s['anzeige']:<28} bei {schwelle:.2f}: {text}")
    return ergebnis


def _main(argv):
    vorlagen_id = None
    if len(argv) >= 2 and argv[0] == "--vorlagen-id":
        vorlagen_id, argv = argv[1], argv[2:]
    dateien = []
    for a in argv:
        p = Path(a)
        dateien += sorted(p.glob("*.csv")) if p.is_dir() else [p]
    if not dateien:
        print("Noch keine Messungen vorhanden.")
        return []
    mehrere_reihen = len({d.parent for d in dateien}) > 1

    sitzungen = []
    alt = 0
    for d in dateien:
        meta, zeilen = lade(d)
        if vorlagen_id and meta.get("vorlagen_id") and meta["vorlagen_id"] != vorlagen_id:
            alt += 1
            continue
        name = meta.get("name", d.stem)
        bel = [z for z in zeilen if z.get("beleuchtet") == "1"]
        sitzungen.append({
            "name": name, "gruppe": gruppe(name), "zeilen": zeilen, "meta": meta,
            "anzeige": f"{d.parent.name[5:]}/{name}" if mehrere_reihen else name,
            "bilder": len(zeilen), "beleuchtet": len(bel),
            "gesicht": sum(1 for z in bel if (zahl(z.get("gesichter")) or 0) > 0),
            "brauchbar": sum(1 for z in bel if z.get("brauchbar") == "1"),
            "erstes": next((zahl(z["t_ms"]) for z in bel if z.get("brauchbar") == "1"), None),
            "gruende": [z.get("grund") for z in bel if z.get("brauchbar") == "0"],
        })

    if alt:
        print(f"{alt} Sitzungen mit älteren Vorlagen nicht berücksichtigt.\n")
    print(f"{'Sitzung':<28}{'Bilder':>7}{'hell':>6}{'Gesicht':>8}{'brauchb.':>9}{'erstes':>9}"
          f"  verworfen wegen")
    for s in sitzungen:
        gr = {}
        for g in s["gruende"]:
            gr[g] = gr.get(g, 0) + 1
        erstes = f"{int(s['erstes'])} ms" if s["erstes"] is not None else "-"
        print(f"{s['anzeige']:<28}{s['bilder']:>7}{s['beleuchtet']:>6}{s['gesicht']:>8}"
              f"{s['brauchbar']:>9}{erstes:>9}  "
              + ", ".join(f"{k}={v}" for k, v in sorted(gr.items())))

    for s in sitzungen:
        if s["gruppe"] == "leer" and s["gesicht"]:
            print(f"Achtung: {s['anzeige']} meldet in {s['gesicht']} Bildern ein Gesicht.")
    kam = [zahl(s["meta"].get("kamera_start_ms")) for s in sitzungen]
    mod = [zahl(s["meta"].get("modelle_laden_ms")) for s in sitzungen]
    kam = [k for k in kam if k is not None]
    mod = [k for k in mod if k is not None]
    if kam and mod:
        print(f"\nKamerastart {min(kam):.0f} bis {max(kam):.0f} ms, "
              f"Modelle laden {statistics.median(mod):.0f} ms (Median)")

    return [e for name, spalte in MODELLE for e in [bewerte(name, spalte, sitzungen)] if e]


def auswertung(argv):
    """Liefert (Text, Ergebnisse je Modell) ohne etwas auszugeben."""
    puffer = io.StringIO()
    with contextlib.redirect_stdout(puffer):
        ergebnisse = _main(list(argv))
    return puffer.getvalue(), ergebnisse


def main(argv):
    text, _ = auswertung(argv)
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
