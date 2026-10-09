"""Auswertung der Messung des Handzeichens ✌. Regeln vor der Messung festgelegt (09.10.2026).

Ein beleuchtetes Bild zählt, wenn eine Hand sicher erkannt ist (presence mindestens 0,5; die
Handflächensuche nutzt MediaPipes Schwelle 0,5) und Googles Klassifikator Victory mit
mindestens 0,5 als wahrscheinlichste Klasse wählt. Ein Zeichen ist erkannt, wenn das K = 3
Bilder in Folge so ist (etwa 0,4 s), wie im Prüfdienst.

Gemessen wird wie im echten Einsatz mit Rückmeldung („✓ Erkannt“ im Bild). Treffer: Beginn
zwischen 0,3 s vor und 5 s nach der Aufforderung. Fehlalarm: jedes erkannte Zeichen in den
Schritten ohne Handzeichen (Tippen, Alltag).

Machbar: kein einziger Fehlalarm (hart), mindestens 90 % erkannt, Median höchstens 1,5 s,
alle Schritte gemessen.

Aufruf: python3 auswerten_hand.py ORDNER
"""

import csv
import json
import statistics as st
import sys
from pathlib import Path

K = 3
RUECKMELDUNG_MS = 6000   # so lange steht die Aufforderung höchstens
P_MIN = 0.5
PRESENCE_MIN = 0.5
FENSTER = (-300, 5000)
TREFFER_MIN = 0.90
MEDIAN_MAX_MS = 1500

MIT = ["bestaetigen", "dunkel", "weit"]
OHNE = ["tippen", "alltag"]
KLASSEN = ("p_keine", "p_faust", "p_offen", "p_zeigen", "p_runter", "p_hoch", "p_victory", "p_love")
VERFAHREN = "Victory ✌"


def klasse(r, name):
    return r[name] is not None and r[name] >= P_MIN and r[name] == max(r[k] for k in KLASSEN)


def victory(r):
    return klasse(r, "p_victory")


def zahl(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def lade(pfad: Path):
    with open(pfad, newline="") as f:
        zeilen = [z for z in csv.DictReader(l for l in f if not l.startswith("#"))]
    return [{k: (v if k == "name" else zahl(v)) for k, v in z.items()} for z in zeilen
            if z.get("beleuchtet") == "1"]


def kurztext(pfad: Path):
    z = lade(pfad)
    return f"{sum(1 for r in z if r.get('hand') == 1)} von {len(z)} Bildern mit Hand"


def signale(ordner: Path, sid):
    try:
        return [int(x) for x in json.loads((ordner / f"{sid}.signale.json").read_text())]
    except (OSError, ValueError):
        return []


def hand_sicher(r):
    return r.get("hand") == 1 and (r.get("presence") or 0) >= PRESENCE_MIN


def ereignisse(zeilen, bedingung, k=K):
    """(start_unix_ms, anzahl_bilder) für Läufe von mindestens k Bildern in Folge."""
    aus, start, n = [], None, 0
    for r in zeilen + [None]:
        ja = r is not None and hand_sicher(r) and bedingung(r)
        if ja:
            if n == 0:
                start = r["unix_ms"]
            n += 1
            continue
        if n >= k:
            aus.append((start, n))
        n = 0
    return aus


def zuordnen(ev, sig, fenster=FENSTER):
    frei = list(sig)
    treffer, extra, verz = 0, 0, []
    for start, n in ev:
        passend = [s for s in frei if fenster[0] <= start - s <= fenster[1]]
        if not passend:
            extra += 1
            continue
        frei.remove(passend[0])
        treffer += 1
        verz.append(start - passend[0])
    return treffer, extra, verz


def auswertung(ordner: Path):
    ordner = Path(ordner)
    daten = {p.stem: lade(p) for p in sorted(ordner.glob("*.csv"))}
    if not daten:
        return "Noch keine Messungen.", []
    text = [f"Messreihe {ordner.name}: {', '.join(daten)}",
            f"Regel: Hand sicher erkannt und ✌ {K} Bilder in Folge, bis 5 s nach der "
            f"Aufforderung; machbar ab {TREFFER_MIN:.0%}, Median bis "
            f"{MEDIAN_MAX_MS / 1000:.1f} s, ohne Fehlalarm", ""]
    for sid, z in daten.items():
        mit = sum(1 for r in z if r.get("hand") == 1)
        text.append(f"  {sid:14s} {len(z):3d} Bilder, Hand in {mit}")
    text += ["", f"━━ {VERFAHREN} ━━"]
    t_sum = n_sum = 0
    alle_verz = []
    for sid in MIT:
        if sid not in daten:
            text.append(f"    {sid:14s} fehlt")
            continue
        sig = signale(ordner, sid)
        t, ex, verz = zuordnen(ereignisse(daten[sid], victory), sig)
        alle_verz += verz
        t_sum += t
        n_sum += len(sig)
        v = f", Verzögerung {st.median(verz) / 1000:.2f} s" if verz else ""
        text.append(f"    {sid:14s} {t}/{len(sig)} erkannt{f', {ex} ohne Hinweis' if ex else ''}{v}")
    fa = 0
    for sid in OHNE:
        if sid in daten:
            n = len(ereignisse(daten[sid], victory))
            fa += n
            text.append(f"    {sid:14s} {n} Fehlalarme")
        else:
            text.append(f"    {sid:14s} fehlt")
    quote = t_sum / n_sum if n_sum else 0.0
    median = st.median(alle_verz) if alle_verz else None
    ok = (n_sum > 0 and quote >= TREFFER_MIN and fa == 0 and median is not None
          and median <= MEDIAN_MAX_MS and all(s in daten for s in MIT + OHNE))
    m = f", Median {median / 1000:.2f} s bis erkannt" if median is not None else ""
    text.append(f"  → {t_sum}/{n_sum} erkannt ({quote:.0%}){m}, {fa} Fehlalarme: "
                f"{'MACHBAR' if ok else 'nicht erfüllt'}")
    ergebnisse = [{"verfahren": VERFAHREN, "ok": ok, "quote": quote, "fa": fa, "median": median,
                   "kurz": f"{quote:.0%} erkannt{m}, {fa} Fehlalarme" + (" → machbar" if ok else "")}]
    return "\n".join(text), ergebnisse


if __name__ == "__main__":
    print(auswertung(Path(sys.argv[1]))[0])
