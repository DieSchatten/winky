"""Seite "Messung": Kalibrierung der Erkennung mit eigenen und fremden Gesichtern.

Läuft als normaler Benutzer mit dem Messwerkzeug. Gespeichert werden nur
Kennzahlen (CSV) und eigene Mess-Vorlagen unter ~/.local/share/winky. Die
Systemvorlagen für die Entsperrung sind davon getrennt.
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path

from gi.repository import Adw, GLib, Gtk

import auswerten
import messumgebung as umgebung
from prozess import Prozess
from vorschau import Vorschau, komma, live_text


def VORLAGEN():
    return umgebung.MESSUNGEN / "vorlagen.bin"


def schritt(id, titel, gruppe, text, dauer=10, countdown=5, optional=False):
    return dict(id=id, titel=titel, gruppe=gruppe, text=text, dauer=dauer,
                countdown=countdown, optional=optional)


EINLERNEN = schritt(
    "einlernen", "Einlernen für die Messung", "Vorbereitung",
    "Setz dich normal vor den Laptop, Abstand wie beim Arbeiten. Bewege den Kopf während "
    "der Aufnahme langsam etwas nach links, rechts, oben und unten.\n\n"
    "Diese Vorlagen dienen nur der Messung. Neues Einlernen beginnt automatisch eine neue "
    "Messreihe, weil alte Werte nicht mehr vergleichbar sind.",
    dauer=25, countdown=3)

ENTSPERREN_TEXT = ("Schau auf den Bildschirm und klick dann auf Starten, so wie du später "
                   "entsperren würdest. Die Messung beginnt sofort und dauert 3 Sekunden.")

FESTE_SCHRITTE = [
    schritt("ich-normal", "Normal", "Du", "Setz dich normal hin und schau auf den Bildschirm."),
    schritt("ich-entsperren-1", "Entsperren 1", "Du", ENTSPERREN_TEXT, dauer=3, countdown=0),
    schritt("ich-entsperren-2", "Entsperren 2", "Du", ENTSPERREN_TEXT, dauer=3, countdown=0),
    schritt("ich-entsperren-3", "Entsperren 3", "Du", ENTSPERREN_TEXT, dauer=3, countdown=0),
    schritt("ich-dunkel", "Dunkler Raum", "Du",
            "Mach zuerst das Raumlicht aus, der Bildschirm bleibt an. Nach dem Klick auf "
            "Starten hast du 5 Sekunden, um die Hände von Tastatur und Kamera wegzunehmen. "
            "Dann normal auf den Bildschirm schauen."),
    schritt("ich-nah", "Nah", "Du", "Etwa 30 cm nah an den Bildschirm und draufschauen."),
    schritt("ich-fern", "Weit weg", "Du", "Etwa 70 cm zurücklehnen und auf den Bildschirm schauen."),
    schritt("ich-seitlich", "Seitlich", "Du",
            "Kopf leicht zur Seite drehen und zum Bildschirmrand schauen."),
    schritt("ich-brille", "Mit Brille", "Du",
            "Mit Brille oder Sonnenbrille auf den Bildschirm schauen.", optional=True),
    schritt("leer", "Niemand da", "Kontrolle",
            "Niemand vor der Kamera. Verlass den Platz während des Countdowns.",
            dauer=5, countdown=8),
    schritt("spoof-handy", "Handyfoto", "Täuschungsversuche",
            "Halte ein Foto von dir auf dem Handy vor die Kamera. Du selbst bleibst außer Sicht."),
    schritt("spoof-ausdruck", "Ausdruck", "Täuschungsversuche",
            "Halte ein ausgedrucktes Foto von dir vor die Kamera. Du selbst bleibst außer Sicht.",
            optional=True),
]


def personen_schritte(name):
    anzeige = name.capitalize()
    return [
        schritt(f"fremd-{name}-1", f"{anzeige} 1", "Andere Personen",
                f"{anzeige} setzt sich normal vor den Laptop und schaut auf den Bildschirm."),
        schritt(f"fremd-{name}-2", f"{anzeige} 2", "Andere Personen",
                f"{anzeige} setzt sich noch einmal davor, diesmal etwas näher und leicht seitlich."),
    ]


def vorlagen_id():
    try:
        return hashlib.sha256(VORLAGEN().read_bytes()).hexdigest()[:12]
    except FileNotFoundError:
        return None


class Messreihe:
    def __init__(self, ordner: Path):
        self.ordner = ordner
        self.datei = ordner / "messreihe.json"
        try:
            self.daten = json.loads(self.datei.read_text())
        except (FileNotFoundError, ValueError):
            # Messreihen aus dem alten Skript gehören zu den damals entstandenen Vorlagen
            self.daten = {"vorlagen_id": vorlagen_id(), "personen": []}
            self.speichern()

    @property
    def name(self):
        return self.ordner.name

    @property
    def vorlagen_id(self):
        return self.daten.get("vorlagen_id")

    @property
    def personen(self):
        return self.daten.setdefault("personen", [])

    def speichern(self):
        tmp = self.datei.with_suffix(".neu")
        tmp.write_text(json.dumps(self.daten, indent=2, ensure_ascii=False))
        os.chmod(tmp, 0o600)
        tmp.replace(self.datei)

    def csv(self, sid):
        return self.ordner / f"{sid}.csv"

    def hat_messungen(self):
        return any(self.ordner.glob("*.csv"))

    @staticmethod
    def neu(personen=()):
        basis = time.strftime("%Y-%m-%d_%H%M%S")
        for i in range(1, 100):
            ordner = umgebung.MESSUNGEN / (basis if i == 1 else f"{basis}-{i}")
            try:
                ordner.mkdir(mode=0o700, parents=True, exist_ok=False)
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError("kein freier Name für die Messreihe")
        r = Messreihe.__new__(Messreihe)
        r.ordner = ordner
        r.datei = ordner / "messreihe.json"
        r.daten = {"vorlagen_id": vorlagen_id(), "personen": list(personen)}
        r.speichern()
        return r


def zusammenfassung(pfad: Path):
    meta, zeilen = auswerten.lade(pfad)
    bel = [z for z in zeilen if z.get("beleuchtet") == "1"]
    gut = [z for z in bel if z.get("brauchbar") == "1"]
    werte = [w for z in gut for w in [auswerten.zahl(z.get("wert_top3"))] if w is not None]
    return {
        "meta": meta, "beleuchtet": len(bel), "brauchbar": len(gut),
        "gesicht": sum(1 for z in bel if (auswerten.zahl(z.get("gesichter")) or 0) > 0),
        "median": sorted(werte)[len(werte) // 2] if werte else None,
        "minimum": min(werte) if werte else None,
        "erstes": auswerten.zahl(gut[0]["t_ms"]) if gut else None,
        "zweites": auswerten.zahl(gut[1]["t_ms"]) if len(gut) > 1 else None,
    }


def reihen_ordner():
    """Messreihen der Erkennung: Ordner mit Datumsnamen. Die Unterordner anderer Seiten
    (etwa hand/) gehören nicht dazu."""
    if not umgebung.MESSUNGEN.is_dir():
        return []
    return sorted(p for p in umgebung.MESSUNGEN.iterdir()
                  if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{4}(\d{2})?(-\d+)?", p.name))


def gesamtauswertung():
    """Auswertung aller Messreihen mit den aktuellen Mess-Vorlagen.

    Liefert (Text, Ergebnisse je Modell, Ordnerliste)."""
    vid = vorlagen_id()
    if not umgebung.MESSUNGEN.is_dir() or vid is None:
        return "Noch keine Messungen.", [], []
    ordner = [p for p in reihen_ordner()
              if Messreihe(p).vorlagen_id == vid and any(p.glob("*.csv"))]
    if not ordner:
        return "Noch keine Messungen.", [], []
    text, ergebnisse = auswerten.auswertung(["--vorlagen-id", vid, *map(str, ordner)])
    return text, ergebnisse, ordner


class MessungSeite(Gtk.Box):
    """Schritte links, Ablauf rechts. melde(text) zeigt eine Kurzmeldung,
    geaendert() informiert die App über neue Ergebnisse."""

    def __init__(self, melde, geaendert):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.melde, self.geaendert = melde, geaendert
        self.lauf = None
        self.lauf_art = None
        self.lauf_schritt = None
        self.nach_vorschau = None
        self.countdown_id = None
        self.schritt_aktuell = None
        self._angezeigt = None
        self.reihe = self._letzte_oder_neue_reihe()

        leiste = Gtk.Box(spacing=8, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
        leiste.append(Gtk.Label(label="Messreihe:"))
        self.reihen_liste = Gtk.StringList()
        self.reihen_auswahl = Gtk.DropDown(model=self.reihen_liste)
        self.reihen_auswahl.connect("notify::selected", self._reihe_gewaehlt)
        leiste.append(self.reihen_auswahl)
        knopf_neu = Gtk.Button(icon_name="document-new-symbolic",
                               tooltip_text="Neue Messreihe, zum Beispiel an einem anderen Tag")
        knopf_neu.connect("clicked", lambda *_: self._neue_reihe())
        leiste.append(knopf_neu)
        self.append(leiste)
        self.banner = Adw.Banner()
        self.banner.connect("button-clicked", lambda *_: self._neue_reihe())
        self.append(self.banner)

        teiler = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, position=320, vexpand=True)
        self.liste = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.liste.add_css_class("navigation-sidebar")
        self.liste.set_header_func(self._kopfzeile)
        self.liste.connect("row-selected", self._zeile_gewaehlt)
        self.liste.connect("row-activated", self._zeile_aktiviert)
        teiler.set_start_child(Gtk.ScrolledWindow(child=self.liste,
                                                  hscrollbar_policy=Gtk.PolicyType.NEVER))
        teiler.set_shrink_start_child(False)
        teiler.set_resize_start_child(False)
        self.stapel = Gtk.Stack()
        self.stapel.add_named(self._baue_schrittseite(), "schritt")
        self.stapel.add_named(self._baue_auswertung(), "auswertung")
        teiler.set_end_child(self.stapel)
        self.append(teiler)

        self._reihen_laden()
        self._liste_aufbauen(auswahl="einlernen" if not VORLAGEN().exists() else None)

    # ------------------------------------------------------------ Messreihen

    def _letzte_oder_neue_reihe(self):
        umgebung.MESSUNGEN.mkdir(mode=0o700, parents=True, exist_ok=True)
        reihen = reihen_ordner()
        aktuell = vorlagen_id()
        for p in reversed(reihen):
            r = Messreihe(p)
            if r.vorlagen_id == aktuell:
                return r
        return Messreihe(reihen[-1]) if reihen else Messreihe.neu()

    def _reihen_laden(self):
        self._reihen = [p.name for p in reihen_ordner()]
        self._wird_geladen = True
        self.reihen_liste.splice(0, self.reihen_liste.get_n_items(), self._reihen)
        self.reihen_auswahl.set_selected(self._reihen.index(self.reihe.name))
        self._wird_geladen = False
        self._banner_aktualisieren()

    def _reihe_gewaehlt(self, *_):
        if getattr(self, "_wird_geladen", False) or self.lauf:
            return
        i = self.reihen_auswahl.get_selected()
        if 0 <= i < len(self._reihen) and self._reihen[i] != self.reihe.name:
            self.reihe = Messreihe(umgebung.MESSUNGEN / self._reihen[i])
            self._banner_aktualisieren()
            self._liste_aufbauen()

    def _neue_reihe(self):
        if self.lauf:
            return
        self.reihe = Messreihe.neu(self.reihe.personen)
        self._reihen_laden()
        self._liste_aufbauen()
        self.melde(f"Neue Messreihe {self.reihe.name} angelegt")

    def _reihe_aktuell(self):
        return vorlagen_id() is not None and self.reihe.vorlagen_id == vorlagen_id()

    def _banner_aktualisieren(self):
        if VORLAGEN().exists() and not self._reihe_aktuell():
            self.banner.set_title("Diese Messreihe gehört zu früheren Vorlagen. "
                                  "Messen geht nur in einer aktuellen Messreihe.")
            self.banner.set_button_label("Neue Messreihe")
            self.banner.set_revealed(True)
        else:
            self.banner.set_revealed(False)

    # ------------------------------------------------------------ Seitenleiste

    def _schritte(self):
        alle = [EINLERNEN, *FESTE_SCHRITTE]
        for p in self.reihe.personen:
            alle += personen_schritte(p)
        return alle

    def status(self, s):
        """(Symbol, Untertitel, erledigt)"""
        if s["id"] == "einlernen":
            if VORLAGEN().exists():
                zeit = time.strftime("%d.%m. %H:%M", time.localtime(VORLAGEN().stat().st_mtime))
                return "emblem-ok-symbolic", f"Vorlagen vom {zeit}", True
            return "media-record-symbolic", "noch offen, bitte zuerst", False
        pfad = self.reihe.csv(s["id"])
        if not pfad.exists():
            return "media-record-symbolic", "optional" if s["optional"] else "offen", False
        z = zusammenfassung(pfad)
        if z["meta"].get("vorlagen_id") and z["meta"]["vorlagen_id"] != self.reihe.vorlagen_id:
            return "dialog-warning-symbolic", "alte Vorlagen, bitte wiederholen", False
        if s["id"].startswith(("spoof", "leer")):
            text = f"{z['gesicht']} von {z['beleuchtet']} Bildern mit Gesicht"
        else:
            m = f", Wert {komma(z['median'])}" if z["median"] is not None else ""
            text = f"{z['brauchbar']} brauchbare Bilder{m}"
        return "emblem-ok-symbolic", text, True

    def _liste_aufbauen(self, auswahl=None):
        auswahl = auswahl or (self.schritt_aktuell["id"] if self.schritt_aktuell else None)
        while (zeile := self.liste.get_row_at_index(0)) is not None:
            self.liste.remove(zeile)
        ziel = None
        for s in self._schritte():
            symbol, untertitel, _ = self.status(s)
            zeile = Adw.ActionRow(title=s["titel"], subtitle=untertitel)
            zeile.add_prefix(Gtk.Image(icon_name=symbol))
            zeile.schritt, zeile.gruppe, zeile.aktion = s, s["gruppe"], None
            self.liste.append(zeile)
            if s["id"] == auswahl:
                ziel = zeile
        neu = Adw.ActionRow(title="Person hinzufügen …", activatable=True)
        neu.add_prefix(Gtk.Image(icon_name="list-add-symbolic"))
        neu.schritt, neu.gruppe, neu.aktion = None, "Andere Personen", "person"
        self.liste.append(neu)
        ausw = Adw.ActionRow(title="Auswertung", subtitle="Ergebnis und Entscheidung")
        ausw.add_prefix(Gtk.Image(icon_name="view-refresh-symbolic"))
        ausw.schritt, ausw.gruppe, ausw.aktion = None, "Ergebnis", "auswertung"
        self.liste.append(ausw)
        if auswahl == "auswertung":
            ziel = ausw
        self.liste.select_row(ziel or self.liste.get_row_at_index(0))

    def _kopfzeile(self, zeile, davor):
        if davor is None or davor.gruppe != zeile.gruppe:
            label = Gtk.Label(label=zeile.gruppe, xalign=0)
            label.add_css_class("heading")
            label.set_margin_top(14 if davor else 6)
            label.set_margin_bottom(4)
            label.set_margin_start(12)
            zeile.set_header(label)
        else:
            zeile.set_header(None)

    def _zeile_gewaehlt(self, _liste, zeile):
        if zeile is None:
            return
        if zeile.aktion == "auswertung":
            self.schritt_aktuell = None
            self.stapel.set_visible_child_name("auswertung")
            self._auswertung_berechnen()
        elif zeile.schritt:
            self.schritt_aktuell = zeile.schritt
            self.stapel.set_visible_child_name("schritt")
            self._schrittseite_fuellen()

    def _zeile_aktiviert(self, _liste, zeile):
        if zeile.aktion == "person":
            self._person_dialog()

    def zeige_auswertung(self):
        self._liste_aufbauen(auswahl="auswertung")

    # ------------------------------------------------------------ Schrittseite

    def _baue_schrittseite(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=24,
                      margin_bottom=24, margin_start=24, margin_end=24)
        self.s_gruppe = Gtk.Label(xalign=0)
        self.s_gruppe.add_css_class("dim-label")
        self.s_titel = Gtk.Label(xalign=0)
        self.s_titel.add_css_class("title-1")
        self.s_text = Gtk.Label(xalign=0, wrap=True, max_width_chars=80)
        for w in (self.s_gruppe, self.s_titel, self.s_text):
            box.append(w)
        self.vorschau = Vorschau()
        box.append(self.vorschau)
        hinweis = Gtk.Label(xalign=0, label="Das Kamerabild wird nur angezeigt und nirgends "
                            "gespeichert. Gespeichert werden nur Zahlen.")
        hinweis.add_css_class("dim-label")
        hinweis.add_css_class("caption")
        box.append(hinweis)
        self.live = Gtk.Label(xalign=0)
        box.append(self.live)
        self.fortschritt = Gtk.ProgressBar()
        box.append(self.fortschritt)

        knoepfe = Gtk.Box(spacing=8)
        self.k_vorschau = Gtk.ToggleButton(label="Kamera-Vorschau")
        self.k_vorschau.set_tooltip_text("Kamerabild anzeigen, um dich vor dem Start auszurichten")
        self.k_vorschau.connect("toggled", self._vorschau_umschalten)
        self.k_start = Gtk.Button(label="Starten")
        self.k_start.add_css_class("suggested-action")
        self.k_start.connect("clicked", lambda *_: self.starten())
        self.k_abbruch = Gtk.Button(label="Abbrechen")
        self.k_abbruch.add_css_class("destructive-action")
        self.k_abbruch.connect("clicked", lambda *_: self.abbrechen())
        self.k_weiter = Gtk.Button(label="Nächster offener Schritt", hexpand=True,
                                   halign=Gtk.Align.END)
        self.k_weiter.connect("clicked", lambda *_: self._naechster())
        for k in (self.k_vorschau, self.k_start, self.k_abbruch, self.k_weiter):
            knoepfe.append(k)
        box.append(knoepfe)
        self.ergebnis = Gtk.Label(xalign=0, wrap=True, selectable=True)
        box.append(self.ergebnis)
        neben = Gtk.Box(spacing=8)
        self.k_loeschen = Gtk.Button(label="Ergebnis löschen")
        self.k_loeschen.connect("clicked", lambda *_: self._ergebnis_loeschen())
        self.k_person_weg = Gtk.Button(label="Person entfernen")
        self.k_person_weg.connect("clicked", lambda *_: self._person_entfernen())
        for k in (self.k_loeschen, self.k_person_weg):
            k.add_css_class("flat")
            neben.append(k)
        box.append(neben)
        return Gtk.ScrolledWindow(child=box, hscrollbar_policy=Gtk.PolicyType.NEVER)

    def _schrittseite_fuellen(self):
        s = self.schritt_aktuell
        self.s_gruppe.set_label(s["gruppe"] + (" · optional" if s["optional"] else ""))
        self.s_titel.set_label(s["titel"])
        self.s_text.set_label(s["text"])
        _, _, erledigt = self.status(s)
        self.ergebnis.set_label(self._ergebnis_text(s) if erledigt else "")
        if not self.lauf and s["id"] != self._angezeigt:
            self.live.set_label("")
            self.fortschritt.set_fraction(0)
            self.vorschau.leeren()
        self._angezeigt = s["id"]
        self._knoepfe_aktualisieren()

    def _ergebnis_text(self, s):
        if s["id"] == "einlernen":
            return "Mess-Vorlagen sind gespeichert. Erneutes Einlernen beginnt eine neue Messreihe."
        z = zusammenfassung(self.reihe.csv(s["id"]))
        zeilen = [f"Gespeichert: {z['beleuchtet']} beleuchtete Bilder, davon {z['gesicht']} mit "
                  f"Gesicht und {z['brauchbar']} brauchbar."]
        if z["median"] is not None:
            zeilen.append(f"Ähnlichkeit: Median {komma(z['median'])}, "
                          f"niedrigster Wert {komma(z['minimum'])}.")
        if z["erstes"] is not None:
            zeilen.append(f"Erstes brauchbares Bild nach {int(z['erstes'])} ms.")
        if s["id"].startswith("ich-entsperren") and z["zweites"] is not None:
            zeilen.append(f"Entscheidung wäre nach {int(z['zweites'])} ms gefallen.")
        if s["id"].startswith(("spoof", "leer")):
            zeilen.append("Gut: kein Gesicht erkannt." if z["gesicht"] == 0 else
                          "Achtung: Hier wurde ein Gesicht erkannt.")
        return "\n".join(zeilen)

    def _knoepfe_aktualisieren(self):
        s = self.schritt_aktuell
        laeuft = self.lauf is not None or self.countdown_id is not None
        messung_laeuft = laeuft and self.lauf_art != "vorschau"
        erledigt = self.status(s)[2] if s else False
        darf = s is not None and (s["id"] == "einlernen" or
                                  (VORLAGEN().exists() and self._reihe_aktuell()))
        self.k_start.set_label("Wiederholen" if erledigt else "Starten")
        self.k_start.set_sensitive(darf and not messung_laeuft)
        self.k_abbruch.set_visible(messung_laeuft)
        self.k_vorschau.set_sensitive(not messung_laeuft)
        self.k_loeschen.set_visible(erledigt and s["id"] != "einlernen")
        self.k_loeschen.set_sensitive(not laeuft)
        self.k_person_weg.set_visible(bool(s) and s["id"].startswith("fremd-"))
        self.k_person_weg.set_sensitive(not laeuft)
        self.k_weiter.set_sensitive(not laeuft)
        self.liste.set_sensitive(not messung_laeuft)
        self.reihen_auswahl.set_sensitive(not laeuft)

    # ------------------------------------------------------------ Abläufe

    def beschaeftigt(self):
        return self.lauf is not None or self.countdown_id is not None

    def _vorschau_umschalten(self, knopf):
        if knopf.get_active():
            if self.lauf is None:
                args = ["vorschau", "--dauer", "300"]
                if VORLAGEN().exists() and self._reihe_aktuell():
                    args += ["--vorlagen", umgebung.werkzeug_pfad(VORLAGEN())]
                self._lauf_starten("vorschau", args, None)
        elif self.lauf and self.lauf_art == "vorschau":
            self.lauf.abbrechen()

    def starten(self):
        s = self.schritt_aktuell
        if s is None:
            return
        if self.lauf and self.lauf_art == "vorschau":
            self.nach_vorschau = s
            self.k_vorschau.set_active(False)
            self.vorschau.hinweis("Kamera wird umgeschaltet …")
            return
        if self.lauf:
            return
        self._countdown(s, s["countdown"])

    def _countdown(self, s, rest):
        self.countdown_id = None
        if rest <= 0:
            self._messung_starten(s)
            return
        self.vorschau.leeren(f"Start in {rest}")
        self.live.set_label("")
        self.fortschritt.set_fraction(0)
        self.lauf_art = "countdown"
        self.countdown_id = GLib.timeout_add(1000, self._countdown_tick, s, rest - 1)
        self._knoepfe_aktualisieren()

    def _countdown_tick(self, s, rest):
        self.countdown_id = None
        self._countdown(s, rest)
        return False

    def _messung_starten(self, s):
        if s["id"] == "einlernen":
            args = ["einlernen", "--vorlagen", umgebung.werkzeug_pfad(VORLAGEN()),
                    "--dauer", str(s["dauer"])]
            self._lauf_starten("einlernen", args, s)
            return
        teil = self.reihe.csv(s["id"]).with_suffix(".csv.teil")
        args = ["messen", "--vorlagen", umgebung.werkzeug_pfad(VORLAGEN()), "--vorlagen-id",
                vorlagen_id(), "--name", s["id"], "--dauer", str(s["dauer"]),
                "--csv", umgebung.werkzeug_pfad(teil)]
        self._lauf_starten("messen", args, s)

    def _lauf_starten(self, art, args, s):
        if not umgebung.kamera_vorhanden():
            self.melde("IR-Kamera nicht gefunden")
            self.k_vorschau.set_active(False)
            self.lauf_art = None
            self._knoepfe_aktualisieren()
            return
        self.lauf_art, self.lauf_schritt = art, s
        self.live.set_label("Kamera und Modelle starten …")
        self.vorschau.hinweis("Kamera startet …")
        self.fortschritt.set_fraction(0)
        try:
            self.lauf = Prozess(umgebung.messwerkzeug_befehl(args), self._bei_bild,
                                self._bei_status, self._bei_ende)
        except (OSError, RuntimeError) as e:
            self.lauf, self.lauf_art = None, None
            self.melde(f"Start fehlgeschlagen: {e}")
        self._knoepfe_aktualisieren()

    def abbrechen(self):
        if self.countdown_id is not None:
            GLib.source_remove(self.countdown_id)
            self.countdown_id = None
            self.lauf_art = None
            self.vorschau.hinweis("Abgebrochen")
            self._knoepfe_aktualisieren()
        elif self.lauf:
            self.lauf.abbrechen()

    def _bei_bild(self, w, h, daten):
        if self.lauf:
            self.vorschau.zeige(w, h, daten)

    def _bei_status(self, st):
        if not self.lauf:
            return
        text, gut = live_text(st)
        self.live.set_label(text)
        self.live.remove_css_class("gut")
        self.live.remove_css_class("warnung")
        self.live.add_css_class("gut" if gut else "warnung")
        if st.get("dauer"):
            self.fortschritt.set_fraction(min(1.0, float(st.get("t", 0)) / float(st["dauer"])))

    def _bei_ende(self, lauf, rc):
        art, s = self.lauf_art, self.lauf_schritt
        self.lauf, self.lauf_art, self.lauf_schritt = None, None, None
        self.vorschau.leeren()
        if art == "vorschau":
            self.live.set_label("")
            self.k_vorschau.set_active(False)
            if rc not in (0, 3, -15) and not lauf.abgebrochen:
                self.ergebnis.set_label(f"Vorschau beendet mit Fehler:\n{lauf.fehlermeldung(rc)}")
            if self.nach_vorschau is not None:
                s, self.nach_vorschau = self.nach_vorschau, None
                self._knoepfe_aktualisieren()
                self._countdown(s, s["countdown"])
                return
        elif art == "einlernen":
            if rc == 0:
                self.vorschau.hinweis("Fertig")
                self.fortschritt.set_fraction(1)
                if self.reihe.hat_messungen():
                    self.reihe = Messreihe.neu(self.reihe.personen)
                    self.melde("Neue Mess-Vorlagen gespeichert, neue Messreihe angelegt")
                else:
                    self.reihe.daten["vorlagen_id"] = vorlagen_id()
                    self.reihe.speichern()
                    self.melde("Mess-Vorlagen gespeichert")
                self._reihen_laden()
            else:
                self.vorschau.hinweis("Abgebrochen" if lauf.abgebrochen else "Fehlgeschlagen")
                self.ergebnis.set_label("" if lauf.abgebrochen else lauf.fehlermeldung(rc))
        elif art == "messen":
            teil = self.reihe.csv(s["id"]).with_suffix(".csv.teil")
            if rc == 0 and teil.exists():
                teil.replace(self.reihe.csv(s["id"]))
                self.vorschau.hinweis("Fertig")
                self.fortschritt.set_fraction(1)
            else:
                teil.unlink(missing_ok=True)
                self.vorschau.hinweis("Abgebrochen" if lauf.abgebrochen else "Fehlgeschlagen")
                if not lauf.abgebrochen:
                    self.ergebnis.set_label(f"Die Messung ist fehlgeschlagen:\n"
                                            f"{lauf.fehlermeldung(rc)}")
        self._liste_aufbauen(auswahl=s["id"] if s else None)
        if art in ("einlernen", "messen") and rc == 0 and s is not None:
            self.ergebnis.set_label(self._ergebnis_text(s))
            self.geaendert()
        self._knoepfe_aktualisieren()

    def _ergebnis_loeschen(self):
        s = self.schritt_aktuell
        if s and s["id"] != "einlernen":
            self.reihe.csv(s["id"]).unlink(missing_ok=True)
            self._liste_aufbauen(auswahl=s["id"])
            self.melde(f"Ergebnis „{s['titel']}“ gelöscht")
            self.geaendert()

    def _naechster(self):
        schritte = self._schritte()
        ids = [s["id"] for s in schritte]
        start = ids.index(self.schritt_aktuell["id"]) + 1 if self.schritt_aktuell else 0
        for s in schritte[start:] + schritte[:start]:
            if not self.status(s)[2] and not s["optional"]:
                self._liste_aufbauen(auswahl=s["id"])
                return
        self._liste_aufbauen(auswahl="auswertung")

    # ------------------------------------------------------------ Personen

    def _person_dialog(self):
        dialog = Adw.AlertDialog.new(
            "Person hinzufügen",
            "Vorname der Person. Gespeichert werden nur Zahlen, keine Bilder. "
            "Bitte vorher kurz um Erlaubnis fragen.")
        eingabe = Gtk.Entry(placeholder_text="Vorname", activates_default=True)
        dialog.set_extra_child(eingabe)
        dialog.add_response("abbrechen", "Abbrechen")
        dialog.add_response("ok", "Hinzufügen")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("ok")
        dialog.set_close_response("abbrechen")

        def antwort(_d, r):
            name = "".join(c for c in eingabe.get_text().strip().lower()
                           if c.isalnum() or c == "-")[:24]
            if r != "ok" or not name:
                return
            if name in self.reihe.personen:
                self.melde(f"{name.capitalize()} ist schon dabei")
            else:
                self.reihe.personen.append(name)
                self.reihe.speichern()
            self._liste_aufbauen(auswahl=f"fremd-{name}-1")

        dialog.connect("response", antwort)
        dialog.present(self.get_root())

    def _person_entfernen(self):
        s = self.schritt_aktuell
        if not s or not s["id"].startswith("fremd-"):
            return
        name = s["id"][len("fremd-"):].rsplit("-", 1)[0]
        dialog = Adw.AlertDialog.new(f"{name.capitalize()} entfernen?",
                                     "Beide Messungen dieser Person werden gelöscht.")
        dialog.add_response("abbrechen", "Abbrechen")
        dialog.add_response("weg", "Entfernen")
        dialog.set_response_appearance("weg", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("abbrechen")

        def antwort(_d, r):
            if r != "weg":
                return
            for teil in personen_schritte(name):
                self.reihe.csv(teil["id"]).unlink(missing_ok=True)
            if name in self.reihe.personen:
                self.reihe.personen.remove(name)
                self.reihe.speichern()
            self.schritt_aktuell = None
            self._liste_aufbauen(auswahl="auswertung")
            self.geaendert()

        dialog.connect("response", antwort)
        dialog.present(self.get_root())

    # ------------------------------------------------------------ Auswertung

    def _baue_auswertung(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=24,
                      margin_bottom=24, margin_start=24, margin_end=24)
        titel = Gtk.Label(label="Auswertung", xalign=0)
        titel.add_css_class("title-1")
        box.append(titel)
        self.a_uebersicht = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.a_uebersicht.add_css_class("boxed-list")
        box.append(self.a_uebersicht)
        self.a_hinweis = Gtk.Label(xalign=0, wrap=True)
        self.a_hinweis.add_css_class("dim-label")
        box.append(self.a_hinweis)
        self.a_text = Gtk.TextView(editable=False, monospace=True, cursor_visible=False,
                                   wrap_mode=Gtk.WrapMode.NONE)
        box.append(Gtk.ScrolledWindow(child=self.a_text, vexpand=True))
        knopf = Gtk.Button(label="Neu berechnen", halign=Gtk.Align.START)
        knopf.connect("clicked", lambda *_: self._auswertung_berechnen())
        box.append(knopf)
        return box

    def _auswertung_berechnen(self):
        text, ergebnisse, ordner = gesamtauswertung()
        self.a_text.get_buffer().set_text(text)
        if ordner:
            self.a_hinweis.set_label("Ausgewertet werden alle Messreihen mit denselben "
                                     "Mess-Vorlagen: " + ", ".join(p.name for p in ordner) + ".")
        else:
            self.a_hinweis.set_label("Noch keine Messungen in dieser Messreihe.")
        while (z := self.a_uebersicht.get_row_at_index(0)) is not None:
            self.a_uebersicht.remove(z)

        def zeile(titel, untertitel, ok):
            r = Adw.ActionRow(title=titel, subtitle=untertitel)
            symbol = {True: "emblem-ok-symbolic", False: "dialog-warning-symbolic",
                      None: "media-record-symbolic"}[ok]
            r.add_prefix(Gtk.Image(icon_name=symbol))
            self.a_uebersicht.append(r)

        csvs = {p.stem for o in ordner for p in o.glob("*.csv")}
        fehlt = [s["titel"] for s in FESTE_SCHRITTE if not s["optional"] and s["id"] not in csvs]
        zeile("Eigene Messungen und Kontrollen",
              "vollständig" if not fehlt else "es fehlen: " + ", ".join(fehlt), not fehlt)
        personen = sorted({c.split("-")[1] for c in csvs if c.startswith("fremd-")})
        if not personen:
            zeile("Andere Personen", "noch keine gemessen, mindestens eine ist nötig, besser "
                  "zwei bis drei aus der Familie", False)
        else:
            zusatz = "" if len(personen) >= 2 else ", weitere machen das Ergebnis belastbarer"
            zeile("Andere Personen", f"{len(personen)} gemessen: "
                  + ", ".join(p.capitalize() for p in personen) + zusatz, True)
        if not any(e.get("ok") is not None for e in ergebnisse):
            zeile("Entscheidung", "offen, bis andere Personen gemessen sind", None)
        for e in ergebnisse:
            if e.get("ok") is None:
                continue
            text = (f"WEITER, empfohlene Schwelle {komma(e['schwelle'], 2)}" if e["ok"]
                    else "Kriterium nicht erfüllt")
            zeile(f"Entscheidung {e['modell']}", text, e["ok"])
