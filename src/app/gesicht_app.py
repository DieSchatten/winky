#!/usr/bin/env python3
"""Winky: Einrichtung und Verwaltung der Gesichtsentsperrung.

Ein Assistent führt Menschen ohne Technikwissen durch die Einrichtung; Technik steht unter
„Erweitert“. Das eigene Gesicht verwaltet jeder Benutzer mit seinem Passwort, systemweite
Einstellungen brauchen das Administratorpasswort. Die App selbst läuft ohne besondere Rechte.
"""

import math
import os
import subprocess
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, GObject, Gtk  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import system  # noqa: E402
import umgebung  # noqa: E402
from prozess import Prozess  # noqa: E402
from sprache import _, ngettext  # noqa: E402
from vorschau import RingVorschau, css_laden, komma  # noqa: E402

GEGENPROBE_ABSTAND = 0.10   # so weit muss eine andere Person unter der Schwelle bleiben
SCHWELLE_MAX = 0.95
HINWEIS = "/usr/libexec/winky/winky-hinweis"
APP_ID = "io.github.dieschatten.Winky"

# Was während einer Aufnahme unter dem Bild steht (aus dem Feld "grund" des Prüfdienstes)
TIPPS = {
    "ok": _("Looks good"),
    "kein_gesicht": _("No face visible. Look at the camera."),
    "zu_klein": _("Move a little closer to the camera"),
    "gedreht": _("Turn your head a little less to the side"),
    "geneigt": _("Hold your head a little straighter"),
    "unsicher": _("Look straight at the camera"),
    "punkte_unsicher": _("The face is partly covered"),
    "ueberbelichtet": _("Move a little further away from the camera"),
    "keine_punkte": _("The face isn’t fully visible"),
}

ABLAEUFE = {
    "einlernen": {
        "titel": _("Record your face"),
        "schritte": [_("Sit at your computer the way you usually do and look at the camera."),
                     _("Click “Start recording” and enter your password."),
                     _("Slowly turn your head a little to the left, right, up and down.")],
        "hinweis": _("Recording takes 25 seconds. Winky doesn’t save any photos, only numbers "
                     "that only the system can read."),
        "knopf": _("Start recording"), "nochmal": _("Record again"),
    },
    "ergaenzen": {
        "titel": _("Add to your face"),
        "schritte": [_("Give the addition a name below and click “Start adding”, then enter "
                       "your password."),
                     _("First look at the camera as usual for a few seconds, the way Winky "
                       "already knows you. That’s how Winky knows it’s you."),
                     _("When “Now change it” appears below the picture: put on your glasses, "
                       "change the light or sit a little differently, and slowly move your "
                       "head.")],
        "hinweis": _("Takes 25 seconds. Your previous recording stays. Winky only adds what "
                     "matches your face, so it won’t add anyone else by mistake. Up to three "
                     "additions, each can be deleted again."),
        "knopf": _("Start adding"), "nochmal": _("Add more"),
    },
    "testen": {
        "titel": _("Try it out"),
        "schritte": [_("Click “Try it out” and enter your password."),
                     _("Just look at the camera.")],
        "hinweis": _("The lock screen will open just as quickly later on."),
        "knopf": _("Try it out"), "nochmal": _("Try again"),
    },
    "gegenprobe": {
        "titel": _("Check with a second person"),
        "schritte": [_("Ask someone to join you, ideally someone who looks like you, for "
                       "example a family member."),
                     _("Click “Start check” and enter your password."),
                     _("Then move out of the picture within 5 seconds. The other person looks "
                       "at the camera for 10 seconds.")],
        "hinweis": _("Winky must not recognize this person. No picture is saved, only how "
                     "similar they look to you for Winky. Optional, but recommended."),
        "knopf": _("Start check"), "nochmal": _("Check again"),
    },
    "geste-testen": {
        "titel": _("Test face and ✌"),
        "schritte": [_("Click “Start test” and enter your password."),
                     _("Look at the camera and show the V sign next to your face: index and "
                       "middle finger up, palm facing the camera."),
                     _("Hold it until “✓” appears.")],
        "hinweis": _("Everyone who wants to confirm sudo this way does this test for "
                     "themselves."),
        "knopf": _("Start test"), "nochmal": _("Test again"),
    },
}

# Assistent: Reihenfolge der Schritte; gezählt werden die zwischen Willkommen und Fertig
SCHRITTE = ["willkommen", "kamera", "einlernen", "testen", "gegenprobe", "einschalten", "sudo",
            "fertig"]
GEZAEHLT = SCHRITTE[1:-1]


def datum(ts):
    if not ts:
        return _("unknown")
    t = time.localtime(ts)
    heute = time.localtime()
    if t[:3] == heute[:3]:
        return _("today at {time}").format(time=time.strftime("%H:%M", t))
    if t[:3] == time.localtime(time.time() - 86400)[:3]:
        return _("yesterday at {time}").format(time=time.strftime("%H:%M", t))
    # Übersetzbares strftime-Format für Datum und Uhrzeit
    return time.strftime(_("%Y-%m-%d %H:%M"), t)


def text(inhalt, *klassen, mitte=False, breite=None):
    lbl = Gtk.Label(label=inhalt, wrap=True, xalign=0.5 if mitte else 0,
                    justify=Gtk.Justification.CENTER if mitte else Gtk.Justification.LEFT)
    if breite:
        lbl.set_max_width_chars(breite)
    for k in klassen:
        lbl.add_css_class(k)
    return lbl


def textzeile(titel, untertitel="", symbol=None):
    r = Adw.ActionRow(title=titel, subtitle=untertitel)
    r.set_subtitle_selectable(True)
    if symbol:
        r.add_prefix(Gtk.Image(icon_name=symbol))
    return r


def weiterzeile(titel, untertitel, aktion, symbol=None):
    """Zeile, die per Klick eine Seite oder einen Ablauf öffnet."""
    r = Adw.ActionRow(title=titel, subtitle=untertitel, activatable=True)
    if symbol:
        r.add_prefix(Gtk.Image(icon_name=symbol))
    r.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
    r.connect("activated", lambda *_: aktion())
    return r


class SchalterZeile(Adw.ActionRow):
    """Zeile mit Schalter wie Adw.SwitchRow, dazu wahlweise ⓘ mit ausführlichem Hinweis und
    weitere Knöpfe vor dem Schalter. Gesperrt wird nur der Schalter: der Hinweis bleibt lesbar."""

    __gtype_name__ = "WinkySchalterZeile"
    active = GObject.Property(type=bool, default=False)

    def __init__(self, titel, untertitel="", symbol=None, info=None, warnung=False):
        super().__init__(title=titel, subtitle=untertitel)
        if symbol:
            bild = Gtk.Image(icon_name=symbol)
            if warnung:
                bild.add_css_class("warning")
            self.add_prefix(bild)
        if info:
            label = Gtk.Label(label=info, wrap=True, max_width_chars=44, xalign=0,
                              selectable=True, margin_top=6, margin_bottom=6, margin_start=6,
                              margin_end=6)
            ik = Gtk.MenuButton(icon_name="dialog-information-symbolic", valign=Gtk.Align.CENTER,
                                popover=Gtk.Popover(child=label))
            ik.add_css_class("flat")
            ik.add_css_class("circular")
            ik.set_tooltip_text(_("What this means"))
            self.add_suffix(ik)
        self.schalter = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.bind_property("active", self.schalter, "active",
                           GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        self._vor_schalter = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        self.add_suffix(self._vor_schalter)
        self.add_suffix(self.schalter)
        self.set_activatable_widget(self.schalter)

    def vor_schalter(self, widget):
        self._vor_schalter.append(widget)

    def get_active(self):
        return self.active

    def set_active(self, wert):
        self.active = bool(wert)

    def set_sensitive(self, wert):
        self.schalter.set_sensitive(wert)
        self.set_activatable(wert)

    def get_sensitive(self):
        return self.schalter.get_sensitive()


def knopf(beschriftung, aktion, *klassen):
    k = Gtk.Button(label=beschriftung, valign=Gtk.Align.CENTER)
    k.connect("clicked", lambda *_: aktion())
    for c in klassen:
        k.add_css_class(c)
    return k


def rollbar(inhalt, breite=680):
    clamp = Adw.Clamp(maximum_size=breite, child=inhalt)
    return Gtk.ScrolledWindow(child=clamp, hscrollbar_policy=Gtk.PolicyType.NEVER,
                              vexpand=True)


def seite(titel, tag, inhalt, unten=None):
    ansicht = Adw.ToolbarView()
    ansicht.add_top_bar(Adw.HeaderBar())
    ansicht.set_content(inhalt)
    if unten is not None:
        ansicht.add_bottom_bar(unten)
    return Adw.NavigationPage(title=titel, tag=tag, child=ansicht)


def stand(z):
    """Was von der Einrichtung erledigt ist (für Assistent und Startseite)."""
    test = (z.eingelernt and z.test_ok > 0 and z.test_ok >= z.eingelernt_am
            and not (z.schwelle > 0 and 0 < z.test_wert < z.schwelle))
    if z.gegenprobe_wert is None or not z.eingelernt or \
            (z.test_wert and z.gegenprobe_wert >= z.test_wert - 0.10):
        gegenprobe = None   # so ähnlich wie das eigene Gesicht: zählt nicht (meist man selbst)
    else:
        gegenprobe = z.gegenprobe_wert < z.schwelle - GEGENPROBE_ABSTAND
    geste = z.eingelernt and z.geste_ok > 0 and z.geste_ok >= z.eingelernt_am
    return {"kamera": bool(z.kamera), "einlernen": z.eingelernt, "testen": test,
            "gegenprobe": gegenprobe, "geste": geste}


def strengere_schwelle(wert):
    """Schwelle, bei der eine Person mit diesem Wert genug Abstand hat."""
    return math.ceil((wert + GEGENPROBE_ABSTAND + 0.02) * 100) / 100


def strenger_moeglich(z):
    """Nur strenger stellen, wenn das eigene Gesicht danach noch sicher erkannt wird."""
    if z.gegenprobe_wert is None:
        return False
    neu = strengere_schwelle(z.gegenprobe_wert)
    return neu <= SCHWELLE_MAX and (not z.test_wert or neu <= z.test_wert - 0.05)




class ErgaenzungsListe(Adw.PreferencesGroup):
    """Benannte Ergänzungen mit Löschknopf (Abschnitt Gesicht und Seite „Gesicht ergänzen“)."""

    def __init__(self, fenster):
        super().__init__(title=_("Your additions"),
                         description=_("Extra recordings, for example with glasses. Delete one if "
                                       "you no longer need it."))
        self.fenster = fenster
        self.zeilen = []
        self._stand = None

    def zeigen(self, liste, laeuft):
        stand = tuple((e.get("id"), e.get("name"), e.get("anzahl")) for e in liste)
        if stand != self._stand:
            self._stand = stand
            for r in self.zeilen:
                self.remove(r)
            self.zeilen = []
            for e in liste:
                name = e.get("name") or _("Addition without a name")
                anzahl = int(e.get("anzahl", 0))
                zeile = textzeile(name, ngettext("{n} image, {date}", "{n} images, {date}",
                                                 anzahl).format(n=anzahl, date=datum(e.get("zeit"))),
                                  "list-add-symbolic")
                weg = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER,
                                 tooltip_text=_("Delete"))
                weg.add_css_class("flat")
                weg.connect("clicked", lambda _b, e=e, n=name:
                            self.fenster.ergaenzung_loeschen_fragen(e, n))
                zeile.add_suffix(weg)
                zeile.knopf = weg
                self.add(zeile)
                self.zeilen.append(zeile)
        for r in self.zeilen:
            r.knopf.set_sensitive(not laeuft)
        self.set_visible(bool(liste))


class KameraAblauf(Gtk.Box):
    """Anleitung, Kamerabild, Fortschritt und Ergebnis für einen Ablauf mit der Kamera
    (einlernen, testen, gegenprobe, geste-testen)."""

    def __init__(self, fenster, art, mit_titel=True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.fenster = fenster
        self.titel = text("", "title-1")
        self.titel.set_visible(mit_titel)
        self.append(self.titel)
        self.anleitung = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.anleitung)
        self.hinweis = text("", "dim-label")
        self.append(self.hinweis)
        # Rund ausgeschnitten, der Ring zeigt den Fortschritt
        self.vorschau = RingVorschau(300)
        self.vorschau.set_margin_top(6)
        self.append(self.vorschau)
        self.live = text("", "title-4", mitte=True)
        self.append(self.live)
        # Beim Ergänzen: Name, damit sich die Ergänzung später gezielt löschen lässt
        self.name_liste = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.name_liste.add_css_class("boxed-list")
        self.e_name = Adw.EntryRow(title=_("Name of the addition, for example “With glasses”"))
        self.name_liste.append(self.e_name)
        self.append(self.name_liste)
        knoepfe = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        self.k_start = knopf("", self.starten, "pill", "suggested-action")
        self.k_abbruch = knopf(_("Cancel"), self.abbrechen, "pill")
        knoepfe.append(self.k_start)
        knoepfe.append(self.k_abbruch)
        self.append(knoepfe)
        self.ergebnis = text("", "title-3", mitte=True)
        self.ergebnis.set_selectable(True)
        self.append(self.ergebnis)
        # Nur bei der zweiten Person: Winky strenger stellen, wenn sie zu ähnlich war
        self.k_strenger = knopf(_("Make Winky stricter"), fenster.strenger_einstellen,
                                "pill", "destructive-action")
        self.k_strenger.set_halign(Gtk.Align.CENTER)
        self.append(self.k_strenger)
        self.zusatz = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.append(self.zusatz)
        # Beim Ergänzen gleich sehen, was schon drin ist, und Überflüssiges löschen
        self.ergaenzungen = ErgaenzungsListe(fenster)
        self.ergaenzungen.set_margin_top(12)
        self.append(self.ergaenzungen)
        self.setze_art(art)

    def setze_art(self, art):
        self.art = art
        a = ABLAEUFE[art]
        self.titel.set_label(a["titel"])
        while (kind := self.anleitung.get_first_child()) is not None:
            self.anleitung.remove(kind)
        for i, schritt in enumerate(a["schritte"], 1):
            zeile = Gtk.Box(spacing=12)
            nummer = Gtk.Label(label=str(i), valign=Gtk.Align.START)
            nummer.add_css_class("schrittnummer")
            zeile.append(nummer)
            inhalt = text(schritt)
            inhalt.set_hexpand(True)
            zeile.append(inhalt)
            self.anleitung.append(zeile)
        self.hinweis.set_label(a["hinweis"])
        self.name_liste.set_visible(art == "ergaenzen")
        self.e_name.set_text("")
        self.zuruecksetzen()

    def zuruecksetzen(self):
        self.vorschau.leeren()
        self.live.set_label("")
        self.ergebnis.set_label("")

    def starten(self):
        if self.art != "gegenprobe":
            self.fenster.lauf_starten(self)
            return
        # Nie aus Versehen: erst bestätigen, dass die andere Person bereitsteht
        dialog = Adw.AlertDialog.new(
            _("Is the other person ready?"),
            _("After you enter your password, you have 5 seconds to move out of the picture. "
              "Then the other person looks at the camera for 10 seconds."))
        dialog.add_response("abbrechen", _("Cancel"))
        dialog.add_response("los", _("Start check"))
        dialog.set_response_appearance("los", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_close_response("abbrechen")
        dialog.connect("response", lambda _d, r: r == "los" and self.fenster.lauf_starten(self))
        dialog.present(self.fenster)
        self.bestaetigung = dialog

    def abbrechen(self):
        if self.fenster.gesicht_lauf and self.fenster.lauf_ansicht is self:
            self.fenster.gesicht_lauf.abbrechen()

    def aktualisieren(self, z, s, bereit, laeuft):
        a = ABLAEUFE[self.art]
        meiner = self.fenster.gesicht_lauf is not None and self.fenster.lauf_ansicht is self
        erledigt = {"einlernen": s["einlernen"], "testen": s["testen"],
                    "ergaenzen": bool(z.ergaenzt_am),
                    "gegenprobe": s["gegenprobe"] is not None, "geste-testen": s["geste"]}
        self.k_start.set_label(a["nochmal"] if erledigt[self.art] else a["knopf"])
        moeglich = bereit and (bool(z.kamera) if self.art == "einlernen" else z.eingelernt)
        self.k_start.set_sensitive(moeglich and not laeuft)
        self.k_start.set_visible(not meiner)
        self.k_abbruch.set_visible(meiner)
        self.k_strenger.set_visible(self.art == "gegenprobe" and s["gegenprobe"] is False
                                    and strenger_moeglich(z))
        self.k_strenger.set_sensitive(not laeuft)
        self.e_name.set_sensitive(not laeuft)
        self.ergaenzungen.zeigen(z.ergaenzungen or [] if self.art == "ergaenzen" else [], laeuft)
        if not meiner and not self.live.get_label():
            if not bereit:
                self.live.set_label(_("Winky isn’t fully installed."))
            elif not z.kamera:
                self.live.set_label(_("Set up the camera first."))
            elif self.art != "einlernen" and not z.eingelernt:
                self.live.set_label(_("Record your face first."))


class Fenster(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Winky")
        self.set_default_size(900, 760)
        self.set_size_request(360, 420)   # nötig für den Umbruch auf schmale Fenster
        css_laden()
        self.zustand = system.Zustand()
        self.aktion = None        # laufender Verwaltungsaufruf ohne Kamerabild
        self.gesicht_lauf = None  # Aufnehmen, Ausprobieren, zweite Person, ✌ (mit Kamerabild)
        self.lauf_ansicht = None  # KameraAblauf, der den laufenden Ablauf zeigt
        self.kamera_name = None   # Name aus der letzten Kamerasuche (nur zur Anzeige)
        self._schalter_sperre = False

        self.ablaeufe = []
        self.nav = Adw.NavigationView()
        self.nav.add(self._baue_start())
        self.nav.add(self._baue_einrichtung())
        self.nav.add(self._baue_kamera())
        # Schmales Fenster: Seitenleiste und Inhalt nacheinander statt nebeneinander
        schmal = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 600sp"))
        schmal.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(schmal)
        self.nav.connect("popped", self._seite_weg)
        self.toasts = Adw.ToastOverlay(child=self.nav)
        self.set_content(self.toasts)
        self.connect("close-request", self._schliessen)
        self.aktualisieren()
        if not self.zustand.eingelernt and self.zustand.installiert and self.zustand.dienst:
            self.einrichtung_oeffnen()
        GLib.timeout_add_seconds(15, self._regelmaessig)

    def melde(self, inhalt):
        self.toasts.add_toast(Adw.Toast(title=inhalt, timeout=6))

    def _regelmaessig(self):
        # Nicht, solange ein Dialog offen ist: das Auffrischen verschiebt ihn und setzt Schalter
        # zurück, ein Klick darauf ginge sonst ins Leere
        if not self.beschaeftigt() and self.get_visible_dialog() is None:
            self.aktualisieren()
        return True

    def beschaeftigt(self):
        return self.aktion is not None or self.gesicht_lauf is not None

    # Startseite: Seitenleiste mit Übersicht, Freigaben, Gesicht, Verlauf, Sicherheit, Erweitert

    ABSCHNITTE = (("uebersicht", _("Overview"), "go-home-symbolic"),
                  ("freigaben", _("Unlocks"), "system-lock-screen-symbolic"),
                  ("gesicht", _("Face"), "avatar-default-symbolic"),
                  ("verlauf", _("History"), "document-open-recent-symbolic"),
                  ("sicherheit", _("Security and help"), "security-high-symbolic"),
                  ("erweitert", _("Advanced"), "preferences-system-symbolic"))

    def _baue_start(self):
        inhalte = {"uebersicht": self._baue_uebersicht(), "freigaben": self._baue_freigaben(),
                   "gesicht": self._baue_gesicht(), "verlauf": self._baue_verlauf(),
                   "sicherheit": self._baue_sicherheit(), "erweitert": self._baue_erweitert()}
        self.abschnitte = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                                    vexpand=True)
        for sid, titel, _symbol in self.ABSCHNITTE:
            self.abschnitte.add_titled(inhalte[sid], sid, titel)

        # Seitenleiste: Winky-Symbol und Name oben, Abschnitte, „Über Winky“ unten
        self.leiste = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.leiste.add_css_class("navigation-sidebar")
        for sid, titel, symbol in self.ABSCHNITTE:
            zeile = Gtk.ListBoxRow()
            zeile.sid = sid
            box = Gtk.Box(spacing=12, margin_top=4, margin_bottom=4, margin_start=4)
            box.append(Gtk.Image(icon_name=symbol))
            box.append(Gtk.Label(label=titel, xalign=0))
            zeile.set_child(box)
            self.leiste.append(zeile)
        self.leiste.connect("row-activated", lambda _l, r: self.abschnitt_zeigen(r.sid))
        kopf = Gtk.Box(spacing=8)
        kopf.append(Gtk.Image(icon_name=APP_ID, pixel_size=24))
        kopf.append(text("Winky", "heading"))
        leiste_kopf = Adw.HeaderBar(title_widget=kopf)
        ueber = Gtk.Button(child=Adw.ButtonContent(icon_name="help-about-symbolic",
                                                   label=_("About Winky")),
                           margin_start=6, margin_end=6, margin_bottom=6)
        ueber.add_css_class("flat")
        ueber.connect("clicked", lambda *_: self.ueber_zeigen())
        leiste_ansicht = Adw.ToolbarView(content=Gtk.ScrolledWindow(
            child=self.leiste, hscrollbar_policy=Gtk.PolicyType.NEVER))
        leiste_ansicht.add_top_bar(leiste_kopf)
        leiste_ansicht.add_bottom_bar(ueber)
        leiste_ansicht.set_bottom_bar_style(Adw.ToolbarStyle.FLAT)

        self.inhalt_titel = Adw.WindowTitle(title=_("Overview"))
        self.banner = Adw.Banner(title=_("Part of Winky isn’t running. Reinstall Winky in the "
                                         "Software app."))
        inhalt_ansicht = Adw.ToolbarView(content=self.abschnitte)
        inhalt_ansicht.add_top_bar(Adw.HeaderBar(title_widget=self.inhalt_titel))
        inhalt_ansicht.add_top_bar(self.banner)
        self.inhalt_seite = Adw.NavigationPage(title=_("Overview"), child=inhalt_ansicht)

        self.split = Adw.NavigationSplitView(
            sidebar=Adw.NavigationPage(title="Winky", child=leiste_ansicht),
            content=self.inhalt_seite, min_sidebar_width=200, max_sidebar_width=240)
        self.leiste.select_row(self.leiste.get_row_at_index(0))
        self.split.set_show_content(True)   # schmales Fenster: mit der Übersicht beginnen
        return Adw.NavigationPage(title="Winky", tag="start", child=self.split)

    def abschnitt_zeigen(self, sid):
        self.abschnitte.set_visible_child_name(sid)
        titel = self.abschnitte.get_page(self.abschnitte.get_child_by_name(sid)).get_title()
        self.inhalt_titel.set_title(titel)
        self.inhalt_seite.set_title(titel)
        for i, (eintrag, _t, _s) in enumerate(self.ABSCHNITTE):
            if eintrag == sid:
                self.leiste.select_row(self.leiste.get_row_at_index(i))
        if self.nav.get_visible_page().get_tag() != "start":
            self.nav.pop_to_tag("start")
        self.split.set_show_content(True)

    def _platzhalter(self, titel, inhalt):
        """Abschnitt, solange die Einrichtung fehlt."""
        seite_ = Adw.StatusPage(icon_name=APP_ID, title=titel, description=inhalt, vexpand=True)
        k = knopf(_("Start setup"), self.einrichtung_oeffnen, "pill", "suggested-action")
        k.set_halign(Gtk.Align.CENTER)
        seite_.set_child(k)
        return seite_

    def _baue_uebersicht(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, valign=Gtk.Align.CENTER,
                      vexpand=True, margin_top=24, margin_bottom=24, margin_start=18,
                      margin_end=18)
        # Das Winky-Symbol groß, der Zustand als kleines Zeichen daran
        logo = Gtk.Overlay(halign=Gtk.Align.CENTER, margin_bottom=8)
        logo.set_child(Gtk.Image(icon_name=APP_ID, pixel_size=128))
        self.s_kreis = Gtk.Box(halign=Gtk.Align.END, valign=Gtk.Align.END)
        self.s_kreis.add_css_class("statuszeichen")
        self.s_symbol = Gtk.Image(pixel_size=18, hexpand=True, halign=Gtk.Align.CENTER,
                                  valign=Gtk.Align.CENTER)
        self.s_kreis.append(self.s_symbol)
        logo.add_overlay(self.s_kreis)
        box.append(logo)
        self.s_titel = text("", "title-1", mitte=True)
        box.append(self.s_titel)
        self.s_text = text("", mitte=True, breite=46)
        box.append(self.s_text)
        self.s_zuletzt = text("", "dim-label", mitte=True)
        box.append(self.s_zuletzt)
        knoepfe = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER, margin_top=14)
        self.s_einrichten = knopf(_("Start setup"), self.einrichtung_oeffnen, "pill",
                                  "suggested-action")
        knoepfe.append(self.s_einrichten)
        self.r_probe = Gtk.Button(child=Adw.ButtonContent(icon_name="camera-web-symbolic",
                                                          label=_("Try it out")))
        self.r_probe.add_css_class("pill")
        self.r_probe.connect("clicked", lambda *_: self.kamera_oeffnen("testen"))
        knoepfe.append(self.r_probe)
        self.s_pause_inhalt = Adw.ButtonContent(icon_name="media-playback-pause-symbolic",
                                                label=_("Pause"))
        self.r_pause = Gtk.ToggleButton(child=self.s_pause_inhalt)
        self.r_pause.add_css_class("pill")
        self.r_pause.set_tooltip_text(_("Winky is resting, only your password works "
                                        "everywhere"))
        self.r_pause.connect("notify::active", self._pause_umgeschaltet)
        knoepfe.append(self.r_pause)
        box.append(knoepfe)
        return rollbar(box)

    def _baue_freigaben(self):
        s = Adw.PreferencesPage()
        self.g_schalter = Adw.PreferencesGroup(
            title=_("What Winky unlocks for you"),
            description=_("To change these, your computer asks for the administrator password."))
        self.r_aktiv = SchalterZeile(
            _("Lock screen"), symbol="system-lock-screen-symbolic",
            info=_("A photo on a screen or phone doesn’t fool Winky, screens look black in the "
                   "infrared image. An elaborately made printout or a mask could, just like "
                   "with Windows Hello without extra protection."))
        self.r_aktiv.connect("notify::active", self._aktiv_umgeschaltet)
        self.g_schalter.add(self.r_aktiv)
        self.r_entsperren_geste = SchalterZeile(
            _("Unlock only with ✌"), symbol="security-high-symbolic",
            info=_("Your face alone is then not enough: the lock screen and the login after "
                   "startup also need your ✌. This protects you if someone holds the computer up "
                   "to your face, for example while you’re asleep or under pressure. Without a ✌, "
                   "the password field appears after 8 seconds at most."))
        self.r_entsperren_geste.connect("notify::active", self._entsperren_geste_umgeschaltet)
        self.g_schalter.add(self.r_entsperren_geste)
        self.r_anmeldung = SchalterZeile(
            _("Login after startup"), _("Caution: the login keyring then stays locked"),
            "dialog-warning-symbolic", warnung=True,
            info=_("Your face also logs you in after a restart. The login keyring then stays "
                   "locked and asks for the password when a program needs it. Someone who looks "
                   "very much like you, or holds the computer up to your face, gets in without "
                   "the password from a switched-off computer too."))
        self.r_anmeldung.connect("notify::active", self._anmeldung_umgeschaltet)
        self.g_schalter.add(self.r_anmeldung)
        self.r_schluesselbund = SchalterZeile(
            _("Also unlock the keyring (experimental)"), symbol="dialog-warning-symbolic",
            warnung=True,
            info=_("Your login password is stored sealed in this computer’s TPM chip and handed "
                   "to the keyring only right after your face was recognized at the login "
                   "screen. Someone who has this computer may still be able to read it, for "
                   "example by starting it from a USB stick with Ubuntu or a related Linux; "
                   "without Secure Boot it’s even easier. Don’t use this password anywhere "
                   "else."))
        self.r_schluesselbund.connect("notify::active", self._schluesselbund_umgeschaltet)
        self.g_schalter.add(self.r_schluesselbund)
        self.r_sudo = SchalterZeile(
            _("sudo in the terminal"), symbol="utilities-terminal-symbolic",
            info=_("A harmful program running as you can trigger a sudo request. But nothing "
                   "happens without your ✌, and every request shows up with the command. After "
                   "three unconfirmed requests, only the password works for 10 minutes."))
        self.s_sudo = self.r_sudo
        self.k_sudo_einrichten = knopf(_("Set up"), lambda: self.kamera_oeffnen("geste-testen"))
        self.r_sudo.vor_schalter(self.k_sudo_einrichten)
        self.r_sudo.connect("notify::active", self._sudo_umgeschaltet)
        self.g_schalter.add(self.r_sudo)
        self.r_dialoge = SchalterZeile(
            _("Administrator dialogs"), symbol="dialog-password-symbolic",
            info=_("Password dialogs such as updates or installing software. The ✌ window "
                   "shows what you are approving. If one appears that you didn’t expect, don’t "
                   "show the ✌."))
        self.r_dialoge.connect("notify::active", self._dialoge_umgeschaltet)
        self.g_schalter.add(self.r_dialoge)
        self.r_keepassxc = SchalterZeile(
            "KeePassXC", symbol="dialog-password-symbolic",
            info=_("Only KeePassXC 2.8 or later, installed as a normal package. Older versions "
                   "don’t have quick unlock on Linux, and the Flatpak version can’t register "
                   "it with the system."))
        self.r_keepassxc.connect("notify::active", self._keepassxc_umgeschaltet)
        self.g_schalter.add(self.r_keepassxc)
        self.r_keepassxc_geste = SchalterZeile(
            _("KeePassXC only with ✌"),
            _("Recommended: without your ✌ sign, nobody can open the database, not even while "
              "you’re sitting at the computer"), "security-high-symbolic")
        self.r_keepassxc_geste.connect("notify::active", self._keepassxc_geste_umgeschaltet)
        self.g_schalter.add(self.r_keepassxc_geste)
        # Deutlich sichtbar, solange kein passendes KeePassXC da ist
        self.r_keepassxc_version = Adw.ActionRow(
            title=_("<b>Only works with KeePassXC 2.8 or later</b>"))
        self.r_keepassxc_version.set_subtitle_selectable(True)
        warnung = Gtk.Image(icon_name="dialog-warning-symbolic")
        warnung.add_css_class("warning")
        self.r_keepassxc_version.add_prefix(warnung)
        self.g_schalter.add(self.r_keepassxc_version)
        s.add(self.g_schalter)

        # Automatisch sperren wie in den GNOME-Einstellungen: Schalter = lock-enabled, Minuten =
        # idle-delay (Bildschirm aus), gesperrt wird dann sofort (lock-delay 0)
        g_sperre = Adw.PreferencesGroup(
            title=_("Screen lock"),
            description=_("With face unlock, a short time hardly bothers you: you’re back in "
                          "with a glance."))
        self.r_sperre_an = Adw.SwitchRow(title=_("Lock automatically"))
        self.r_sperre_an.add_prefix(Gtk.Image(icon_name="system-lock-screen-symbolic"))
        self.r_sperre_an.connect("notify::active", self._sperre_umgeschaltet)
        g_sperre.add(self.r_sperre_an)
        self.r_sperrzeit = Adw.SpinRow.new_with_range(1, 60, 1)
        self.r_sperrzeit.set_title(_("After minutes without input"))
        self.r_sperrzeit.add_prefix(Gtk.Image(icon_name="preferences-system-time-symbolic"))
        self.r_sperrzeit.connect("notify::value", self._sperrzeit_gewaehlt)
        g_sperre.add(self.r_sperrzeit)
        s.add(g_sperre)
        box = Gtk.Stack()
        box.add_named(s, "inhalt")
        box.add_named(self._platzhalter(_("Not set up yet"),
                                        _("Record your face and try it out once, then you can "
                                          "choose here what Winky unlocks.")), "leer")
        self.freigaben_stapel = box
        return box

    def _baue_gesicht(self):
        s = Adw.PreferencesPage()
        self.g_pflege = Adw.PreferencesGroup(title=_("Try out and maintain"))
        self.r_testen = weiterzeile(_("Try out recognition"),
                                    _("Look at the camera and see whether Winky recognizes you"),
                                    lambda: self.kamera_oeffnen("testen"), "camera-web-symbolic")
        self.r_ergaenzen = weiterzeile(_("Add to your face"),
                                       _("Winky sometimes doesn’t recognize you, for example with "
                                         "glasses or in different light? Add these looks."),
                                       lambda: self.kamera_oeffnen("ergaenzen"),
                                       "list-add-symbolic")
        self.r_neu = weiterzeile(_("Record your face again"),
                                 _("Starts over and replaces everything recorded so far"),
                                 lambda: self.kamera_oeffnen("einlernen"), "view-refresh-symbolic")
        self.r_zweite = weiterzeile(_("Check with a second person"), "",
                                    lambda: self.kamera_oeffnen("gegenprobe"),
                                    "system-users-symbolic")
        self.r_geste = weiterzeile(_("Test face and ✌"), "",
                                   lambda: self.kamera_oeffnen("geste-testen"),
                                   "utilities-terminal-symbolic")
        for r in (self.r_testen, self.r_ergaenzen, self.r_neu, self.r_zweite, self.r_geste):
            self.g_pflege.add(r)
        s.add(self.g_pflege)
        self.g_ergaenzungen = ErgaenzungsListe(self)
        s.add(self.g_ergaenzungen)
        box = Gtk.Stack()
        box.add_named(s, "inhalt")
        box.add_named(self._platzhalter(_("No face recorded yet"),
                                        _("The setup records your face in about two minutes.")),
                      "leer")
        self.gesicht_stapel = box
        return box

    @property
    def _ergaenzung_zeilen(self):
        return self.g_ergaenzungen.zeilen

    def _ergaenzungen_zeigen(self):
        liste = self.zustand.ergaenzungen or []
        self.g_ergaenzungen.zeigen(liste, self.beschaeftigt())
        self.r_ergaenzen.set_subtitle(
            _("Up to three additions. Delete one first, or reuse a name to replace it.")
            if len(liste) >= 3 else
            _("Winky sometimes doesn’t recognize you, for example with glasses or in different "
              "light? Add these looks."))

    def ergaenzung_loeschen_fragen(self, eintrag, name):
        dialog = Adw.AlertDialog.new(
            _("Delete “{name}”?").format(name=name),
            _("Winky forgets these extra images. Your face and the other additions stay."))
        dialog.add_response("abbrechen", _("Cancel"))
        dialog.add_response("weg", _("Delete"))
        dialog.set_response_appearance("weg", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("abbrechen")
        dialog.connect("response", lambda _d, r: r == "weg" and self._verwalten(
            ["ergaenzung-entfernen", str(eintrag.get("id"))],
            _("“{name}” deleted").format(name=name)))
        dialog.present(self)

    def _baue_verlauf(self):
        s = Adw.PreferencesPage()
        self.g_verlauf = Adw.PreferencesGroup(
            description=_("What Winky checked recently, newest first"))
        self._verlauf_zeilen = []
        s.add(self.g_verlauf)
        return s

    # Assistent

    def _baue_einrichtung(self):
        self.w_stapel = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
                                  vexpand=True)
        self.w_ablauf = {}

        def schritt(sid, titel, beschreibung, *inhalt, symbol=None):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=24,
                          margin_bottom=24, margin_start=18, margin_end=18)
            if symbol:
                bild = Gtk.Image(icon_name=symbol, pixel_size=96)
                if symbol == "emblem-ok-symbolic":
                    bild.add_css_class("success")
                box.append(bild)
            box.append(text(titel, "title-1", mitte=symbol is not None))
            if beschreibung:
                box.append(text(beschreibung, mitte=symbol is not None))
            for w in inhalt:
                box.append(w)
            self.w_stapel.add_named(rollbar(box), sid)
            return box

        liste = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        liste.add_css_class("boxed-list")
        for symbol, zeile in (
                ("dialog-password-symbolic", _("Your password keeps working, always.")),
                ("camera-photo-symbolic", _("Winky doesn’t save any photos of you.")),
                ("preferences-system-time-symbolic", _("Setup takes about two minutes.")),
                ("system-shutdown-symbolic", _("After you turn on your computer, you still need "
                                               "your password (you can change this later)."))):
            liste.append(textzeile(zeile, symbol=symbol))
        schritt("willkommen", _("Welcome to Winky"),
                _("With Winky, you unlock the lock screen with a glance at the camera, similar "
                  "to Windows Hello."), liste, symbol=APP_ID)

        self.w_kamera_knopf = knopf(_("Search for camera"), self._kamera_suchen, "pill",
                                    "suggested-action")
        self.w_kamera_knopf.set_halign(Gtk.Align.CENTER)
        self.w_kamera_status = text("", "title-4", mitte=True)
        schritt("kamera", _("Find the camera"),
                _("Winky needs your computer’s infrared camera. That’s the camera Windows uses "
                  "to unlock with your face (Windows Hello). When searching, your computer asks "
                  "for the administrator password."),
                self.w_kamera_knopf, self.w_kamera_status,
                text(_("None found? Not every computer has an infrared camera. A normal webcam "
                       "isn’t enough, because even a photo could fool it."),
                     "dim-label"))

        for sid, art in (("einlernen", "einlernen"), ("testen", "testen"),
                         ("gegenprobe", "gegenprobe")):
            a = KameraAblauf(self, art, mit_titel=False)
            self.w_ablauf[sid] = a
            self.ablaeufe.append(a)
            titel = (_("Check with a second person (optional)") if sid == "gegenprobe"
                     else ABLAEUFE[art]["titel"])
            schritt(sid, titel, "", a)

        self.w_einschalten = knopf(_("Turn on face unlock"),
                                   lambda: self._aktiv_setzen(True), "pill", "suggested-action")
        self.w_einschalten.set_halign(Gtk.Align.CENTER)
        self.w_einschalten_status = text("", "title-4", mitte=True)
        so = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        so.add_css_class("boxed-list")
        for nr, zeile in (("1", _("Lock the screen: Super+L (Windows key and L)")),
                          ("2", _("To unlock, press a key or move the mouse")),
                          ("3", _("Look at the camera, done")),
                          ("", _("If it doesn’t work, the password field appears as usual."))):
            r = textzeile(zeile)
            if nr:
                r.add_prefix(text(nr, "title-4"))
            so.append(r)
        schritt("einschalten", _("Turn on"),
                _("Everything is ready. Turn on face unlock for the lock screen. Your computer "
                  "will ask for the administrator password to do this."),
                self.w_einschalten, self.w_einschalten_status,
                text(_("How it works from now on"), "heading"), so)

        a = KameraAblauf(self, "geste-testen", mit_titel=False)
        self.w_ablauf["sudo"] = a
        self.ablaeufe.append(a)
        sudo_liste = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        sudo_liste.add_css_class("boxed-list")
        self.w_sudo = Adw.SwitchRow(title=_("Confirm sudo with face and ✌"),
                                    subtitle=_("Changing this needs the administrator password"))
        self.w_sudo.connect("notify::active", self._sudo_umgeschaltet)
        sudo_liste.append(self.w_sudo)
        a.zusatz.append(sudo_liste)
        schritt("sudo", _("For the terminal (optional)"),
                _("Do you use sudo in the terminal? Then you can confirm commands with your face "
                  "and the ✌ sign instead of typing your password. If you don’t use the "
                  "terminal, just skip this step."), a)

        schritt("fertig", _("Done!"),
                _("Winky is set up. Try it right away: press Super+L, then any key, and look at "
                  "the camera. “Security and help” in the sidebar explains what to watch out "
                  "for."), symbol="emblem-ok-symbolic")

        unten = Gtk.Box(spacing=12, margin_top=10, margin_bottom=10, margin_start=18,
                        margin_end=18)
        self.w_zurueck = knopf(_("Back"), lambda: self._schritt_wechseln(-1), "pill")
        self.w_zaehler = text("", "dim-label", mitte=True)
        self.w_zaehler.set_hexpand(True)
        self.w_weiter = knopf(_("Next"), lambda: self._schritt_wechseln(1), "pill",
                              "suggested-action")
        unten.append(self.w_zurueck)
        unten.append(self.w_zaehler)
        unten.append(self.w_weiter)
        self.w_stapel.connect("notify::visible-child-name", lambda *_: self._assistent_anzeigen())
        return seite(_("Setup"), "einrichtung", self.w_stapel, unten)

    def einrichtung_oeffnen(self):
        """Öffnet den Assistenten beim ersten offenen Schritt."""
        s = stand(self.zustand)
        offen = [sid for sid in ("kamera", "einlernen", "testen") if not s[sid]]
        if not s["kamera"] and not s["einlernen"]:
            ziel = "willkommen"
        elif offen:
            ziel = offen[0]
        elif not self.zustand.aktiv:
            ziel = "gegenprobe" if s["gegenprobe"] is None else "einschalten"
        else:
            ziel = "sudo"
        self.w_stapel.set_visible_child_name(ziel)
        if self.nav.get_visible_page().get_tag() != "einrichtung":
            self.nav.push_by_tag("einrichtung")
        self._assistent_anzeigen()

    def _schritt_wechseln(self, richtung):
        i = SCHRITTE.index(self.w_stapel.get_visible_child_name()) + richtung
        if i >= len(SCHRITTE):
            self.nav.pop_to_tag("start")
            return
        self.w_stapel.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT if richtung > 0
                                          else Gtk.StackTransitionType.SLIDE_RIGHT)
        self.w_stapel.set_visible_child_name(SCHRITTE[max(0, i)])

    def _assistent_anzeigen(self):
        sid = self.w_stapel.get_visible_child_name()
        if sid is None:
            return
        z, s, laeuft = self.zustand, stand(self.zustand), self.beschaeftigt()
        self.w_zaehler.set_label(
            _("Step {number} of {total}").format(number=GEZAEHLT.index(sid) + 1,
                                                 total=len(GEZAEHLT))
            if sid in GEZAEHLT else "")
        self.w_zurueck.set_visible(sid != "willkommen")
        weiter, darf = _("Next"), True
        if sid == "willkommen":
            weiter = _("Let’s go")
        elif sid in ("kamera", "einlernen", "testen"):
            darf = s[sid]
        elif sid == "gegenprobe":
            weiter = _("Next") if s["gegenprobe"] is not None else _("Skip")
        elif sid == "einschalten":
            darf = z.aktiv
        elif sid == "sudo":
            weiter = _("Next") if z.sudo else _("Skip")
        elif sid == "fertig":
            weiter = _("Go to overview")
        self.w_weiter.set_label(weiter)
        self.w_weiter.set_sensitive(darf and not laeuft)
        self.w_zurueck.set_sensitive(not laeuft)

    # Kamera, Sicherheit, Erweitert

    def _baue_kamera(self):
        self.k_ansicht = KameraAblauf(self, "testen")
        self.ablaeufe.append(self.k_ansicht)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=24, margin_bottom=24,
                      margin_start=18, margin_end=18)
        box.append(self.k_ansicht)
        self.k_seite = seite(_("Camera"), "kamera", rollbar(box))
        return self.k_seite

    def kamera_oeffnen(self, art):
        if self.beschaeftigt():
            self.melde(_("Please wait, something else is still running"))
            return
        self.k_ansicht.setze_art(art)
        self.k_seite.set_title(ABLAEUFE[art]["titel"])
        self.nav.push_by_tag("kamera")
        self.aktualisieren()

    def _baue_sicherheit(self):
        s = Adw.PreferencesPage()
        for titel, beschreibung, symbol, zeilen in SICHERHEIT:
            g = Adw.PreferencesGroup(title=titel, description=beschreibung)
            for t, u in zeilen:
                g.add(textzeile(t, u, symbol))
            s.add(g)
        return s

    def _baue_erweitert(self):
        s = Adw.PreferencesPage()
        kamera = Adw.PreferencesGroup(title=_("Camera"))
        self.r_kamera = Adw.ActionRow(title=_("Infrared camera"))
        self.r_kamera.set_subtitle_selectable(True)
        self.k_kamera_suchen = knopf(_("Search again"), self._kamera_suchen)
        self.r_kamera.add_suffix(self.k_kamera_suchen)
        kamera.add(self.r_kamera)
        self.r_kamera_wahl = Adw.ActionRow(title=_("Choose a different camera"),
                                           subtitle=_("If there’s more than one infrared camera"))
        self.k_kamera_wahl = knopf(_("Choose …"), self._kamera_auswahl)
        self.r_kamera_wahl.add_suffix(self.k_kamera_wahl)
        kamera.add(self.r_kamera_wahl)
        self.r_ir_schutz = SchalterZeile(
            _("Infrared camera only for Winky"), symbol="camera-web-symbolic",
            info=_("Normally every program in your account can switch on the cameras, including "
                   "harmful ones, and on many laptops the infrared camera can’t be covered. With "
                   "this switch, only Winky may use the infrared camera; other cameras stay as "
                   "they are. If another program needs the infrared camera (for example another "
                   "face unlock tool), turn this off. If the infrared camera shares its connection "
                   "with the normal camera, Winky leaves both as they are."))
        self.r_ir_schutz.connect("notify::active", self._ir_schutz_umgeschaltet)
        kamera.add(self.r_ir_schutz)
        s.add(kamera)

        strenge = Adw.PreferencesGroup(
            title=_("Strictness"),
            description=_("How similar a face must be to yours (threshold). Higher is safer, but "
                          "Winky might recognize you less often. Default 0.65; your own face is "
                          "usually well above that. The check with a second person shows "
                          "whether other faces stay far enough below. Try it out once after "
                          "every change."))
        self.r_spin = Adw.SpinRow.new_with_range(0.50, SCHWELLE_MAX, 0.01)
        self.r_spin.set_title(_("Threshold"))
        self.r_spin.set_digits(2)
        strenge.add(self.r_spin)
        self.r_speichern = Adw.ActionRow(title=_("Apply the chosen value"))
        self.k_speichern = knopf(_("Save"), lambda: self._verwalten(
            ["schwelle", f"{self.r_spin.get_value():.2f}"], _("Strictness saved"), admin=True))
        self.r_speichern.add_suffix(self.k_speichern)
        strenge.add(self.r_speichern)
        self.r_messwerte = textzeile(_("Your measurements"))
        strenge.add(self.r_messwerte)
        s.add(strenge)

        zeit = Adw.PreferencesGroup(
            title=_("Time for the ✌"),
            description=_("How long Winky waits for your ✌. More time lets you read calmly what "
                          "you are approving. For sudo up to 30 seconds; KeePassXC and "
                          "administrator dialogs end after 9 seconds at most, a limit set by "
                          "the system."))
        self.r_geste_zeit = Adw.SpinRow.new_with_range(5, 30, 1)
        self.r_geste_zeit.set_title(_("Seconds"))
        zeit.add(self.r_geste_zeit)
        self.r_geste_zeit_speichern = Adw.ActionRow(title=_("Apply the chosen value"))
        self.k_geste_zeit = knopf(_("Save"), lambda: self._verwalten(
            ["geste-zeit", str(int(self.r_geste_zeit.get_value()))], _("Time for the ✌ saved"),
            admin=True))
        self.r_geste_zeit_speichern.add_suffix(self.k_geste_zeit)
        zeit.add(self.r_geste_zeit_speichern)
        s.add(zeit)

        kp = Adw.PreferencesGroup(
            title="KeePassXC",
            description=_("Only KeePassXC 2.8 or later, installed as a normal package. Older "
                          "versions don’t have quick unlock on Linux, and the Flatpak version "
                          "can’t register it with the system. There, KeePassXC keeps asking for "
                          "the master password."))
        self.r_keepassxc_info = Adw.ActionRow(title=_("KeePassXC on this computer"))
        self.r_keepassxc_info.set_subtitle_selectable(True)
        self.r_keepassxc_symbol = Gtk.Image()
        self.r_keepassxc_info.add_prefix(self.r_keepassxc_symbol)
        kp.add(self.r_keepassxc_info)
        s.add(kp)

        daten = Adw.PreferencesGroup(title=_("Your data"))
        self.r_vorlagen = Adw.ActionRow(title=_("Your face data"))
        self.k_daten_weg = knopf(_("Delete …"), self._vorlagen_loeschen_fragen)
        self.r_vorlagen.add_suffix(self.k_daten_weg)
        daten.add(self.r_vorlagen)
        self.r_vorlagen_tpm = SchalterZeile(
            _("Seal face data in the TPM chip"), symbol="channel-secure-symbolic",
            info=_("Your face data is then stored on the disk only encrypted; the key stays in "
                   "this computer’s TPM chip. This helps if someone reads your disk in another "
                   "computer or from Windows on the same computer (dual boot). It doesn’t help "
                   "against a USB stick with Ubuntu or a related Linux started on this computer; "
                   "a BIOS password that blocks starting from USB helps against that. After a "
                   "BIOS update or a change to Secure Boot, you may have to record your face "
                   "again. Applies to all users of this computer."))
        self.r_vorlagen_tpm.connect("notify::active", self._vorlagen_tpm_umgeschaltet)
        daten.add(self.r_vorlagen_tpm)
        s.add(daten)

        info = Adw.PreferencesGroup(title=_("About Winky"))
        self.r_version = textzeile(_("Version"))
        self.r_dienst = textzeile(_("Verification service"))
        info.add(self.r_version)
        info.add(self.r_dienst)
        info.add(textzeile(_("License"),
                           _("MIT. Models: YuNet (MIT), SFace and MediaPipe (Apache-2.0)")))
        s.add(info)

        rueckbau = Adw.PreferencesGroup(title=_("Remove"))
        r = textzeile(_("Uninstall"), _("In the Software app under “Installed”. After that, only "
                                        "the password works everywhere again, and the face data "
                                        "of all users is deleted."), "user-trash-symbolic")
        self.k_store = None
        if Gio.AppInfo.get_default_for_uri_scheme("appstream"):
            self.k_store = knopf(_("Open"), self._store_oeffnen)
            r.add_suffix(self.k_store)
        rueckbau.add(r)
        rueckbau.add(textzeile(_("Without the Software app"),
                               _("In the terminal:\nsudo apt purge winky")))
        s.add(rueckbau)
        return s

    # Kameraabläufe

    def lauf_starten(self, ansicht):
        if self.beschaeftigt():
            self.melde(_("Please wait, something else is still running"))
            return
        ansicht.zuruecksetzen()
        ansicht.live.set_label(_("Asking for your password and starting the camera …"))
        ansicht.vorschau.hinweis(_("Camera is starting …"), bis_bild=True)
        try:
            args = [ansicht.art]
            if ansicht.art == "ergaenzen":
                args.append(ansicht.e_name.get_text().strip() or _("Addition {number}").format(
                    number=len(self.zustand.ergaenzungen) + 1))
            self.gesicht_lauf = Prozess(umgebung.verwalten_befehl(args), self._g_bild,
                                        self._g_status, self._g_ende, abbruch_ueber_eingabe=True)
        except OSError as e:
            self.melde(_("Could not start: {error}").format(error=e))
            return
        self.gesicht_lauf.art = ansicht.art
        self.lauf_ansicht = ansicht
        self.aktualisieren()

    def _g_bild(self, w, h, daten):
        if self.gesicht_lauf and self.lauf_ansicht:
            self.lauf_ansicht.vorschau.zeige(w, h, daten)

    def _g_status(self, st):
        a = self.lauf_ansicht
        if a is None:
            return
        if st.get("modus") == "countdown":
            a.vorschau.hinweis(_("Please step out of the picture … {seconds}").format(
                seconds=st.get("rest")), bis_bild=True)
            a.live.set_label(_("Now the other person sits down in front of the camera."))
            return
        inhalt, gut = self._tipp(st, a.art)
        a.live.set_label(inhalt)
        a.live.remove_css_class("gut")
        a.live.remove_css_class("warnung")
        a.live.add_css_class("gut" if gut else "warnung")
        if st.get("dauer"):
            a.vorschau.fortschritt(float(st.get("t", 0)) / float(st["dauer"]),
                                   "gut" if gut else "warnung")

    def _tipp(self, st, art):
        """Kurzer Hinweis unter dem Bild, ohne Messzahlen."""
        if st.get("fehler"):
            return st["fehler"], False
        if art == "geste-testen":
            gesicht = (_("Face recognized ✓") if st.get("gesicht_erkannt")
                       else _("Checking face …"))
            if not st.get("hand"):
                hand = _("show ✌ now")
            elif st.get("zeichen"):
                hand = _("✌ recognized, hold it briefly")
            else:
                hand = _("Hand seen, but no ✌ yet")
            return f"{gesicht} · {hand}", bool(st.get("gesicht_erkannt") and st.get("zeichen"))
        grund = st.get("grund")
        if art == "gegenprobe" and grund == "ok" and st.get("wert") is not None:
            if st["wert"] >= self.zustand.schwelle - GEGENPROBE_ABSTAND:
                return _("Caution: to Winky, this person looks a lot like you"), False
            return _("Good: Winky doesn’t recognize this person"), True
        tipp = TIPPS.get(grund, grund or "")
        if art == "ergaenzen" and grund in ("ok", "kein_gesicht", "zu_klein", "gedreht",
                                            "geneigt", "unsicher"):
            # Erst wie immer (daran erkennt Winky dich), dann das ändern, womit es Mühe hat
            if float(st.get("t", 0)) < 7:
                return _("First as usual: look at the camera"), grund == "ok"
            return _("Now change it: glasses on, different light … slowly move your head"), True
        if art == "einlernen" and grund == "ok":
            tipp = _("Good, keep slowly moving your head")
        return tipp, grund == "ok"

    def passwortdialog_hilfe(self, lauf, rc):
        """Erschien gar kein Passwortdialog, deutlich erklären und Abmelden anbieten."""
        if not lauf.passwortdialog_fehlt(rc) or getattr(self, "_hilfe_offen", False):
            return
        self._hilfe_offen = True
        dialog = Adw.AlertDialog.new(
            _("The password dialog isn’t available"),
            _("Winky asks for your password through the desktop’s password dialog, but it didn’t "
              "appear. This can happen when the desktop didn’t start completely, for example "
              "after a login that hung. Log out and back in once (or restart), then it works "
              "again."))
        dialog.add_response("spaeter", _("Later"))
        dialog.add_response("abmelden", _("Log out now"))
        dialog.set_response_appearance("abmelden", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_close_response("spaeter")

        def antwort(_d, r):
            self._hilfe_offen = False
            if r == "abmelden" and not umgebung.ATTRAPPE:
                subprocess.Popen(["gnome-session-quit", "--logout"], start_new_session=True)

        dialog.connect("response", antwort)
        dialog.present(self)
        self.hilfe_dialog = dialog

    def _g_ende(self, lauf, rc):
        self.passwortdialog_hilfe(lauf, rc)
        a = self.lauf_ansicht
        self.gesicht_lauf = None
        self.lauf_ansicht = None
        erg = lauf.ergebnis or {}
        abgebrochen = lauf.abgebrochen or erg.get("abgebrochen")
        a.vorschau.leeren()
        a.live.set_label("")
        a.live.remove_css_class("gut")
        a.live.remove_css_class("warnung")
        if abgebrochen:
            a.vorschau.hinweis(_("Canceled"))
            a.ergebnis.set_label("")
        elif lauf.art == "einlernen":
            if erg.get("ok"):
                a.vorschau.hinweis(_("✓ Recorded"))
                a.vorschau.fortschritt(1, "gut")
                a.ergebnis.set_label(_("✓ Your face is recorded. Now try out whether Winky "
                                       "recognizes you."))
                self.melde(_("Face recorded"))
            else:
                a.vorschau.hinweis(_("Not saved"))
                a.vorschau.fortschritt(1, "warnung")
                a.ergebnis.set_label(lauf.fehlermeldung(rc))
        elif lauf.art == "ergaenzen":
            if erg.get("ok"):
                a.vorschau.hinweis(_("✓ Added"))
                a.vorschau.fortschritt(1, "gut")
                a.ergebnis.set_label((_("✓ Replaced the addition with the same name.") + " "
                                      if erg.get("ersetzt") else "") +
                                     _("✓ Added {count} images. Try it out the way Winky had "
                                       "trouble before.").format(count=erg.get("uebernommen", 0)))
                self.melde(_("Face added"))
            else:
                a.vorschau.hinweis(_("Nothing added"))
                a.vorschau.fortschritt(1, "warnung")
                a.ergebnis.set_label(lauf.fehlermeldung(rc))
        elif lauf.art == "testen":
            if erg.get("status") == "treffer":
                a.vorschau.hinweis(_("✓ Recognized"))
                a.vorschau.fortschritt(1, "gut")
                a.ergebnis.set_label(_("✓ Recognized after {seconds} seconds.").format(
                    seconds=komma(erg.get("dauer_ms", 0) / 1000, 1)))
            else:
                a.vorschau.hinweis(_("Not recognized"))
                a.vorschau.fortschritt(1, "warnung")
                a.ergebnis.set_label(
                    _("Winky didn’t recognize you this time. Look straight at the camera and "
                      "try again. If it often doesn’t work, record your face again.")
                    if erg.get("status") in ("kein_treffer", "kein_gesicht")
                    else lauf.fehlermeldung(rc))
        elif lauf.art == "geste-testen":
            if erg.get("ok"):
                a.vorschau.hinweis(_("✓ Recognized"))
                a.vorschau.fortschritt(1, "gut")
                a.ergebnis.set_label(_("✓ Face and ✌ recognized. You can now use them to "
                                       "confirm sudo."))
                self.melde(_("Face and ✌ recognized"))
            else:
                a.vorschau.hinweis(_("Not recognized"))
                a.vorschau.fortschritt(1, "warnung")
                a.ergebnis.set_label(lauf.fehlermeldung(rc))
        else:  # gegenprobe
            wert = erg.get("wert")
            if erg.get("ok"):
                a.vorschau.hinweis(_("✓ Passed"))
                a.vorschau.fortschritt(1, "gut")
                a.ergebnis.set_label(_("✓ Passed: Winky didn’t recognize the other person."))
            elif erg.get("wie_eigen"):
                a.vorschau.hinweis(_("Was that you?"))
                a.vorschau.fortschritt(1, "warnung")
                a.ergebnis.set_label(lauf.fehlermeldung(rc))
            elif wert is not None and wert >= 0 and erg.get("status") != "kein_gesicht":
                a.vorschau.hinweis(_("Too similar"))
                a.vorschau.fortschritt(1, "warnung")
                a.ergebnis.set_label(
                    _("To Winky, this person looks too much like you. Make Winky stricter so "
                      "that only you can unlock the screen.") if strenger_moeglich(system.lese_zustand())
                    else _("To Winky, this person looks too much like you, and stricter settings "
                           "would lock you out as well. Better use only your password."))
            else:
                a.vorschau.hinweis(_("Not checked"))
                a.vorschau.fortschritt(1, "warnung")
                a.ergebnis.set_label(lauf.fehlermeldung(rc))
        self.aktualisieren()

    def strenger_einstellen(self):
        z = self.zustand
        if z.gegenprobe_wert is None:
            return
        neu = strengere_schwelle(z.gegenprobe_wert)
        if not strenger_moeglich(z):
            self.melde(_("This person looks too much like you. Winky can’t reliably tell you "
                         "apart, so it’s better to use only your password."))
            return
        self._verwalten(["schwelle", f"{neu:.2f}"],
                        _("Winky is now stricter ({value}). Try it out to see whether it still "
                          "recognizes you.").format(value=komma(neu, 2)), admin=True)

    def _seite_weg(self, _nav, page):
        """Wer eine Seite mit laufender Kamera verlässt, bricht den Ablauf ab."""
        if self.gesicht_lauf and page.get_tag() in ("einrichtung", "kamera"):
            self.gesicht_lauf.abbrechen()

    # Verwaltung

    def _store_oeffnen(self):
        try:
            Gio.AppInfo.launch_default_for_uri(f"appstream://{APP_ID}", None)
        except GLib.Error:
            self.melde(_("Couldn’t open the Software app"))

    def _verwalten(self, args, erfolg, admin=False, danach=None, eingabe=None):
        if self.beschaeftigt():
            self.melde(_("Please wait, something else is still running"))
            return

        def ende(lauf, rc):
            self.aktion = None
            erg = lauf.ergebnis or {}
            ok = rc == 0 and bool(erg.get("ok"))
            meldung = (erg.get("hinweis") or erfolg) if ok else lauf.fehlermeldung(rc)
            if not ok:
                self.passwortdialog_hilfe(lauf, rc)
            self.melde(meldung)
            self.aktualisieren()
            if danach:
                danach(ok, erg, meldung)

        try:
            self.aktion = Prozess(umgebung.verwalten_befehl(args, admin=admin), bei_ende=ende,
                                  abbruch_ueber_eingabe=True, eingabe=eingabe)
        except OSError as e:
            self.melde(_("Could not start: {error}").format(error=e))
        self.aktualisieren()

    def _kamera_suchen(self):
        def danach(ok, erg, meldung):
            if ok:
                self.kamera_name = (erg.get("kamera") or {}).get("name")
            self.w_kamera_status.set_label("" if ok else meldung)
            self.aktualisieren()

        if self.beschaeftigt():
            self.melde(_("Please wait, something else is still running"))
            return
        self.w_kamera_status.set_label(_("Searching …"))
        self._verwalten(["kamera", "auto"], _("Camera set up"), admin=True, danach=danach)

    def _kamera_auswahl(self):
        def gefunden(ok, erg, _meldung):
            if not ok:
                return
            liste = [k for k in erg.get("kameras", []) if not k.get("fehler")]
            if not liste:
                self.melde(_("No infrared camera found"))
                return
            dialog = Adw.AlertDialog.new(_("Choose camera"),
                                         _("Cameras found with an infrared image:"))
            auswahl = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
            auswahl.add_css_class("boxed-list")
            for k in liste:
                strahler = (_("Light flashing") if k.get("blinkt") else
                            _("Light on") if k.get("hell", 0) >= 10 else _("Image dark"))
                zeile = Adw.ActionRow(title=k.get("name", "?"),
                                      subtitle=f"{k['pfad']} · {k.get('breite')}×{k.get('hoehe')}"
                                               f" · {strahler}")
                zeile.pfad = k["pfad"]
                zeile.name = k.get("name")
                auswahl.append(zeile)
            auswahl.select_row(auswahl.get_row_at_index(0))
            dialog.set_extra_child(auswahl)
            dialog.add_response("abbrechen", _("Cancel"))
            dialog.add_response("ok", _("Apply"))
            dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_close_response("abbrechen")

            def antwort(_d, r):
                zeile = auswahl.get_selected_row()
                if r == "ok" and zeile is not None:
                    self.kamera_name = zeile.name
                    GLib.idle_add(lambda: self._verwalten(
                        ["kamera", zeile.pfad], _("Camera selected"), admin=True) and False)

            dialog.connect("response", antwort)
            dialog.present(self)

        self._verwalten(["kameras"], _("Camera search finished"), danach=gefunden)

    def _vorlagen_loeschen_fragen(self):
        dialog = Adw.AlertDialog.new(_("Delete your face data?"),
                                     _("After that, your face won’t unlock anything until you "
                                       "record it again. Your password keeps working."))
        dialog.add_response("abbrechen", _("Cancel"))
        dialog.add_response("weg", _("Delete"))
        dialog.set_response_appearance("weg", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("abbrechen")
        dialog.connect("response", lambda _d, r: r == "weg" and self._verwalten(
            ["entfernen"], _("Face data deleted")))
        dialog.present(self)

    def _aktiv_setzen(self, an):
        if an:
            self._verwalten(["aktivieren"], _("Turned on. Try it with Super+L."), admin=True)
        else:
            self._verwalten(["deaktivieren"], _("Turned off, only the password works again"),
                            admin=True)

    def _aktiv_umgeschaltet(self, zeile, _pspec):
        if not self._schalter_sperre and zeile.get_active() != self.zustand.aktiv:
            self._aktiv_setzen(zeile.get_active())

    def _keepassxc_umgeschaltet(self, zeile, _pspec):
        # GTK meldet ein Umschalten manchmal doppelt: nur auf echte Änderungen reagieren
        if self._schalter_sperre or zeile.get_active() == self.zustand.keepassxc:
            return
        if zeile.get_active():
            self._verwalten(["keepassxc", "an"], _("KeePassXC can now be opened with your face"),
                            admin=True)
        else:
            self._verwalten(["keepassxc", "aus"], _("KeePassXC is back to password only"),
                            admin=True)

    def _keepassxc_geste_umgeschaltet(self, zeile, _pspec):
        # GTK meldet ein Umschalten manchmal doppelt: nur auf echte Änderungen reagieren
        if self._schalter_sperre or zeile.get_active() == self.zustand.keepassxc_geste:
            return
        if zeile.get_active():
            self._verwalten(["keepassxc", "geste-an"], _("KeePassXC now requires face and ✌"),
                            admin=True)
        else:
            self._verwalten(["keepassxc", "geste-aus"],
                            _("KeePassXC now opens with your face alone"), admin=True)

    def _sudo_umgeschaltet(self, zeile, _pspec):
        # GTK meldet ein Umschalten manchmal doppelt: nur auf echte Änderungen reagieren
        if self._schalter_sperre or zeile.get_active() == self.zustand.sudo:
            return
        if zeile.get_active():
            self._verwalten(["sudo", "an"], _("sudo can now be confirmed with face and ✌"),
                            admin=True, danach=lambda ok, _e, _m: ok and self._hinweis_starten())
        else:
            self._verwalten(["sudo", "aus"], _("sudo is back to password only"), admin=True)

    def ueber_zeigen(self):
        v = umgebung.version()
        self.ueber = Adw.AboutDialog(
            application_name="Winky", application_icon=APP_ID, developer_name="DieSchatten",
            version=str(v.get("version", "?")), website="https://github.com/DieSchatten/winky",
            issue_url="https://github.com/DieSchatten/winky/issues",
            license_type=Gtk.License.MIT_X11,
            comments=_("Face unlock for GNOME with an infrared camera, like Windows Hello. "
                       "Use at your own risk.") + "\n\n" +
            _("Why “Winky”: The first idea was to confirm with a wink. In tests, winking "
              "turned out to depend too much on the person, while the ✌ (victory) sign was "
              "recognized reliably. The ✌ stayed, the name too."),
            debug_info=f"Winky {v.get('version')} · {v.get('commit')} · {v.get('gebaut')}")
        self.ueber.add_legal_section("YuNet, ONNX Runtime", None, Gtk.License.MIT_X11, None)
        self.ueber.add_legal_section("SFace, MediaPipe", None, Gtk.License.APACHE_2_0, None)
        self.ueber.present(self)

    def _schluesselbund_umgeschaltet(self, zeile, _pspec):
        # GTK meldet ein Umschalten manchmal doppelt: nur auf echte Änderungen reagieren
        if self._schalter_sperre or zeile.get_active() == bool(self.zustand.schluesselbund):
            return
        if not zeile.get_active():
            self._verwalten(["schluesselbund", "aus"],
                            _("The keyring password has been removed from the TPM chip"))
            return
        if getattr(self, "schluessel_dialog", None):   # schon offen: kein zweiter Dialog
            return
        text = _("Winky stores your login password sealed in this computer’s TPM chip and "
                 "hands it to the keyring after you log in with your face. Only on this "
                 "computer, only right after your face was recognized at the login screen.\n\n"
                 "Someone who has this computer may still be able to read it, for example by "
                 "starting it from a USB stick with Ubuntu or a related Linux. A BIOS password "
                 "that blocks starting from USB helps against that. Don’t use this password "
                 "anywhere else.")
        if system.secure_boot() is not True:
            text += "\n\n" + _("Secure Boot is off. Then the TPM chip protects your password "
                               "only weakly: someone who has this computer may be able to "
                               "read it. Do not use this password anywhere else.")
        dialog = Adw.AlertDialog.new(_("Unlock the keyring with your face?"), text)
        # Vor dem Anzeigen merken: GTK kann die zweite Meldung schon während present() schicken
        self.schluessel_dialog = dialog
        self.e_passwort = Adw.PasswordEntryRow(title=_("Your login password"),
                                               activates_default=True)
        liste = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        liste.add_css_class("boxed-list")
        liste.append(self.e_passwort)
        # Feste Breite: Das Passwortfeld ist mit und ohne Fokus unterschiedlich breit; der Dialog
        # würde sich beim Klick auf „Versiegeln“ neu ausrichten und der Klick ginge ins Leere
        liste.set_size_request(400, -1)
        dialog.set_extra_child(liste)
        dialog.add_response("abbrechen", _("Cancel"))
        dialog.add_response("ok", _("Seal"))
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("ok")   # Enter im Passwortfeld versiegelt
        dialog.set_close_response("abbrechen")

        def antwort(_d, r):
            self.schluessel_dialog = None
            passwort = self.e_passwort.get_text()
            self.e_passwort.set_text("")
            if r == "ok" and passwort:
                GLib.idle_add(lambda: self.schluesselbund_versiegeln(passwort) and False)
            else:
                self.aktualisieren()

        dialog.connect("response", antwort)
        dialog.present(self)

    def schluesselbund_versiegeln(self, passwort):
        self._verwalten(["schluesselbund", "an"],
                        _("After the next restart, your face also opens the keyring"),
                        eingabe=passwort.encode() + b"\n")

    def _anmeldung_umgeschaltet(self, zeile, _pspec):
        # GTK meldet ein Umschalten manchmal doppelt: nur auf echte Änderungen reagieren
        if self._schalter_sperre or zeile.get_active() == self.zustand.anmeldung:
            return
        if zeile.get_active():
            if getattr(self, "anmeldung_dialog", None):   # schon offen: kein zweiter Dialog
                return
            # Erst den Risikohinweis zeigen, dann nach dem Administratorpasswort fragen
            dialog = Adw.AlertDialog.new(
                _("Also log in with your face after a restart?"),
                _("Your face also logs you in after a restart. The login keyring then stays "
                  "locked and asks for the password when a program needs it. Someone who looks "
                  "very much like you, or holds the computer up to your face, gets in without "
                  "the password from a switched-off computer too."))
            dialog.add_response("abbrechen", _("Cancel"))
            dialog.add_response("an", _("Turn on"))
            dialog.set_response_appearance("an", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_close_response("abbrechen")
            self.anmeldung_dialog = dialog

            def antwort(_d, r):
                self.anmeldung_dialog = None
                if r == "an":
                    GLib.idle_add(lambda: self._verwalten(
                        ["anmeldung", "an"], _("Your face now also logs you in after a restart"),
                        admin=True) and False)
                else:
                    self.aktualisieren()

            dialog.connect("response", antwort)
            dialog.present(self)
        else:
            self._verwalten(["anmeldung", "aus"],
                            _("After a restart, the password is required again"), admin=True)

    def _dialoge_umgeschaltet(self, zeile, _pspec):
        # GTK meldet ein Umschalten manchmal doppelt: nur auf echte Änderungen reagieren
        if self._schalter_sperre or zeile.get_active() == self.zustand.dialoge:
            return
        if zeile.get_active():
            self._verwalten(["dialoge", "an"],
                            _("Administrator dialogs can now be approved with face and ✌"),
                            admin=True, danach=lambda ok, _e, _m: ok and self._hinweis_starten())
        else:
            self._verwalten(["dialoge", "aus"], _("Administrator dialogs are back to password only"),
                            admin=True)

    def _entsperren_geste_umgeschaltet(self, zeile, _pspec):
        # GTK meldet ein Umschalten manchmal doppelt: nur auf echte Änderungen reagieren
        if self._schalter_sperre or zeile.get_active() == self.zustand.entsperren_geste:
            return
        if zeile.get_active():
            self._verwalten(["entsperren-geste", "an"],
                            _("From now on, unlocking needs your face and ✌"), admin=True)
        else:
            self._verwalten(["entsperren-geste", "aus"],
                            _("Your face alone unlocks again"), admin=True)

    def _ir_schutz_umgeschaltet(self, zeile, _pspec):
        # GTK meldet ein Umschalten manchmal doppelt: nur auf echte Änderungen reagieren
        if self._schalter_sperre or zeile.get_active() == self.zustand.ir_schutz:
            return
        if zeile.get_active():
            self._verwalten(["ir-schutz", "an"],
                            _("Only Winky can use the infrared camera now"), admin=True)
        else:
            self._verwalten(["ir-schutz", "aus"],
                            _("The infrared camera is available to all programs again"), admin=True)

    def _desktop(self):
        """Sitzungs- und Sperreinstellungen von GNOME; None, wenn es sie nicht gibt."""
        if not hasattr(self, "_desktop_einst"):
            quelle = Gio.SettingsSchemaSource.get_default()
            if quelle and quelle.lookup("org.gnome.desktop.session", True) and \
                    quelle.lookup("org.gnome.desktop.screensaver", True):
                self._desktop_einst = (Gio.Settings.new("org.gnome.desktop.session"),
                                       Gio.Settings.new("org.gnome.desktop.screensaver"))
            else:
                self._desktop_einst = None
        return self._desktop_einst

    def _sperrzeit_zeigen(self):
        einst = self._desktop()
        if einst is None:
            for zeile in (self.r_sperre_an, self.r_sperrzeit):
                zeile.set_sensitive(False)
            self.r_sperre_an.set_subtitle(_("Not available on this desktop"))
            return
        sitzung, sperre = einst
        sekunden = sitzung.get_uint("idle-delay")
        an = sekunden > 0 and sperre.get_boolean("lock-enabled")
        self._sperrzeit_sperre = True
        self.r_sperre_an.set_active(an)
        fokus = self.get_focus()   # beim Tippen nicht überschreiben (Aktualisierung alle 15 s)
        tippt = fokus is not None and (fokus == self.r_sperrzeit or
                                       fokus.is_ancestor(self.r_sperrzeit))
        if sekunden and not tippt:
            self.r_sperrzeit.set_value(max(1, min(60, round(sekunden / 60))))
        self._sperrzeit_sperre = False
        self.r_sperrzeit.set_sensitive(an)
        self.r_sperre_an.set_subtitle(
            _("Without input, the screen turns off and locks") if an else
            _("Never locks by itself; lock with Super+L"))
        if an and sperre.get_uint("lock-delay"):
            self.r_sperrzeit.set_subtitle(_("Locks {seconds} s after the screen turns off").format(
                seconds=sperre.get_uint("lock-delay")))
        elif an and (sekunden % 60 or sekunden > 3600):
            self.r_sperrzeit.set_subtitle(_("Currently {minutes} minutes (set in the system "
                                            "settings)").format(minutes=round(sekunden / 60)))
        else:
            self.r_sperrzeit.set_subtitle("")

    def _sperre_setzen(self):
        """Bildschirm nach der eingestellten Zeit aus und sofort gesperrt."""
        sitzung, sperre = self._desktop()
        sitzung.set_uint("idle-delay", int(self.r_sperrzeit.get_value()) * 60)
        sperre.set_boolean("lock-enabled", True)
        sperre.set_uint("lock-delay", 0)

    def _sperre_umgeschaltet(self, zeile, _pspec):
        if getattr(self, "_sperrzeit_sperre", False) or self._desktop() is None:
            return
        if zeile.get_active():
            self._sperre_setzen()
        else:
            # Wie der Schalter in den GNOME-Einstellungen: Bildschirm geht weiter aus, sperrt nicht
            self._desktop()[1].set_boolean("lock-enabled", False)
        self._sperrzeit_zeigen()

    def _sperrzeit_gewaehlt(self, _zeile, _pspec):
        if getattr(self, "_sperrzeit_sperre", False) or self._desktop() is None \
                or not self.r_sperre_an.get_active():
            return
        self._sperre_setzen()
        self._sperrzeit_zeigen()

    def _vorlagen_tpm_umgeschaltet(self, zeile, _pspec):
        # GTK meldet ein Umschalten manchmal doppelt: nur auf echte Änderungen reagieren
        if self._schalter_sperre or zeile.get_active() == self.zustand.vorlagen_tpm:
            return
        if not zeile.get_active():
            self._verwalten(["vorlagen-tpm", "aus"],
                            _("Face data is stored unencrypted again"), admin=True)
            return
        if getattr(self, "tpm_dialog", None):   # schon offen: kein zweiter Dialog
            return
        text = _(
            "Your face data (numbers, no photos) is then stored on the disk only encrypted. "
            "The key is in this computer’s TPM chip. When the computer starts, Winky unseals the "
            "data into memory only, so unlocking stays just as fast.\n\n"
            "This helps if someone reads your disk in another computer or from Windows on the "
            "same computer (dual boot). It doesn’t help if someone starts this computer from a "
            "USB stick with Ubuntu or a related Linux: Secure Boot accepts it, so the TPM chip "
            "unseals the data there too. A BIOS password that blocks starting from USB helps "
            "against that. If your disk is already encrypted, sealing adds little.\n\n"
            "Please note: after a BIOS or firmware update, or if Secure Boot is turned on or off, "
            "the TPM chip may refuse the data. Winky then tells you, and you record your face "
            "again. Your password always works. The previous unencrypted data is deleted; on "
            "SSDs, remnants can’t be ruled out completely, so record your face again afterwards "
            "if that matters to you.")
        if system.secure_boot() is not True:
            text += "\n\n" + _("Secure Boot is off. Then the TPM chip protects the data only "
                                 "weakly.")
        dialog = Adw.AlertDialog.new(_("Seal your face data in the TPM chip?"), text)
        dialog.add_response("abbrechen", _("Cancel"))
        dialog.add_response("an", _("Seal"))
        dialog.set_response_appearance("an", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_close_response("abbrechen")
        self.tpm_dialog = dialog

        def antwort(_d, r):
            self.tpm_dialog = None
            if r == "an":
                GLib.idle_add(lambda: self._verwalten(
                    ["vorlagen-tpm", "an"], _("Your face data is now sealed in the TPM chip"),
                    admin=True) and False)
            else:
                self.aktualisieren()

        dialog.connect("response", antwort)
        dialog.present(self)

    def _hinweis_starten(self):
        """Das Hinweisprogramm startet sonst erst bei der nächsten Anmeldung."""
        if umgebung.ATTRAPPE or not os.path.exists(HINWEIS):
            return
        laeuft = subprocess.run(["pgrep", "-u", str(os.getuid()), "-f", HINWEIS],
                                capture_output=True).returncode == 0
        if not laeuft:
            subprocess.Popen([HINWEIS], start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _pause_umgeschaltet(self, zeile, _pspec):
        # GTK meldet ein Umschalten manchmal doppelt: nur auf echte Änderungen reagieren
        if self._schalter_sperre or zeile.get_active() == self.zustand.pausiert:
            return
        self._verwalten(["pausieren" if zeile.get_active() else "fortsetzen"],
                        _("Paused: only the password works everywhere") if zeile.get_active()
                        else _("Winky is back"), admin=True)

    # Anzeige

    def _darf_aktivieren(self):
        z, s = self.zustand, stand(self.zustand)
        if not (z.installiert and z.dienst):
            return False, _("Winky isn’t fully installed.")
        if not z.kamera:
            return False, _("Set up the camera first.")
        if not z.eingelernt:
            return False, _("Record your face first.")
        if not s["testen"]:
            return False, _("First try it out successfully once.")
        if z.schwelle <= 0:
            return False, _("No strictness set (Advanced).")
        if s["gegenprobe"] is False:
            return False, _("The second person looked too much like you. Make Winky stricter in "
                            "the previous step.")
        return True, _("Ready to turn on.")

    def aktualisieren(self):
        self.zustand = z = system.lese_zustand()
        s = stand(z)
        laeuft = self.beschaeftigt()
        bereit = z.installiert and z.dienst
        fertig_eingerichtet = z.eingelernt and s["testen"] and z.aktiv

        self.banner.set_revealed(not bereit)
        if not bereit:
            art, symbol, titel, inhalt = (
                "fehlt", "dialog-warning-symbolic", _("Winky is missing something"),
                _("Without this part, Winky can’t check anything. Until then, your password "
                  "works everywhere."))
        elif z.eingelernt and z.vorlagen_tpm and z.tpm_fehler:
            art, symbol, titel, inhalt = (
                "fehlt", "dialog-warning-symbolic", _("Record your face again"),
                _("Your sealed face data can’t be unsealed anymore, for example after a BIOS "
                  "update. Until you record your face again under “Face”, only your password "
                  "works."))
        elif z.pausiert:
            art, symbol, titel, inhalt = (
                "pause", "media-playback-pause-symbolic", _("Winky is paused"),
                _("Right now, only your password works everywhere."))
        elif fertig_eingerichtet:
            art, symbol, titel, inhalt = (
                "an", "emblem-ok-symbolic", _("Winky is on"),
                _("Lock the screen with Super+L. To unlock, press a key, look at the camera and "
                  "show ✌.") if z.entsperren_geste else
                _("Lock the screen with Super+L. To unlock, press a key and look at the "
                  "camera."))
        elif z.aktiv and not z.eingelernt:
            art, symbol, titel, inhalt = (
                "neu", "avatar-default-symbolic", _("Not set up for you yet"),
                _("Winky is on for this computer. Record your face so you can use it too."))
        elif z.eingelernt:
            art, symbol, titel, inhalt = (
                "neu", "avatar-default-symbolic", _("Almost done"),
                _("Your face is recorded. Finish the setup to turn on Winky."))
        else:
            art, symbol, titel, inhalt = (
                "neu", "avatar-default-symbolic", _("Welcome to Winky"),
                _("Unlock the lock screen with a glance at the camera. Setup takes about two "
                  "minutes."))
        for a in ("an", "pause", "neu", "fehlt"):
            self.s_kreis.remove_css_class(a)
        self.s_kreis.add_css_class(art)
        self.s_kreis.set_visible(art != "neu")
        self.s_symbol.set_from_icon_name(symbol)
        self.s_titel.set_label(titel)
        self.s_text.set_label(inhalt)
        self.s_einrichten.set_visible(bereit and not fertig_eingerichtet and not z.pausiert)
        self.s_einrichten.set_label(_("Continue setup") if z.eingelernt or z.kamera
                                    else _("Start setup"))
        self.s_einrichten.set_sensitive(not laeuft)
        self.r_probe.set_visible(bereit and z.eingelernt and not z.pausiert)
        self.r_pause.set_visible(bereit and (z.aktiv or z.pausiert))
        self.s_pause_inhalt.set_label(_("Resume") if z.pausiert else _("Pause"))
        self.s_pause_inhalt.set_icon_name("media-playback-start-symbolic" if z.pausiert
                                          else "media-playback-pause-symbolic")

        # Schalter
        darf, grund = self._darf_aktivieren()
        info = system.keepassxc_info() if bereit else {"polkit_aktion": False, "gefunden": None}
        self.freigaben_stapel.set_visible_child_name(
            "inhalt" if bereit and (z.aktiv or z.pausiert or s["testen"]) else "leer")
        self._schalter_sperre = True
        self.r_aktiv.set_active(z.aktiv)
        self.r_aktiv.set_sensitive((darf or z.aktiv) and not laeuft)
        self.r_aktiv.set_subtitle(_("Unlock with a glance at the camera") if darf or z.aktiv
                                  else grund)
        self.r_anmeldung.set_active(z.anmeldung)
        self.r_anmeldung.set_sensitive((z.aktiv or z.anmeldung) and not laeuft)
        self.r_schluesselbund.set_visible(z.anmeldung or bool(z.schluesselbund))
        self.r_schluesselbund.set_active(bool(z.schluesselbund))
        self.r_schluesselbund.set_sensitive(not laeuft)
        self.r_schluesselbund.set_subtitle(
            _("Your password has changed. Turn this on again to keep using it.")
            if z.schluesselbund_veraltet and not z.schluesselbund else
            _("Your login password is stored sealed in the TPM chip. Caution: whoever has this "
              "computer may be able to read it."))
        self.s_sudo.set_active(z.sudo)
        self.s_sudo.set_sensitive(((z.aktiv and s["geste"]) or z.sudo) and not laeuft)
        self.k_sudo_einrichten.set_visible(not s["geste"] and not z.sudo)
        self.k_sudo_einrichten.set_sensitive(z.eingelernt and not laeuft)
        self.r_sudo.set_subtitle(
            _("Confirm commands with face and ✌") if z.sudo or (z.aktiv and s["geste"]) else
            _("Turn on the lock screen first") if not z.aktiv else
            _("Test face and ✌ first"))
        self.w_sudo.set_active(z.sudo)
        self.w_sudo.set_sensitive(((z.aktiv and s["geste"]) or z.sudo) and not laeuft)
        self.w_sudo.set_subtitle(_("Changing this needs the administrator password")
                                 if z.aktiv and s["geste"]
                                 else _("Pass the test above first") if z.aktiv else
                                 _("Turn on the lock screen first"))
        kp_geste_fehlt = z.keepassxc_geste and not s["geste"]
        kp_bereit = bereit and z.eingelernt and s["testen"] and not kp_geste_fehlt
        kp_sichtbar = z.keepassxc or bool(info.get("gefunden")) or bool(info.get("polkit_aktion"))
        self.r_keepassxc.set_visible(kp_sichtbar)
        self.r_keepassxc.set_active(z.keepassxc)
        self.r_keepassxc.set_sensitive((kp_bereit or z.keepassxc) and not laeuft)
        if kp_geste_fehlt and not z.keepassxc:
            kp_text = _("Test face and ✌ first")
        elif info.get("polkit_aktion"):
            kp_text = (_("Open the password database with your face and ✌") if z.keepassxc_geste
                       else _("Open the password database with your face"))
        else:
            kp_text = (_("Open the password database with your face and ✌ (needs KeePassXC 2.8 "
                         "or later, see Advanced)") if z.keepassxc_geste
                       else _("Open the password database with your face (needs KeePassXC 2.8 or "
                              "later, see Advanced)"))
        self.r_keepassxc.set_subtitle(kp_text)
        self.r_keepassxc_geste.set_visible(kp_sichtbar)
        self.r_keepassxc_geste.set_active(z.keepassxc_geste)
        self.r_keepassxc_geste.set_sensitive(bereit and not laeuft)
        gefunden = info.get("gefunden")
        self.r_keepassxc_version.set_visible(kp_sichtbar and not info.get("polkit_aktion"))
        rest = _("Older versions and the Flatpak version can’t do this: there, KeePassXC asks "
                 "for the master password as usual, and Winky isn’t asked at all.")
        self.r_keepassxc_version.set_subtitle(
            _("Found: {found}.").format(found=gefunden) + " " + rest if gefunden else rest)
        self.r_pause.set_active(z.pausiert)
        self.r_pause.set_sensitive(bereit and (z.aktiv or z.pausiert) and not laeuft)
        self._sperrzeit_zeigen()
        self.r_entsperren_geste.set_active(z.entsperren_geste)
        self.r_entsperren_geste.set_sensitive(((z.aktiv and s["geste"]) or z.entsperren_geste)
                                              and not laeuft)
        self.r_entsperren_geste.set_subtitle(
            _("Face and ✌ for the lock screen and login") if z.entsperren_geste else
            _("Protects against someone holding the computer up to your face")
            if z.aktiv and s["geste"] else
            _("Turn on the lock screen first") if not z.aktiv else _("Test face and ✌ first"))
        self.r_dialoge.set_active(z.dialoge)
        self.r_dialoge.set_sensitive(((z.aktiv and s["geste"]) or z.dialoge) and not laeuft)
        self.r_dialoge.set_subtitle(
            _("Approve password dialogs such as updates with face and ✌; the dialog shows what")
            if z.dialoge or (z.aktiv and s["geste"]) else
            _("Turn on the lock screen first") if not z.aktiv else _("Test face and ✌ first"))
        self._schalter_sperre = False

        # Ausprobieren und pflegen
        self.gesicht_stapel.set_visible_child_name("inhalt" if bereit and z.eingelernt
                                                   else "leer")
        for r in (self.r_probe, self.r_testen, self.r_ergaenzen, self.r_neu, self.r_zweite,
                  self.r_geste):
            r.set_sensitive(not laeuft)
        self.r_zweite.set_subtitle({None: _("Recommended: checks that Winky only recognizes you"),
                                    True: _("Passed, Winky only recognizes you"),
                                    False: _("Too similar. Make it stricter here.")
                                    if strenger_moeglich(z) else
                                    _("Too similar; Winky can’t reliably tell you apart")}
                                   [s["gegenprobe"]])
        self.r_geste.set_subtitle(_("Passed ({date})").format(date=datum(z.geste_ok))
                                  if s["geste"] else
                                  _("Needed if you want to confirm sudo with ✌"))

        self._verlauf_zeigen(bereit and z.eingelernt)
        self._ergaenzungen_zeigen()

        # Assistent und Kameraabläufe
        if z.kamera:
            self.w_kamera_status.set_label(
                _("✓ Camera is set up: {name}").format(name=self.kamera_name) if self.kamera_name
                else _("✓ Camera is set up"))
        elif self.w_kamera_status.get_label().startswith("✓"):
            self.w_kamera_status.set_label("")
        self.w_kamera_knopf.set_label(_("Search one more time") if z.kamera
                                      else _("Search for camera"))
        self.w_kamera_knopf.set_sensitive(bereit and not laeuft)
        self.w_einschalten.set_visible(not z.aktiv)
        self.w_einschalten.set_sensitive(darf and not laeuft)
        self.w_einschalten_status.set_label(
            _("✓ Turned on") if z.aktiv else "" if darf else grund)
        for a in self.ablaeufe:
            a.aktualisieren(z, s, bereit, laeuft)
        self._assistent_anzeigen()

        # Erweitert
        self.r_kamera.set_subtitle(z.kamera or _("None set up yet"))
        self._schalter_sperre = True
        self.r_ir_schutz.set_active(z.ir_schutz)
        self._schalter_sperre = False
        self.r_ir_schutz.set_sensitive(((bereit and bool(z.kamera)) or z.ir_schutz) and not laeuft)
        self.r_ir_schutz.set_subtitle(
            _("Not effective: programs can still open the infrared camera. Turn it off and on "
              "again.") if z.ir_schutz and z.ir_offen else
            _("Other programs can’t switch on the infrared camera") if z.ir_schutz else
            _("Set up the camera first.") if not z.kamera else
            _("Otherwise every program in your account can switch on the infrared camera"))
        self.k_kamera_suchen.set_sensitive(bereit and not laeuft)
        self.k_kamera_wahl.set_sensitive(bereit and not laeuft)
        if z.schwelle > 0 and not self.r_spin.has_focus():
            self.r_spin.set_value(z.schwelle)
        self.r_spin.set_sensitive(bereit and not laeuft)
        self.k_speichern.set_sensitive(bereit and not laeuft)
        if not self.r_geste_zeit.has_focus():
            self.r_geste_zeit.set_value(z.geste_zeit)
        self.r_geste_zeit.set_sensitive(bereit and not laeuft)
        self.k_geste_zeit.set_sensitive(bereit and not laeuft)
        self.r_geste_zeit_speichern.set_subtitle(
            _("Currently set: {value} seconds").format(value=z.geste_zeit))
        self.r_speichern.set_subtitle(
            _("Currently set: {value}").format(value=komma(z.schwelle, 2)) if z.schwelle > 0
            else _("Not set yet"))
        du = komma(z.test_wert, 2) if s["testen"] else None
        andere = komma(z.gegenprobe_wert, 2) if z.gegenprobe_wert is not None else None
        if du and andere:
            werte = _("Similarity: you on your last try {you}, the second person "
                      "{other}").format(you=du, other=andere)
        elif du:
            werte = _("Similarity: you on your last try {you}").format(you=du)
        elif andere:
            werte = _("Similarity: the second person {other}").format(other=andere)
        else:
            werte = _("None yet")
        self.r_messwerte.set_subtitle(werte)
        self.r_vorlagen.set_subtitle(_("Recorded {date}, readable only by the system, no "
                                       "photos").format(date=datum(z.eingelernt_am))
                                     if z.eingelernt else _("None"))
        self.k_daten_weg.set_sensitive(z.eingelernt and not laeuft)
        self._schalter_sperre = True
        self.r_vorlagen_tpm.set_active(z.vorlagen_tpm)
        self._schalter_sperre = False
        self.r_vorlagen_tpm.set_sensitive(bereit and not laeuft)
        self.r_vorlagen_tpm.set_subtitle(
            _("Can’t be unsealed anymore (the TPM chip changed). Record your face again.")
            if z.vorlagen_tpm and z.tpm_fehler else
            _("Your face data is stored on the disk only encrypted") if z.vorlagen_tpm else
            _("Helps if your disk is read in another computer or from Windows (dual boot)"))
        if info.get("polkit_aktion"):
            self.r_keepassxc_symbol.set_from_icon_name("emblem-ok-symbolic")
            self.r_keepassxc_info.set_subtitle(
                _("Found KeePassXC with quick unlock. In KeePassXC, turn on quick unlock under "
                  "Settings, Security."))
        else:
            self.r_keepassxc_symbol.set_from_icon_name("dialog-information-symbolic")
            gefunden = info.get("gefunden")
            vorab = (_("Found: {found}.").format(found=gefunden) if gefunden
                     else _("No KeePassXC found."))
            self.r_keepassxc_info.set_subtitle(
                vorab + " " + _("You need KeePassXC 2.8 or later as a normal package, because "
                                "only that registers quick unlock with the system. You can "
                                "already turn it on beforehand."))
        v = umgebung.version()
        self.r_version.set_subtitle(_("{version} · revision {commit} · built {built}").format(
            version=v.get("version"), commit=v.get("commit"), built=v.get("gebaut")))
        self.r_dienst.set_subtitle(_("Ready (starts when needed)") if z.dienst
                                   else _("Not active"))

    def _verlauf_zeigen(self, sichtbar):
        for r in self._verlauf_zeilen:
            self.g_verlauf.remove(r)
        self._verlauf_zeilen = []
        eintraege = system.verlauf(20) if sichtbar else []
        letzte = next((e for e in eintraege or [] if e["status"] == "treffer"
                       and e.get("zweck") in ("sperrbildschirm", "anmeldung")), None)
        self.s_zuletzt.set_label(_("Last unlocked {date}").format(date=datum(letzte["zeit"]))
                                 if letzte else "")
        self.s_zuletzt.set_visible(letzte is not None)
        if eintraege is None:
            zeilen = [textzeile(_("Can’t read the history"),
                                _("The system log isn’t accessible for your account."))]
        elif not eintraege:
            zeilen = [textzeile(_("Nothing has happened yet"),
                                _("Lock the screen with Super+L."))]
        else:
            zeilen = []
            for e in eintraege:
                ok = e["status"] == "treffer"
                if e.get("zweck") == "sudo" and e.get("grund") == "passwort":
                    titel = (_("sudo: password typed instead of ✌: {command}").format(
                        command=e["befehl"]) if e.get("befehl")
                        else _("sudo: password typed instead of ✌"))
                elif e.get("zweck") == "sudo":
                    if e.get("befehl"):
                        titel = (_("sudo confirmed: {command}") if ok
                                 else _("sudo not confirmed: {command}")).format(
                                     command=e["befehl"])
                    else:
                        titel = _("sudo confirmed") if ok else _("sudo not confirmed")
                elif e.get("zweck") == "keepassxc":
                    titel = _("KeePassXC opened") if ok else _("KeePassXC: password needed")
                elif e.get("zweck") == "dialog":
                    # Welche Aktion, zeigt nur der Passwortdialog; Winky erfährt sie nicht
                    titel = (_("Administrator dialog approved with ✌") if ok
                             else _("Administrator dialog not approved"))
                elif e.get("zweck") == "anmeldung" and ok:
                    titel = _("Logged in with your face after startup")
                else:
                    titel = system.STATUS_TEXTE.get(e["status"], e["status"])
                zeilen.append(textzeile(
                    titel, _("{date}, after {seconds} s").format(
                        date=datum(e["zeit"]), seconds=komma(e["dauer_ms"] / 1000, 1)),
                    "emblem-ok-symbolic" if ok else "dialog-information-symbolic"))
        for r in zeilen:
            self.g_verlauf.add(r)
            self._verlauf_zeilen.append(r)

    def _schliessen(self, *_):
        for lauf in (self.gesicht_lauf, self.aktion):
            if lauf:
                lauf.abbrechen()
        return False


# Seite „Sicherheit und Hilfe“ ohne Fachbegriffe; ausführlich in SICHERHEIT.md
SICHERHEIT = [
    (_("What Winky can do"), None, "emblem-ok-symbolic", [
        (_("Unlock the lock screen with your face"),
         _("Only the lock of a running session, unless you also turn on login after startup. "
           "The keyring then stays locked, unless you also let Winky unlock it (experimental).")),
        (_("Optionally confirm sudo with face and ✌"),
         _("Only in a terminal on the computer itself, only with both together, and only if "
           "you turn it on.")),
        (_("Optionally open KeePassXC"),
         _("Only with KeePassXC 2.8 or later as a normal package, after you first open it with "
           "the master password. By default only with face and ✌.")),
        (_("Several people on the same computer"),
         _("Each person records their own face with their own password.")),
    ]),
    (_("What Winky can’t do"), None, "dialog-information-symbolic", [
        (_("Replace your password"),
         _("The password always works. It’s the only way in after failed attempts and during a "
           "pause, and after you turn on the computer unless you allow your face there.")),
        (_("Reliably tell twins or very similar siblings apart"),
         _("No face recognition can do that. The check with a second person shows whether it’s "
           "a close call.")),
        (_("Work with a normal webcam"),
         _("Winky needs an infrared camera, like the ones built in for Windows Hello.")),
        (_("Tell whether you agree"),
         _("Someone could hold the computer up to your face. That’s why sudo also needs the "
           "✌, and under Unlocks you can require it for unlocking too.")),
    ]),
    (_("What to watch out for"), None, "dialog-warning-symbolic", [
        (_("Lock the screen when you walk away"),
         _("Super+L. Winky only protects what is locked.")),
        (_("Do the check with a second person"),
         _("Ideally with a family member who looks like you.")),
        (_("If a sudo message appears that you didn’t expect: don’t show ✌"),
         _("Then a program asked for administrator rights without you. Just ignore it, the "
           "request ends after a few seconds.")),
        (_("Anyone who looks very much like you shouldn’t be able to use Winky"),
         _("In that case, make Winky stricter (Advanced) or leave it off.")),
    ]),
    (_("Technical limits"), None, "security-medium-symbolic", [
        (_("A photo on a screen or phone doesn’t fool Winky"),
         _("Screens look black in the infrared image. An elaborately made printout or a mask "
           "could, though, just like with Windows Hello without extra protection.")),
        (_("Winky doesn’t protect against someone taking your computer away"),
         _("For that you need an encrypted hard drive. Winky makes the lock screen more "
           "convenient, it isn’t theft protection.")),
        (_("A harmful program running as you can trigger a sudo request"),
         _("But nothing happens without your ✌, and every request shows up as a message with "
           "the command. After three unconfirmed requests, only the password works for 10 "
           "minutes.")),
    ]),
    (_("If something goes wrong"), None, "help-browser-symbolic", [
        (_("The password always works"),
         _("If Winky doesn’t recognize you, the password field appears after three seconds at "
           "most.")),
        (_("Pause in the overview"),
         _("Turns off Winky everywhere right away, then only your password works. Nothing is "
           "deleted; “Resume” turns everything back on.")),
        (_("Emergency off switch without this app"),
         _("Ctrl+Alt+F3, sign in with your username and password, then type:\n"
           "sudo touch /etc/winky/disabled")),
        (_("Uninstall"),
         _("In the Software app under “Installed”. After that, only the password works "
           "everywhere again.")),
    ]),
    (_("Note"), None, "dialog-information-symbolic", [
        (_("Use at your own risk"),
         _("Winky is a convenience feature. It doesn’t replace a strong password or an "
           "encrypted hard drive.")),
    ]),
]


def main():
    flags = Gio.ApplicationFlags.DEFAULT_FLAGS
    if umgebung.ATTRAPPE:  # Test neben einer laufenden echten App
        flags |= Gio.ApplicationFlags.NON_UNIQUE
    app = Adw.Application(application_id=APP_ID, flags=flags)
    app.connect("activate", lambda a: (a.get_active_window() or Fenster(a)).present())
    return app.run(sys.argv[:1])


if __name__ == "__main__":
    sys.exit(main())
