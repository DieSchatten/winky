"""Messseiten des Kalibrierwerkzeugs: Schritte mit Anleitung, Hinweisen im Kamerabild,
Countdown, automatischem Weiter und Auswertung. Gespeichert werden nur Zahlen (CSV des
Messwerkzeugs) und bei Zeichen-Schritten die Zeitpunkte der Hinweise (<schritt>.signale.json).
"""

import json
import os
import time

from gi.repository import Adw, GLib, Gtk

import messumgebung as umgebung
from prozess import Prozess
from vorschau import Vorschau

SIGNALE = [3, 7, 11, 15, 19]   # Sekunden nach Messbeginn


def schritt(id, titel, gruppe, anleitung, dauer=20, countdown=3, optional=False, signal=None,
            signal_dauer=0.8, hinweis=None, aufgaben=None, lesetext=None, tipptext=None,
            signal_zeiten=None):
    """anleitung: kurze Sätze. Im Bild: signal zu den Zeiten SIGNALE bzw. signal_zeiten (werden
    gespeichert), hinweis während der ganzen Messung, aufgaben nacheinander. lesetext: zum Lesen;
    tipptext: zum Abtippen ins Eingabefeld (wird nicht gespeichert)."""
    return dict(id=id, titel=titel, gruppe=gruppe, anleitung=anleitung, dauer=dauer,
                countdown=countdown, optional=optional, signal=signal,
                signale=(signal_zeiten or SIGNALE) if signal else [], signal_dauer=signal_dauer,
                hinweis=hinweis,
                aufgaben=aufgaben or [], lesetext=lesetext, tipptext=tipptext)


class MessSeite(Gtk.Box):
    """Schritte links, Ablauf rechts. Unterklassen setzen ORDNER, SCHRITTE, BEFEHL,
    AUSWERTEN (Modul mit kurztext(pfad) und auswertung(ordner)) und live_text(st)."""

    ORDNER = None
    SCHRITTE = []
    BEFEHL = None
    AUSWERTEN = None

    def live_text(self, st):
        return "", True

    def status_merken(self, st):
        """Unterklassen: Rückmeldung je Bild (z. B. „✓ Erkannt“), bei Messungen aufgerufen."""

    def reihen_ordner(self):
        return umgebung.MESSUNGEN / self.ORDNER

    def neue_reihe(self):
        basis = time.strftime("%Y-%m-%d_%H%M%S")
        for i in range(1, 100):
            ordner = self.reihen_ordner() / (basis if i == 1 else f"{basis}-{i}")
            try:
                ordner.mkdir(mode=0o700, parents=True, exist_ok=False)
                return ordner
            except FileExistsError:
                continue
        raise RuntimeError("kein freier Name für die Messreihe")

    def __init__(self, melde):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.melde = melde
        self.lauf = None
        self.lauf_schritt = None
        self.vorschau_lauf = False
        self.nach_vorschau = None
        self.countdown_id = None
        self.zeit_ids = []          # geplante Hinweise im Bild
        self.signale = []
        self.start_unix = None
        self.schritt_aktuell = None
        self.reihen_ordner().mkdir(mode=0o700, parents=True, exist_ok=True)
        vorhandene = sorted(p for p in self.reihen_ordner().iterdir() if p.is_dir())
        self.ordner = vorhandene[-1] if vorhandene else self.neue_reihe()

        leiste = Gtk.Box(spacing=8, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
        self.reihe_label = Gtk.Label(xalign=0)
        leiste.append(self.reihe_label)
        knopf_neu = Gtk.Button(icon_name="document-new-symbolic",
                               tooltip_text="Neue Messreihe beginnen")
        knopf_neu.connect("clicked", lambda *_: self._neue_reihe())
        leiste.append(knopf_neu)
        self.append(leiste)

        teiler = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, position=300, vexpand=True)
        self.liste = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.liste.add_css_class("navigation-sidebar")
        self.liste.set_header_func(self._kopfzeile)
        self.liste.connect("row-selected", self._zeile_gewaehlt)
        teiler.set_start_child(Gtk.ScrolledWindow(child=self.liste,
                                                  hscrollbar_policy=Gtk.PolicyType.NEVER))
        teiler.set_shrink_start_child(False)
        teiler.set_resize_start_child(False)
        self.stapel = Gtk.Stack()
        self.stapel.add_named(self._baue_schrittseite(), "schritt")
        self.stapel.add_named(self._baue_auswertung(), "auswertung")
        teiler.set_end_child(self.stapel)
        self.append(teiler)
        self._liste_aufbauen()

    # Dateien

    def csv(self, sid):
        return self.ordner / f"{sid}.csv"

    def signal_datei(self, sid):
        return self.ordner / f"{sid}.signale.json"

    def _neue_reihe(self):
        if self.beschaeftigt():
            return
        self.ordner = self.neue_reihe()
        self.schritt_aktuell = None
        self._liste_aufbauen()
        self.melde(f"Neue Messreihe {self.ordner.name}")

    # Seitenleiste

    def status(self, s):
        pfad = self.csv(s["id"])
        if not pfad.exists():
            return "media-record-symbolic", "freiwillig" if s["optional"] else "offen", False
        return "emblem-ok-symbolic", self.AUSWERTEN.kurztext(pfad), True

    def _liste_aufbauen(self, auswahl=None):
        self.reihe_label.set_label(f"Messreihe {self.ordner.name}")
        auswahl = auswahl or (self.schritt_aktuell["id"] if self.schritt_aktuell else None)
        while (zeile := self.liste.get_row_at_index(0)) is not None:
            self.liste.remove(zeile)
        ziel = None
        for s in self.SCHRITTE:
            symbol, untertitel, _ = self.status(s)
            zeile = Adw.ActionRow(title=s["titel"], subtitle=untertitel)
            zeile.add_prefix(Gtk.Image(icon_name=symbol))
            zeile.schritt, zeile.gruppe = s, s["gruppe"]
            self.liste.append(zeile)
            if s["id"] == auswahl:
                ziel = zeile
        ausw = Adw.ActionRow(title="Auswertung", subtitle="Ergebnis und Entscheidung")
        ausw.add_prefix(Gtk.Image(icon_name="view-refresh-symbolic"))
        ausw.schritt, ausw.gruppe = None, "Ergebnis"
        self.liste.append(ausw)
        if auswahl == "auswertung":
            ziel = ausw
        self.liste.select_row(ziel or self.liste.get_row_at_index(0))

    def _kopfzeile(self, zeile, davor):
        if davor is None or davor.gruppe != zeile.gruppe:
            label = Gtk.Label(label=zeile.gruppe, xalign=0, margin_start=12, margin_bottom=4,
                              margin_top=14 if davor else 6)
            label.add_css_class("heading")
            zeile.set_header(label)
        else:
            zeile.set_header(None)

    def _zeile_gewaehlt(self, _liste, zeile):
        if zeile is None:
            return
        if zeile.schritt is None:
            self.schritt_aktuell = None
            self.stapel.set_visible_child_name("auswertung")
            self._auswertung_berechnen()
        else:
            self.schritt_aktuell = zeile.schritt
            self.stapel.set_visible_child_name("schritt")
            self._schrittseite_fuellen()

    # Schrittseite

    def _baue_schrittseite(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=24,
                      margin_bottom=24, margin_start=24, margin_end=24)
        self.s_gruppe = Gtk.Label(xalign=0)
        self.s_gruppe.add_css_class("dim-label")
        self.s_titel = Gtk.Label(xalign=0)
        self.s_titel.add_css_class("title-1")
        so_gehts = Gtk.Label(label="So geht’s", xalign=0)
        so_gehts.add_css_class("heading")
        self.s_anleitung = Gtk.Label(xalign=0, wrap=True, max_width_chars=80)
        for w in (self.s_gruppe, self.s_titel, so_gehts, self.s_anleitung):
            box.append(w)
        self.s_lesetext = Gtk.Label(xalign=0, wrap=True, max_width_chars=70, selectable=False,
                                    margin_top=12, margin_bottom=12, margin_start=16, margin_end=16)
        self.s_lesetext.add_css_class("title-4")
        self.s_lesekarte = Gtk.Frame(child=self.s_lesetext)
        self.s_lesekarte.add_css_class("view")
        box.append(self.s_lesekarte)
        self.s_tippfeld = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD, top_margin=8, bottom_margin=8,
                                       left_margin=8, right_margin=8)
        self.s_tippfeld.set_size_request(-1, 90)
        self.s_tippkarte = Gtk.Frame(child=self.s_tippfeld)
        box.append(self.s_tippkarte)
        self.vorschau = Vorschau()
        box.append(self.vorschau)
        self.s_bildhinweis = Gtk.Label(xalign=0, label="Das Kamerabild wird nur angezeigt und "
                                       "nirgends gespeichert. Die rosa Punkte zeigen, wo die "
                                       "Lider erkannt werden.")
        self.s_bildhinweis.add_css_class("dim-label")
        self.s_bildhinweis.add_css_class("caption")
        box.append(self.s_bildhinweis)
        self.live = Gtk.Label(xalign=0)
        box.append(self.live)
        self.fortschritt = Gtk.ProgressBar()
        box.append(self.fortschritt)
        knoepfe = Gtk.Box(spacing=8)
        self.k_vorschau = Gtk.ToggleButton(label="Kamerabild ansehen")
        self.k_vorschau.set_tooltip_text("Vor dem Start prüfen, ob die rosa Punkte auf den Lidern liegen")
        self.k_vorschau.connect("toggled", self._vorschau_umschalten)
        self.k_start = Gtk.Button(label="Starten")
        self.k_start.add_css_class("suggested-action")
        self.k_start.connect("clicked", lambda *_: self.starten())
        self.k_abbruch = Gtk.Button(label="Abbrechen")
        self.k_abbruch.add_css_class("destructive-action")
        self.k_abbruch.connect("clicked", lambda *_: self.abbrechen())
        self.k_weiter = Gtk.Button(label="Überspringen", hexpand=True, halign=Gtk.Align.END)
        self.k_weiter.connect("clicked", lambda *_: self._naechster())
        for k in (self.k_start, self.k_abbruch, self.k_vorschau, self.k_weiter):
            knoepfe.append(k)
        box.append(knoepfe)
        self.ergebnis = Gtk.Label(xalign=0, wrap=True, selectable=True)
        box.append(self.ergebnis)
        self.k_loeschen = Gtk.Button(label="Ergebnis löschen", halign=Gtk.Align.START)
        self.k_loeschen.add_css_class("flat")
        self.k_loeschen.connect("clicked", lambda *_: self._ergebnis_loeschen())
        box.append(self.k_loeschen)
        return Gtk.ScrolledWindow(child=box, hscrollbar_policy=Gtk.PolicyType.NEVER)

    def _schrittseite_fuellen(self):
        s = self.schritt_aktuell
        nr = self.SCHRITTE.index(s) + 1
        self.s_gruppe.set_label(f"Schritt {nr} von {len(self.SCHRITTE)} · {s['gruppe']}"
                                + (" · freiwillig" if s["optional"] else ""))
        self.s_titel.set_label(s["titel"])
        self.s_anleitung.set_label("\n".join(f"{i}.  {satz}" for i, satz in
                                             enumerate(s["anleitung"], 1)))
        self.s_lesetext.set_label(s.get("lesetext") or s.get("tipptext") or "")
        self.s_lesekarte.set_visible(bool(s.get("lesetext") or s.get("tipptext")))
        self.s_tippkarte.set_visible(bool(s.get("tipptext")))
        self.s_tippfeld.get_buffer().set_text("")
        erledigt = self.status(s)[2]
        self.ergebnis.set_label(self._ergebnis_text(s) if erledigt else "")
        if not self.beschaeftigt():
            self.live.set_label("")
            self.fortschritt.set_fraction(0)
            self.vorschau.leeren()
            self._bild_zeigen(True)
        self._knoepfe_aktualisieren()

    def _bild_zeigen(self, ja):
        """Beim Lesen verschwindet das Kamerabild, damit der Blick auf dem Text bleibt."""
        self.vorschau.set_visible(ja)
        self.s_bildhinweis.set_visible(ja)

    def _ergebnis_text(self, s):
        text = f"Gespeichert: {self.AUSWERTEN.kurztext(self.csv(s['id']))}."

        if s["signale"]:
            try:
                n = len(json.loads(self.signal_datei(s["id"]).read_text()))
            except (OSError, ValueError):
                n = 0
            text += f" {n} Aufforderungen."
        return text

    def _knoepfe_aktualisieren(self):
        s = self.schritt_aktuell
        messung = self.countdown_id is not None or (self.lauf is not None and not self.vorschau_lauf)
        erledigt = self.status(s)[2] if s else False
        self.k_start.set_label("Wiederholen" if erledigt else "Starten")
        self.k_start.set_sensitive(s is not None and not messung)
        self.k_start.set_visible(not messung)
        self.k_abbruch.set_visible(messung)
        self.k_vorschau.set_sensitive(not messung)
        self.k_loeschen.set_visible(erledigt)
        self.k_loeschen.set_sensitive(not self.beschaeftigt())
        self.k_weiter.set_label("Weiter" if erledigt else "Überspringen")
        self.k_weiter.set_sensitive(not self.beschaeftigt())
        self.liste.set_sensitive(not messung)

    # Abläufe

    def beschaeftigt(self):
        return self.lauf is not None or self.countdown_id is not None

    def _vorschau_umschalten(self, knopf):
        if knopf.get_active():
            if self.lauf is None:
                self.vorschau_lauf = True
                self._bild_zeigen(True)
                self._lauf_starten([self.BEFEHL, "--name", "vorschau", "--dauer", "300"], None)
        elif self.lauf and self.vorschau_lauf:
            self.lauf.abbrechen()

    def starten(self):
        s = self.schritt_aktuell
        if s is None or self.countdown_id is not None:
            return
        if self.lauf and self.vorschau_lauf:
            self.nach_vorschau = s
            self.k_vorschau.set_active(False)
            return
        if self.lauf:
            return
        self.start_unix = None
        self._countdown(s, s["countdown"])

    def _countdown(self, s, rest):
        self.countdown_id = None
        if rest <= 0:
            self._messung_starten(s)
            return
        self.vorschau.leeren(f"Start in {rest}")
        self.live.set_label("")
        self.fortschritt.set_fraction(0)
        self.countdown_id = GLib.timeout_add(1000, self._countdown_tick, s, rest - 1)
        self._knoepfe_aktualisieren()

    def _countdown_tick(self, s, rest):
        self.countdown_id = None
        self._countdown(s, rest)
        return False

    def _messung_starten(self, s):
        teil = self.csv(s["id"]).with_suffix(".csv.teil")
        self.signale, self.start_unix = [], None
        self.vorschau_lauf = False
        self._lauf_starten([self.BEFEHL, "--name", s["id"], "--dauer", str(s["dauer"]),
                            "--csv", umgebung.werkzeug_pfad(teil)], s)

    def _lauf_starten(self, args, s):
        if not umgebung.kamera_vorhanden():
            self.melde("IR-Kamera nicht gefunden")
            self.k_vorschau.set_active(False)
            self.vorschau_lauf = False
            self._knoepfe_aktualisieren()
            return
        self.lauf_schritt = s
        self.live.set_label("Kamera und Modelle starten …")
        self.vorschau.hinweis("Kamera startet …")
        self.fortschritt.set_fraction(0)
        try:
            self.lauf = Prozess(umgebung.messwerkzeug_befehl(args), self._bei_bild,
                                self._bei_status, self._bei_ende)
        except (OSError, RuntimeError) as e:
            self.lauf = None
            self.vorschau_lauf = False
            self.melde(f"Start fehlgeschlagen: {e}")
        self._knoepfe_aktualisieren()

    def abbrechen(self):
        if self.countdown_id is not None:
            GLib.source_remove(self.countdown_id)
            self.countdown_id = None
            self.vorschau.hinweis("Abgebrochen")
            self._knoepfe_aktualisieren()
        elif self.lauf:
            self.lauf.abbrechen()

    # Hinweise im Bild

    def _hinweise_planen(self, s):
        """Startet Hinweise und Aufforderungen, sobald die Kamera läuft."""
        if s["hinweis"]:
            self.vorschau.hinweis(s["hinweis"])
        if s.get("lesetext") or s.get("tipptext"):
            self._bild_zeigen(False)
        if s.get("tipptext"):
            self.s_tippfeld.grab_focus()
        for sek in s["signale"]:
            self._planen(sek, self._signal_zeigen, s)
        if s["aufgaben"]:
            takt = s["dauer"] / len(s["aufgaben"])
            for i, text in enumerate(s["aufgaben"]):
                self._planen(i * takt, self._text_zeigen, text)

    def _planen(self, sek, funktion, *args):
        if sek <= 0:
            funktion(*args)
        else:
            self.zeit_ids.append(GLib.timeout_add(int(sek * 1000), funktion, *args))

    def _text_zeigen(self, text):
        if self.lauf is not None:
            self.vorschau.hinweis(text)
        return False

    def _signal_zeigen(self, s):
        if self.lauf is None:
            return False
        self.signale.append(int(time.time() * 1000))
        self.vorschau.hinweis(s["signal"])
        self.zeit_ids.append(GLib.timeout_add(int(s["signal_dauer"] * 1000),
                                              self._signal_weg, s["signal"]))
        return False

    def _signal_weg(self, text):
        if self.vorschau.label.get_label() == text:
            self.vorschau.label.set_visible(False)
        return False

    def _hinweise_stoppen(self):
        for i in self.zeit_ids:
            if GLib.MainContext.default().find_source_by_id(i):
                GLib.source_remove(i)
        self.zeit_ids = []

    # Rückmeldungen

    def _bei_bild(self, w, h, daten):
        if self.lauf:
            self.vorschau.zeige(w, h, daten)

    def _bei_status(self, st):
        if not self.lauf:
            return
        if self.start_unix is None and not self.vorschau_lauf and self.lauf_schritt:
            self.start_unix = int(time.time() * 1000)
            self._hinweise_planen(self.lauf_schritt)
        if not self.vorschau_lauf and self.lauf_schritt:
            self.status_merken(st)
        text, gut = self.live_text(st)
        self.live.set_label(text)
        self.live.remove_css_class("gut")
        self.live.remove_css_class("warnung")
        self.live.add_css_class("gut" if gut else "warnung")
        if st.get("dauer") and not self.vorschau_lauf:
            self.fortschritt.set_fraction(min(1.0, float(st.get("t", 0)) / float(st["dauer"])))

    def _bei_ende(self, lauf, rc):
        s, war_vorschau = self.lauf_schritt, self.vorschau_lauf
        self.lauf, self.lauf_schritt, self.vorschau_lauf = None, None, False
        self._hinweise_stoppen()
        self._bild_zeigen(True)
        self.vorschau.leeren()
        if war_vorschau:
            self.live.set_label("")
            self.k_vorschau.set_active(False)
            nach, self.nach_vorschau = self.nach_vorschau, None
            if nach is not None:
                self._knoepfe_aktualisieren()
                self._countdown(nach, nach["countdown"])
                return
        elif s is not None:
            teil = self.csv(s["id"]).with_suffix(".csv.teil")
            if rc == 0 and teil.exists():
                if s["signale"]:
                    tmp = self.signal_datei(s["id"]).with_suffix(".neu")
                    tmp.write_text(json.dumps(self.signale))
                    os.chmod(tmp, 0o600)
                    tmp.replace(self.signal_datei(s["id"]))
                teil.replace(self.csv(s["id"]))
                self.vorschau.hinweis("Fertig")
                self.fortschritt.set_fraction(1)
                self.melde(f"„{s['titel']}“ gespeichert, weiter mit dem nächsten Schritt")
                GLib.timeout_add(1500, self._weiter_nach, s)
            else:
                teil.unlink(missing_ok=True)
                self.vorschau.hinweis("Abgebrochen" if lauf.abgebrochen else "Fehlgeschlagen")
                if not lauf.abgebrochen:
                    self.ergebnis.set_label(f"Die Messung ist fehlgeschlagen:\n"
                                            f"{lauf.fehlermeldung(rc)}")
            self._liste_aufbauen(auswahl=s["id"])
            if rc == 0:
                self.ergebnis.set_label(self._ergebnis_text(s))
        self._knoepfe_aktualisieren()

    def _weiter_nach(self, s):
        """Nach einer gelungenen Messung zum nächsten offenen Schritt (nicht starten)."""
        if not self.beschaeftigt() and self.schritt_aktuell is s:
            self._naechster()
        return False

    def _ergebnis_loeschen(self):
        s = self.schritt_aktuell
        if s:
            self.csv(s["id"]).unlink(missing_ok=True)
            self.signal_datei(s["id"]).unlink(missing_ok=True)
            self._liste_aufbauen(auswahl=s["id"])
            self.melde(f"Ergebnis „{s['titel']}“ gelöscht")

    def _naechster(self):
        ids = [s["id"] for s in self.SCHRITTE]
        start = ids.index(self.schritt_aktuell["id"]) + 1 if self.schritt_aktuell else 0
        for s in self.SCHRITTE[start:] + self.SCHRITTE[:start]:
            if not self.status(s)[2] and not s["optional"]:
                self._liste_aufbauen(auswahl=s["id"])
                return
        self._liste_aufbauen(auswahl="auswertung")

    # Auswertung

    def _baue_auswertung(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=24,
                      margin_bottom=24, margin_start=24, margin_end=24)
        titel = Gtk.Label(label="Auswertung", xalign=0)
        titel.add_css_class("title-1")
        box.append(titel)
        self.a_uebersicht = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.a_uebersicht.add_css_class("boxed-list")
        box.append(self.a_uebersicht)
        self.a_text = Gtk.TextView(editable=False, monospace=True, cursor_visible=False,
                                   wrap_mode=Gtk.WrapMode.NONE)
        box.append(Gtk.ScrolledWindow(child=self.a_text, vexpand=True))
        knopf = Gtk.Button(label="Neu berechnen", halign=Gtk.Align.START)
        knopf.connect("clicked", lambda *_: self._auswertung_berechnen())
        box.append(knopf)
        return box

    def _auswertung_berechnen(self):
        text, ergebnisse = self.AUSWERTEN.auswertung(self.ordner)
        self.a_text.get_buffer().set_text(text)
        while (z := self.a_uebersicht.get_row_at_index(0)) is not None:
            self.a_uebersicht.remove(z)

        def zeile(titel, untertitel, ok):
            r = Adw.ActionRow(title=titel, subtitle=untertitel)
            symbol = {True: "emblem-ok-symbolic", False: "dialog-warning-symbolic",
                      None: "media-record-symbolic"}[ok]
            r.add_prefix(Gtk.Image(icon_name=symbol))
            self.a_uebersicht.append(r)

        fehlt = [s["titel"] for s in self.SCHRITTE if not s["optional"] and not self.csv(s["id"]).exists()]
        zeile("Messungen", "vollständig" if not fehlt else "es fehlen: " + ", ".join(fehlt),
              not fehlt)
        for e in ergebnisse:
            zeile(e["verfahren"], e["kurz"], e["ok"])
