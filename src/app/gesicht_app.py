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
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import system  # noqa: E402
import umgebung  # noqa: E402
from prozess import Prozess  # noqa: E402
from sprache import _  # noqa: E402
from vorschau import Vorschau, css_laden, komma  # noqa: E402

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
        # Kleiner als die Kamera (640 x 360), damit Knopf und Ergebnis ohne Blättern sichtbar sind
        self.vorschau = Vorschau(512, 288)
        self.vorschau.set_halign(Gtk.Align.CENTER)
        self.append(self.vorschau)
        self.live = text("", "title-4", mitte=True)
        self.append(self.live)
        self.fortschritt = Gtk.ProgressBar(visible=False)
        self.append(self.fortschritt)
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
        self.setze_art(art)

    def setze_art(self, art):
        self.art = art
        a = ABLAEUFE[art]
        self.titel.set_label(a["titel"])
        while (kind := self.anleitung.get_first_child()) is not None:
            self.anleitung.remove(kind)
        for i, schritt in enumerate(a["schritte"], 1):
            self.anleitung.append(text(f"{i}.  {schritt}"))
        self.hinweis.set_label(a["hinweis"])
        self.zuruecksetzen()

    def zuruecksetzen(self):
        self.vorschau.leeren()
        self.live.set_label("")
        self.ergebnis.set_label("")
        self.fortschritt.set_visible(False)

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
                    "gegenprobe": s["gegenprobe"] is not None, "geste-testen": s["geste"]}
        self.k_start.set_label(a["nochmal"] if erledigt[self.art] else a["knopf"])
        moeglich = bereit and (bool(z.kamera) if self.art == "einlernen" else z.eingelernt)
        self.k_start.set_sensitive(moeglich and not laeuft)
        self.k_start.set_visible(not meiner)
        self.k_abbruch.set_visible(meiner)
        self.k_strenger.set_visible(self.art == "gegenprobe" and s["gegenprobe"] is False
                                    and strenger_moeglich(z))
        self.k_strenger.set_sensitive(not laeuft)
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
        self.set_default_size(820, 900)
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
        self.nav.add(self._baue_sicherheit())
        self.nav.add(self._baue_erweitert())
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
        if not self.beschaeftigt():
            self.aktualisieren()
        return True

    def beschaeftigt(self):
        return self.aktion is not None or self.gesicht_lauf is not None

    # Startseite

    def _baue_start(self):
        s = Adw.PreferencesPage()
        kopf = Adw.PreferencesGroup()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=12,
                      margin_bottom=6)
        self.s_symbol = Gtk.Image(pixel_size=96)
        box.append(self.s_symbol)
        self.s_titel = text("", "title-1", mitte=True)
        box.append(self.s_titel)
        self.s_text = text("", mitte=True, breite=60)
        box.append(self.s_text)
        self.s_einrichten = knopf(_("Start setup"), self.einrichtung_oeffnen, "pill",
                                  "suggested-action")
        self.s_einrichten.set_halign(Gtk.Align.CENTER)
        self.s_einrichten.set_margin_top(8)
        box.append(self.s_einrichten)
        kopf.add(box)
        s.add(kopf)

        self.g_schalter = Adw.PreferencesGroup(
            title=_("What Winky unlocks for you"),
            description=_("To change these, your computer asks for the administrator password."))
        self.r_aktiv = Adw.SwitchRow(title=_("Lock screen"),
                                     subtitle=_("Unlock with a glance at the camera"))
        self.r_aktiv.add_prefix(Gtk.Image(icon_name="system-lock-screen-symbolic"))
        self.r_aktiv.connect("notify::active", self._aktiv_umgeschaltet)
        self.g_schalter.add(self.r_aktiv)
        self.r_anmeldung = Adw.SwitchRow(
            title=_("Login after startup"),
            subtitle=_("Caution: your face also logs you in after a restart. The login keyring "
                       "then stays locked and asks for the password when a program needs it."))
        warnsymbol = Gtk.Image(icon_name="dialog-warning-symbolic")
        warnsymbol.add_css_class("warning")
        self.r_anmeldung.add_prefix(warnsymbol)
        self.r_anmeldung.connect("notify::active", self._anmeldung_umgeschaltet)
        self.g_schalter.add(self.r_anmeldung)
        self.r_schluesselbund = Adw.SwitchRow(title=_("Also unlock the keyring (experimental)"))
        symbol = Gtk.Image(icon_name="dialog-warning-symbolic")
        symbol.add_css_class("warning")
        self.r_schluesselbund.add_prefix(symbol)
        self.r_schluesselbund.connect("notify::active", self._schluesselbund_umgeschaltet)
        self.g_schalter.add(self.r_schluesselbund)
        # Kein SwitchRow: „Einrichten“ muss bedienbar sein, solange der Schalter gesperrt ist
        self.r_sudo = Adw.ActionRow(title=_("sudo in the terminal"))
        self.r_sudo.add_prefix(Gtk.Image(icon_name="utilities-terminal-symbolic"))
        self.k_sudo_einrichten = knopf(_("Set up"), lambda: self.kamera_oeffnen("geste-testen"))
        self.r_sudo.add_suffix(self.k_sudo_einrichten)
        self.s_sudo = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.s_sudo.connect("notify::active", self._sudo_umgeschaltet)
        self.r_sudo.add_suffix(self.s_sudo)
        self.r_sudo.set_activatable_widget(self.s_sudo)
        self.g_schalter.add(self.r_sudo)
        self.r_dialoge = Adw.SwitchRow(title=_("Administrator dialogs"))
        self.r_dialoge.add_prefix(Gtk.Image(icon_name="dialog-password-symbolic"))
        self.r_dialoge.connect("notify::active", self._dialoge_umgeschaltet)
        self.g_schalter.add(self.r_dialoge)
        self.r_keepassxc = Adw.SwitchRow(title="KeePassXC")
        self.r_keepassxc.add_prefix(Gtk.Image(icon_name="dialog-password-symbolic"))
        self.r_keepassxc.connect("notify::active", self._keepassxc_umgeschaltet)
        self.g_schalter.add(self.r_keepassxc)
        self.r_keepassxc_geste = Adw.SwitchRow(
            title=_("KeePassXC only with ✌"),
            subtitle=_("Recommended: without your ✌ sign, nobody can open the database, not "
                       "even while you’re sitting at the computer"))
        self.r_keepassxc_geste.add_prefix(Gtk.Image(icon_name="security-high-symbolic"))
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
        self.r_pause = Adw.SwitchRow(title=_("Pause"),
                                     subtitle=_("Winky is resting, only your password works "
                                                "everywhere"))
        self.r_pause.add_prefix(Gtk.Image(icon_name="media-playback-pause-symbolic"))
        self.r_pause.connect("notify::active", self._pause_umgeschaltet)
        self.g_schalter.add(self.r_pause)
        s.add(self.g_schalter)

        self.g_pflege = Adw.PreferencesGroup(title=_("Try out and maintain"))
        self.r_probe = weiterzeile(_("Try out recognition"), _("Look at the camera and see "
                                                               "whether Winky recognizes you"),
                                   lambda: self.kamera_oeffnen("testen"), "camera-web-symbolic")
        self.r_neu = weiterzeile(_("Record your face again"), _("Helps if Winky has trouble "
                                                                "recognizing you, for example "
                                                                "with new glasses"),
                                 lambda: self.kamera_oeffnen("einlernen"), "view-refresh-symbolic")
        self.r_zweite = weiterzeile(_("Check with a second person"), "",
                                    lambda: self.kamera_oeffnen("gegenprobe"),
                                    "system-users-symbolic")
        self.r_geste = weiterzeile(_("Test face and ✌"), "",
                                   lambda: self.kamera_oeffnen("geste-testen"),
                                   "utilities-terminal-symbolic")
        for r in (self.r_probe, self.r_neu, self.r_zweite, self.r_geste):
            self.g_pflege.add(r)
        s.add(self.g_pflege)

        self.g_verlauf = Adw.PreferencesGroup(title=_("Recent activity"))
        self._verlauf_zeilen = []
        s.add(self.g_verlauf)

        mehr = Adw.PreferencesGroup()
        mehr.add(weiterzeile(_("Security and help"),
                             _("What Winky can and can’t do, emergency off switch"),
                             lambda: self.nav.push_by_tag("sicherheit"), "security-high-symbolic"))
        mehr.add(weiterzeile(_("Advanced"), _("Camera, strictness, delete data, uninstall"),
                             lambda: self.nav.push_by_tag("erweitert"),
                             "preferences-system-symbolic"))
        mehr.add(weiterzeile(_("About Winky"), _("Version, license and project page"),
                             self.ueber_zeigen, "help-about-symbolic"))
        s.add(mehr)

        self.banner = Adw.Banner(title=_("Part of Winky isn’t running. Reinstall Winky in the "
                                         "Software app."))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.banner)
        box.append(s)
        s.set_vexpand(True)
        return seite("Winky", "start", box)

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
                  "the camera. “Security and help” on the start page explains what to watch out "
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
            weiter = _("Go to start page")
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
        return seite(_("Security and help"), "sicherheit", s)

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
        return seite(_("Advanced"), "erweitert", s)

    # Kameraabläufe

    def lauf_starten(self, ansicht):
        if self.beschaeftigt():
            self.melde(_("Please wait, something else is still running"))
            return
        ansicht.zuruecksetzen()
        ansicht.live.set_label(_("Asking for your password and starting the camera …"))
        ansicht.vorschau.hinweis(_("Camera is starting …"), bis_bild=True)
        ansicht.fortschritt.set_fraction(0)
        try:
            self.gesicht_lauf = Prozess(umgebung.verwalten_befehl([ansicht.art]), self._g_bild,
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
            a.fortschritt.set_visible(True)
            a.fortschritt.set_fraction(min(1.0, float(st.get("t", 0)) / float(st["dauer"])))

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
                a.fortschritt.set_fraction(1)
                a.ergebnis.set_label(_("✓ Your face is recorded. Now try out whether Winky "
                                       "recognizes you."))
                self.melde(_("Face recorded"))
            else:
                a.vorschau.hinweis(_("Not saved"))
                a.ergebnis.set_label(lauf.fehlermeldung(rc))
        elif lauf.art == "testen":
            if erg.get("status") == "treffer":
                a.vorschau.hinweis(_("✓ Recognized"))
                a.ergebnis.set_label(_("✓ Recognized after {seconds} seconds.").format(
                    seconds=komma(erg.get("dauer_ms", 0) / 1000, 1)))
            else:
                a.vorschau.hinweis(_("Not recognized"))
                a.ergebnis.set_label(
                    _("Winky didn’t recognize you this time. Look straight at the camera and "
                      "try again. If it often doesn’t work, record your face again.")
                    if erg.get("status") in ("kein_treffer", "kein_gesicht")
                    else lauf.fehlermeldung(rc))
        elif lauf.art == "geste-testen":
            if erg.get("ok"):
                a.vorschau.hinweis(_("✓ Recognized"))
                a.ergebnis.set_label(_("✓ Face and ✌ recognized. You can now use them to "
                                       "confirm sudo."))
                self.melde(_("Face and ✌ recognized"))
            else:
                a.vorschau.hinweis(_("Not recognized"))
                a.ergebnis.set_label(lauf.fehlermeldung(rc))
        else:  # gegenprobe
            wert = erg.get("wert")
            if erg.get("ok"):
                a.vorschau.hinweis(_("✓ Passed"))
                a.ergebnis.set_label(_("✓ Passed: Winky didn’t recognize the other person."))
            elif erg.get("wie_eigen"):
                a.vorschau.hinweis(_("Was that you?"))
                a.ergebnis.set_label(lauf.fehlermeldung(rc))
            elif wert is not None and wert >= 0 and erg.get("status") != "kein_gesicht":
                a.vorschau.hinweis(_("Too similar"))
                a.ergebnis.set_label(
                    _("To Winky, this person looks too much like you. Make Winky stricter so "
                      "that only you can unlock the screen.") if strenger_moeglich(system.lese_zustand())
                    else _("To Winky, this person looks too much like you, and stricter settings "
                           "would lock you out as well. Better use only your password."))
            else:
                a.vorschau.hinweis(_("Not checked"))
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
                       "Use at your own risk."),
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
                 "computer, only right after your face was recognized at the login screen.")
        if system.secure_boot() is not True:
            text += "\n\n" + _("Secure Boot is off. Then the TPM chip protects your password "
                               "only weakly: someone who has this computer may be able to "
                               "read it. Do not use this password anywhere else.")
        dialog = Adw.AlertDialog.new(_("Unlock the keyring with your face?"), text)
        self.e_passwort = Adw.PasswordEntryRow(title=_("Your login password"))
        liste = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        liste.add_css_class("boxed-list")
        liste.append(self.e_passwort)
        dialog.set_extra_child(liste)
        dialog.add_response("abbrechen", _("Cancel"))
        dialog.add_response("ok", _("Seal"))
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
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
        self.schluessel_dialog = dialog

    def schluesselbund_versiegeln(self, passwort):
        self._verwalten(["schluesselbund", "an"],
                        _("After the next restart, your face also opens the keyring"),
                        eingabe=passwort.encode() + b"\n")

    def _anmeldung_umgeschaltet(self, zeile, _pspec):
        # GTK meldet ein Umschalten manchmal doppelt: nur auf echte Änderungen reagieren
        if self._schalter_sperre or zeile.get_active() == self.zustand.anmeldung:
            return
        if zeile.get_active():
            self._verwalten(["anmeldung", "an"],
                            _("Your face now also logs you in after a restart"), admin=True)
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
            symbol, titel, inhalt = ("dialog-warning-symbolic", _("Winky is missing something"),
                                     _("Without this part, Winky can’t check anything. Until "
                                       "then, your password works everywhere."))
        elif z.pausiert:
            symbol, titel, inhalt = ("media-playback-pause-symbolic", _("Winky is paused"),
                                     _("Right now, only your password works everywhere."))
        elif fertig_eingerichtet:
            symbol, titel, inhalt = ("emblem-ok-symbolic", _("Winky is on"),
                                     _("Lock the screen with Super+L. To unlock, press a key and "
                                       "look at the camera."))
        elif z.aktiv and not z.eingelernt:
            symbol, titel, inhalt = (APP_ID, _("Not set up for you yet"),
                                     _("Winky is on for this computer. Record your face so you "
                                       "can use it too."))
        elif z.eingelernt:
            symbol, titel, inhalt = (APP_ID, _("Almost done"),
                                     _("Your face is recorded. Finish the setup to turn on "
                                       "Winky."))
        else:
            symbol, titel, inhalt = (APP_ID, _("Welcome to Winky"),
                                     _("Unlock the lock screen with a glance at the camera. "
                                       "Setup takes about two minutes."))
        self.s_symbol.set_from_icon_name(symbol)
        if symbol == "emblem-ok-symbolic":
            self.s_symbol.add_css_class("success")
        else:
            self.s_symbol.remove_css_class("success")
        self.s_titel.set_label(titel)
        self.s_text.set_label(inhalt)
        self.s_einrichten.set_visible(bereit and not fertig_eingerichtet and not z.pausiert)
        self.s_einrichten.set_label(_("Continue setup") if z.eingelernt or z.kamera
                                    else _("Start setup"))
        self.s_einrichten.set_sensitive(not laeuft)

        # Schalter
        darf, grund = self._darf_aktivieren()
        info = system.keepassxc_info() if bereit else {"polkit_aktion": False, "gefunden": None}
        self.g_schalter.set_visible(bereit and (z.aktiv or z.pausiert or s["testen"]))
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
            _("Your login password is stored sealed in the TPM chip. Caution: weaker without "
              "Secure Boot."))
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
        self.r_dialoge.set_active(z.dialoge)
        self.r_dialoge.set_sensitive(((z.aktiv and s["geste"]) or z.dialoge) and not laeuft)
        self.r_dialoge.set_subtitle(
            _("Approve password dialogs such as updates with face and ✌; the dialog shows what")
            if z.dialoge or (z.aktiv and s["geste"]) else
            _("Turn on the lock screen first") if not z.aktiv else _("Test face and ✌ first"))
        self._schalter_sperre = False

        # Ausprobieren und pflegen
        self.g_pflege.set_visible(bereit and z.eingelernt)
        for r in (self.r_probe, self.r_neu, self.r_zweite, self.r_geste):
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
        self.g_verlauf.set_visible(sichtbar)
        for r in self._verlauf_zeilen:
            self.g_verlauf.remove(r)
        self._verlauf_zeilen = []
        if not sichtbar:
            return
        eintraege = system.verlauf(5)
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
                if e.get("zweck") == "sudo":
                    if e.get("befehl"):
                        titel = (_("sudo confirmed: {command}") if ok
                                 else _("sudo not confirmed: {command}")).format(
                                     command=e["befehl"])
                    else:
                        titel = _("sudo confirmed") if ok else _("sudo not confirmed")
                elif e.get("zweck") == "keepassxc":
                    titel = _("KeePassXC opened") if ok else _("KeePassXC: password needed")
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
           "✌.")),
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
        (_("Pause on the start page"),
         _("Turns everything off right away, without deleting anything.")),
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
