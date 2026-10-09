#!/usr/bin/env python3
"""Winky: Einrichtung und Verwaltung der Gesichtsentsperrung.

Gedacht für Menschen ohne Technikwissen. Ein Assistent führt Schritt für Schritt durch die
Einrichtung, danach zeigt die Startseite nur noch Schalter und „Ausprobieren“. Zahlen und
Technik (Kamerapfad, Schwelle, Version) stehen unter „Erweitert“.

Seiten (Adw.NavigationView):
  start         Zustand in einem Satz, Schalter, Ausprobieren, letzte Ereignisse
  einrichtung   Assistent: Willkommen, Kamera, Aufnehmen, Ausprobieren, zweite Person
                (freiwillig), Einschalten, sudo mit ✌ (freiwillig), Fertig
  kamera        ein Kameraablauf, von der Startseite aus geöffnet
  sicherheit    was Winky kann und was nicht, Risiken, Notausschalter
  erweitert     Kamera, Strenge (Schwelle), Daten löschen, Version, Deinstallieren

Das eigene Gesicht verwaltet jeder Benutzer mit seinem eigenen Passwort. Systemweite
Einstellungen (Kamera, Strenge, Ein/Aus, Pause) brauchen ein Administratorpasswort.
Die App selbst läuft ohne besondere Rechte.
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
from vorschau import Vorschau, css_laden, komma  # noqa: E402

GEGENPROBE_ABSTAND = 0.10   # so weit muss eine andere Person unter der Schwelle bleiben
SCHWELLE_MAX = 0.95
HINWEIS = "/usr/libexec/winky/winky-hinweis"
APP_ID = "io.github.dieschatten.Winky"

# Was während einer Aufnahme unter dem Bild steht (aus dem Feld "grund" des Prüfdienstes)
TIPPS = {
    "ok": "Gut so",
    "kein_gesicht": "Kein Gesicht zu sehen. Schau in die Kamera.",
    "zu_klein": "Etwas näher an die Kamera",
    "gedreht": "Kopf etwas weniger zur Seite drehen",
    "geneigt": "Kopf etwas gerader halten",
    "unsicher": "Schau direkt in die Kamera",
    "punkte_unsicher": "Das Gesicht ist teilweise verdeckt",
    "ueberbelichtet": "Etwas weiter weg von der Kamera",
    "keine_punkte": "Das Gesicht ist nicht ganz zu sehen",
}

ABLAEUFE = {
    "einlernen": {
        "titel": "Gesicht aufnehmen",
        "schritte": ["Setz dich so hin wie immer am Rechner und schau in die Kamera.",
                     "Klick auf „Aufnahme starten“ und gib dein Passwort ein.",
                     "Dreh den Kopf langsam ein wenig nach links, rechts, oben und unten."],
        "hinweis": "Die Aufnahme dauert 25 Sekunden. Winky speichert keine Fotos, nur Zahlen, "
                   "die nur das System lesen kann.",
        "knopf": "Aufnahme starten", "nochmal": "Neu aufnehmen",
    },
    "testen": {
        "titel": "Ausprobieren",
        "schritte": ["Klick auf „Ausprobieren“ und gib dein Passwort ein.",
                     "Schau einfach in die Kamera."],
        "hinweis": "So schnell öffnet sich später auch die Bildschirmsperre.",
        "knopf": "Ausprobieren", "nochmal": "Noch einmal ausprobieren",
    },
    "gegenprobe": {
        "titel": "Mit einer zweiten Person prüfen",
        "schritte": ["Hol jemanden dazu, am besten jemanden, der dir ähnlich sieht, zum "
                     "Beispiel aus der Familie.",
                     "Klick auf „Prüfung starten“ und gib dein Passwort ein.",
                     "Geh dann innerhalb von 5 Sekunden aus dem Bild. Die andere Person schaut "
                     "10 Sekunden in die Kamera."],
        "hinweis": "Winky darf diese Person nicht erkennen. Gespeichert wird kein Bild, nur wie "
                   "ähnlich sie dir für Winky ist. Freiwillig, aber empfohlen.",
        "knopf": "Prüfung starten", "nochmal": "Noch einmal prüfen",
    },
    "geste-testen": {
        "titel": "Gesicht und ✌ testen",
        "schritte": ["Klick auf „Test starten“ und gib dein Passwort ein.",
                     "Schau in die Kamera und zeig neben deinem Gesicht das V-Zeichen: Zeige- und "
                     "Mittelfinger hoch, Handfläche zur Kamera.",
                     "Halte es, bis „✓“ erscheint."],
        "hinweis": "Jede Person, die sudo so bestätigen will, macht diesen Test für sich.",
        "knopf": "Test starten", "nochmal": "Noch einmal testen",
    },
}

# Assistent: Reihenfolge der Schritte; gezählt werden die zwischen Willkommen und Fertig
SCHRITTE = ["willkommen", "kamera", "einlernen", "testen", "gegenprobe", "einschalten", "sudo",
            "fertig"]
GEZAEHLT = SCHRITTE[1:-1]


def datum(ts):
    if not ts:
        return "unbekannt"
    t = time.localtime(ts)
    heute = time.localtime()
    if t[:3] == heute[:3]:
        return time.strftime("heute %H:%M", t)
    if t[:3] == time.localtime(time.time() - 86400)[:3]:
        return time.strftime("gestern %H:%M", t)
    return time.strftime("%d.%m.%Y %H:%M", t)


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
    if z.gegenprobe_wert is None or not z.eingelernt:
        gegenprobe = None
    else:
        gegenprobe = z.gegenprobe_wert < z.schwelle - GEGENPROBE_ABSTAND
    geste = z.eingelernt and z.geste_ok > 0 and z.geste_ok >= z.eingelernt_am
    return {"kamera": bool(z.kamera), "einlernen": z.eingelernt, "testen": test,
            "gegenprobe": gegenprobe, "geste": geste}


def strengere_schwelle(wert):
    """Schwelle, bei der eine Person mit diesem Wert genug Abstand hat."""
    return math.ceil((wert + GEGENPROBE_ABSTAND + 0.02) * 100) / 100


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
        # Bild etwas kleiner als die Kamera (640 x 360), damit Knopf und Ergebnis ohne
        # Blättern zu sehen sind
        self.vorschau = Vorschau(512, 288)
        self.vorschau.set_halign(Gtk.Align.CENTER)
        self.append(self.vorschau)
        self.live = text("", "title-4", mitte=True)
        self.append(self.live)
        self.fortschritt = Gtk.ProgressBar(visible=False)
        self.append(self.fortschritt)
        knoepfe = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        self.k_start = knopf("", self.starten, "pill", "suggested-action")
        self.k_abbruch = knopf("Abbrechen", self.abbrechen, "pill")
        knoepfe.append(self.k_start)
        knoepfe.append(self.k_abbruch)
        self.append(knoepfe)
        self.ergebnis = text("", "title-3", mitte=True)
        self.ergebnis.set_selectable(True)
        self.append(self.ergebnis)
        # Nur bei der zweiten Person: Winky strenger stellen, wenn sie zu ähnlich war
        self.k_strenger = knopf("Winky strenger einstellen", fenster.strenger_einstellen,
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
        self.fenster.lauf_starten(self)

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
        self.k_strenger.set_visible(self.art == "gegenprobe" and s["gegenprobe"] is False)
        self.k_strenger.set_sensitive(not laeuft)
        if not meiner and not self.live.get_label():
            if not bereit:
                self.live.set_label("Winky ist nicht vollständig installiert.")
            elif not z.kamera:
                self.live.set_label("Zuerst die Kamera einrichten.")
            elif self.art != "einlernen" and not z.eingelernt:
                self.live.set_label("Zuerst dein Gesicht aufnehmen.")


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

    # ------------------------------------------------------------ Startseite

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
        self.s_einrichten = knopf("Einrichtung starten", self.einrichtung_oeffnen, "pill",
                                  "suggested-action")
        self.s_einrichten.set_halign(Gtk.Align.CENTER)
        self.s_einrichten.set_margin_top(8)
        box.append(self.s_einrichten)
        kopf.add(box)
        s.add(kopf)

        self.g_schalter = Adw.PreferencesGroup(
            title="Was Winky für dich öffnet",
            description="Zum Ändern fragt dein Computer nach dem Administrator-Passwort.")
        self.r_aktiv = Adw.SwitchRow(title="Bildschirmsperre",
                                     subtitle="mit einem Blick in die Kamera öffnen")
        self.r_aktiv.add_prefix(Gtk.Image(icon_name="system-lock-screen-symbolic"))
        self.r_aktiv.connect("notify::active", self._aktiv_umgeschaltet)
        self.g_schalter.add(self.r_aktiv)
        # Kein SwitchRow: Der Knopf „Einrichten“ muss bedienbar sein, solange der Schalter
        # noch gesperrt ist
        self.r_sudo = Adw.ActionRow(title="sudo im Terminal")
        self.r_sudo.add_prefix(Gtk.Image(icon_name="utilities-terminal-symbolic"))
        self.k_sudo_einrichten = knopf("Einrichten", lambda: self.kamera_oeffnen("geste-testen"))
        self.r_sudo.add_suffix(self.k_sudo_einrichten)
        self.s_sudo = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.s_sudo.connect("notify::active", self._sudo_umgeschaltet)
        self.r_sudo.add_suffix(self.s_sudo)
        self.r_sudo.set_activatable_widget(self.s_sudo)
        self.g_schalter.add(self.r_sudo)
        self.r_keepassxc = Adw.SwitchRow(title="KeePassXC")
        self.r_keepassxc.add_prefix(Gtk.Image(icon_name="dialog-password-symbolic"))
        self.r_keepassxc.connect("notify::active", self._keepassxc_umgeschaltet)
        self.g_schalter.add(self.r_keepassxc)
        self.r_keepassxc_geste = Adw.SwitchRow(
            title="KeePassXC nur mit ✌",
            subtitle="Empfohlen: Ohne dein Handzeichen öffnet niemand die Datenbank, auch "
                     "nicht, während du vor dem Rechner sitzt")
        self.r_keepassxc_geste.add_prefix(Gtk.Image(icon_name="security-high-symbolic"))
        self.r_keepassxc_geste.connect("notify::active", self._keepassxc_geste_umgeschaltet)
        self.g_schalter.add(self.r_keepassxc_geste)
        # Deutlich sichtbar, solange kein passendes KeePassXC da ist
        self.r_keepassxc_version = Adw.ActionRow(title="<b>Funktioniert erst ab KeePassXC 2.8</b>")
        self.r_keepassxc_version.set_subtitle_selectable(True)
        warnung = Gtk.Image(icon_name="dialog-warning-symbolic")
        warnung.add_css_class("warning")
        self.r_keepassxc_version.add_prefix(warnung)
        self.g_schalter.add(self.r_keepassxc_version)
        self.r_pause = Adw.SwitchRow(title="Pause",
                                     subtitle="Winky ruht, überall gilt nur dein Passwort")
        self.r_pause.add_prefix(Gtk.Image(icon_name="media-playback-pause-symbolic"))
        self.r_pause.connect("notify::active", self._pause_umgeschaltet)
        self.g_schalter.add(self.r_pause)
        s.add(self.g_schalter)

        self.g_pflege = Adw.PreferencesGroup(title="Ausprobieren und pflegen")
        self.r_probe = weiterzeile("Erkennung ausprobieren", "Schau in die Kamera und sieh, ob "
                                   "Winky dich erkennt", lambda: self.kamera_oeffnen("testen"),
                                   "camera-web-symbolic")
        self.r_neu = weiterzeile("Gesicht neu aufnehmen", "Hilft, wenn Winky dich schlecht "
                                 "erkennt, zum Beispiel mit neuer Brille",
                                 lambda: self.kamera_oeffnen("einlernen"), "view-refresh-symbolic")
        self.r_zweite = weiterzeile("Mit einer zweiten Person prüfen", "",
                                    lambda: self.kamera_oeffnen("gegenprobe"),
                                    "system-users-symbolic")
        self.r_geste = weiterzeile("Gesicht und ✌ testen", "",
                                   lambda: self.kamera_oeffnen("geste-testen"),
                                   "utilities-terminal-symbolic")
        for r in (self.r_probe, self.r_neu, self.r_zweite, self.r_geste):
            self.g_pflege.add(r)
        s.add(self.g_pflege)

        self.g_verlauf = Adw.PreferencesGroup(title="Zuletzt")
        self._verlauf_zeilen = []
        s.add(self.g_verlauf)

        mehr = Adw.PreferencesGroup()
        mehr.add(weiterzeile("Sicherheit und Hilfe", "Was Winky kann und was nicht, Notausschalter",
                             lambda: self.nav.push_by_tag("sicherheit"), "security-high-symbolic"))
        mehr.add(weiterzeile("Erweitert", "Kamera, Strenge, Daten löschen, Deinstallieren",
                             lambda: self.nav.push_by_tag("erweitert"),
                             "preferences-system-symbolic"))
        s.add(mehr)

        self.banner = Adw.Banner(title="Ein Teil von Winky läuft nicht. Installier Winky in der "
                                       "Software-Verwaltung neu.")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.banner)
        box.append(s)
        s.set_vexpand(True)
        return seite("Winky", "start", box)

    # ------------------------------------------------------------ Assistent

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
                ("dialog-password-symbolic", "Dein Passwort funktioniert weiterhin, immer."),
                ("camera-photo-symbolic", "Winky speichert keine Fotos von dir."),
                ("preferences-system-time-symbolic", "Die Einrichtung dauert etwa zwei Minuten."),
                ("system-shutdown-symbolic", "Nach dem Einschalten des Rechners brauchst du "
                                             "weiterhin dein Passwort.")):
            liste.append(textzeile(zeile, symbol=symbol))
        schritt("willkommen", "Willkommen bei Winky",
                "Mit Winky öffnest du die Bildschirmsperre mit einem Blick in die Kamera, "
                "ähnlich wie Windows Hello.", liste, symbol=APP_ID)

        self.w_kamera_knopf = knopf("Kamera suchen", self._kamera_suchen, "pill",
                                    "suggested-action")
        self.w_kamera_knopf.set_halign(Gtk.Align.CENTER)
        self.w_kamera_status = text("", "title-4", mitte=True)
        schritt("kamera", "Kamera finden",
                "Winky braucht die Infrarot-Kamera deines Rechners. Das ist die Kamera, mit der "
                "sich Windows per Gesicht entsperren lässt (Windows Hello). Bei der Suche fragt "
                "dein Computer nach dem Administrator-Passwort.",
                self.w_kamera_knopf, self.w_kamera_status,
                text("Keine gefunden? Nicht jeder Rechner hat eine Infrarot-Kamera. Eine normale "
                     "Webcam reicht nicht, weil sie sich schon mit einem Foto täuschen ließe.",
                     "dim-label"))

        for sid, art in (("einlernen", "einlernen"), ("testen", "testen"),
                         ("gegenprobe", "gegenprobe")):
            a = KameraAblauf(self, art, mit_titel=False)
            self.w_ablauf[sid] = a
            self.ablaeufe.append(a)
            titel = ABLAEUFE[art]["titel"] + (" (freiwillig)" if sid == "gegenprobe" else "")
            schritt(sid, titel, "", a)

        self.w_einschalten = knopf("Gesichtsentsperrung einschalten",
                                   lambda: self._aktiv_setzen(True), "pill", "suggested-action")
        self.w_einschalten.set_halign(Gtk.Align.CENTER)
        self.w_einschalten_status = text("", "title-4", mitte=True)
        so = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        so.add_css_class("boxed-list")
        for nr, zeile in (("1", "Bildschirm sperren: Super+L (Windows-Taste und L)"),
                          ("2", "Zum Öffnen eine Taste drücken oder die Maus bewegen"),
                          ("3", "In die Kamera schauen, fertig"),
                          ("", "Klappt es nicht, erscheint wie immer das Passwortfeld.")):
            r = textzeile(zeile)
            if nr:
                r.add_prefix(text(nr, "title-4"))
            so.append(r)
        schritt("einschalten", "Einschalten",
                "Alles bereit. Schalte ein, dass dein Gesicht die Bildschirmsperre öffnet. Dein "
                "Computer fragt dafür nach dem Administrator-Passwort.",
                self.w_einschalten, self.w_einschalten_status, text("So geht es ab jetzt",
                                                                    "heading"), so)

        a = KameraAblauf(self, "geste-testen", mit_titel=False)
        self.w_ablauf["sudo"] = a
        self.ablaeufe.append(a)
        sudo_liste = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        sudo_liste.add_css_class("boxed-list")
        self.w_sudo = Adw.SwitchRow(title="sudo mit Gesicht und ✌ bestätigen",
                                    subtitle="Administrator-Passwort zum Ändern")
        self.w_sudo.connect("notify::active", self._sudo_umgeschaltet)
        sudo_liste.append(self.w_sudo)
        a.zusatz.append(sudo_liste)
        schritt("sudo", "Für das Terminal (freiwillig)",
                "Arbeitest du im Terminal mit sudo? Dann kannst du Befehle mit Gesicht und dem "
                "Handzeichen ✌ bestätigen, statt das Passwort zu tippen. Nutzt du kein Terminal, "
                "überspring diesen Schritt einfach.", a)

        schritt("fertig", "Fertig!",
                "Winky ist eingerichtet. Probier es gleich aus: Drück Super+L, dann eine Taste, "
                "und schau in die Kamera. Unter „Sicherheit und Hilfe“ auf der Startseite steht, "
                "worauf du achten solltest.", symbol="emblem-ok-symbolic")

        unten = Gtk.Box(spacing=12, margin_top=10, margin_bottom=10, margin_start=18,
                        margin_end=18)
        self.w_zurueck = knopf("Zurück", lambda: self._schritt_wechseln(-1), "pill")
        self.w_zaehler = text("", "dim-label", mitte=True)
        self.w_zaehler.set_hexpand(True)
        self.w_weiter = knopf("Weiter", lambda: self._schritt_wechseln(1), "pill",
                              "suggested-action")
        unten.append(self.w_zurueck)
        unten.append(self.w_zaehler)
        unten.append(self.w_weiter)
        self.w_stapel.connect("notify::visible-child-name", lambda *_: self._assistent_anzeigen())
        return seite("Einrichtung", "einrichtung", self.w_stapel, unten)

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
        self.w_zaehler.set_label(f"Schritt {GEZAEHLT.index(sid) + 1} von {len(GEZAEHLT)}"
                                 if sid in GEZAEHLT else "")
        self.w_zurueck.set_visible(sid != "willkommen")
        weiter, darf = "Weiter", True
        if sid == "willkommen":
            weiter = "Los geht’s"
        elif sid in ("kamera", "einlernen", "testen"):
            darf = s[sid]
        elif sid == "gegenprobe":
            weiter = "Weiter" if s["gegenprobe"] is not None else "Überspringen"
        elif sid == "einschalten":
            darf = z.aktiv
        elif sid == "sudo":
            weiter = "Weiter" if z.sudo else "Überspringen"
        elif sid == "fertig":
            weiter = "Zur Startseite"
        self.w_weiter.set_label(weiter)
        self.w_weiter.set_sensitive(darf and not laeuft)
        self.w_zurueck.set_sensitive(not laeuft)

    # ------------------------------------------------------------ Kamera, Sicherheit, Erweitert

    def _baue_kamera(self):
        self.k_ansicht = KameraAblauf(self, "testen")
        self.ablaeufe.append(self.k_ansicht)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=24, margin_bottom=24,
                      margin_start=18, margin_end=18)
        box.append(self.k_ansicht)
        self.k_seite = seite("Kamera", "kamera", rollbar(box))
        return self.k_seite

    def kamera_oeffnen(self, art):
        if self.beschaeftigt():
            self.melde("Bitte warten, gerade läuft noch etwas")
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
        return seite("Sicherheit und Hilfe", "sicherheit", s)

    def _baue_erweitert(self):
        s = Adw.PreferencesPage()
        kamera = Adw.PreferencesGroup(title="Kamera")
        self.r_kamera = Adw.ActionRow(title="Infrarot-Kamera")
        self.r_kamera.set_subtitle_selectable(True)
        self.k_kamera_suchen = knopf("Neu suchen", self._kamera_suchen)
        self.r_kamera.add_suffix(self.k_kamera_suchen)
        kamera.add(self.r_kamera)
        self.r_kamera_wahl = Adw.ActionRow(title="Andere Kamera wählen",
                                           subtitle="Falls mehrere Infrarot-Kameras da sind")
        self.k_kamera_wahl = knopf("Auswählen …", self._kamera_auswahl)
        self.r_kamera_wahl.add_suffix(self.k_kamera_wahl)
        kamera.add(self.r_kamera_wahl)
        s.add(kamera)

        strenge = Adw.PreferencesGroup(
            title="Strenge",
            description="Wie ähnlich ein Gesicht deinem sein muss (Schwelle). Höher ist sicherer, "
                        "aber Winky erkennt dich dann vielleicht seltener. Vorgabe 0,65; dein "
                        "eigenes Gesicht liegt meist deutlich darüber. Ob andere Gesichter weit "
                        "genug darunter bleiben, zeigt die Prüfung mit einer zweiten Person. "
                        "Nach jeder Änderung einmal ausprobieren.")
        self.r_spin = Adw.SpinRow.new_with_range(0.50, SCHWELLE_MAX, 0.01)
        self.r_spin.set_title("Schwelle")
        self.r_spin.set_digits(2)
        strenge.add(self.r_spin)
        self.r_speichern = Adw.ActionRow(title="Eingestellten Wert übernehmen")
        self.k_speichern = knopf("Speichern", lambda: self._verwalten(
            ["schwelle", f"{self.r_spin.get_value():.2f}"], "Strenge gespeichert", admin=True))
        self.r_speichern.add_suffix(self.k_speichern)
        strenge.add(self.r_speichern)
        self.r_messwerte = textzeile("Deine Messwerte")
        strenge.add(self.r_messwerte)
        s.add(strenge)

        kp = Adw.PreferencesGroup(
            title="KeePassXC",
            description="Nur ab KeePassXC 2.8 als normales Paket. Ältere Versionen haben unter "
                        "Linux kein Schnellentsperren, und die Flatpak-Version kann es nicht am "
                        "System anmelden. Dort fragt KeePassXC weiter nach dem Master-Passwort.")
        self.r_keepassxc_info = Adw.ActionRow(title="KeePassXC auf diesem Rechner")
        self.r_keepassxc_info.set_subtitle_selectable(True)
        self.r_keepassxc_symbol = Gtk.Image()
        self.r_keepassxc_info.add_prefix(self.r_keepassxc_symbol)
        kp.add(self.r_keepassxc_info)
        s.add(kp)

        daten = Adw.PreferencesGroup(title="Deine Daten")
        self.r_vorlagen = Adw.ActionRow(title="Deine Gesichtsdaten")
        self.k_daten_weg = knopf("Löschen …", self._vorlagen_loeschen_fragen)
        self.r_vorlagen.add_suffix(self.k_daten_weg)
        daten.add(self.r_vorlagen)
        s.add(daten)

        info = Adw.PreferencesGroup(title="Über Winky")
        self.r_version = textzeile("Version")
        self.r_dienst = textzeile("Prüfdienst")
        info.add(self.r_version)
        info.add(self.r_dienst)
        info.add(textzeile("Lizenz", "MIT. Modelle: YuNet (MIT), SFace und MediaPipe (Apache-2.0)"))
        s.add(info)

        rueckbau = Adw.PreferencesGroup(title="Entfernen")
        r = textzeile("Deinstallieren", "In der Software-Verwaltung unter „Installiert“. Danach "
                      "gilt überall wieder nur das Passwort, und die Gesichtsdaten aller "
                      "Benutzer werden gelöscht.", "user-trash-symbolic")
        self.k_store = None
        if Gio.AppInfo.get_default_for_uri_scheme("appstream"):
            self.k_store = knopf("Öffnen", self._store_oeffnen)
            r.add_suffix(self.k_store)
        rueckbau.add(r)
        rueckbau.add(textzeile("Ohne Software-Verwaltung", "Im Terminal:\nsudo apt purge winky"))
        s.add(rueckbau)
        return seite("Erweitert", "erweitert", s)

    # ------------------------------------------------------------ Kameraabläufe

    def lauf_starten(self, ansicht):
        if self.beschaeftigt():
            self.melde("Bitte warten, gerade läuft noch etwas")
            return
        ansicht.zuruecksetzen()
        ansicht.live.set_label("Passwortabfrage und Kamerastart …")
        ansicht.vorschau.hinweis("Kamera startet …", bis_bild=True)
        ansicht.fortschritt.set_fraction(0)
        try:
            self.gesicht_lauf = Prozess(umgebung.verwalten_befehl([ansicht.art]), self._g_bild,
                                        self._g_status, self._g_ende, abbruch_ueber_eingabe=True)
        except OSError as e:
            self.melde(f"Start fehlgeschlagen: {e}")
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
            a.vorschau.hinweis(f"Bitte aus dem Bild gehen … {st.get('rest')}", bis_bild=True)
            a.live.set_label("Die andere Person setzt sich jetzt vor die Kamera.")
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
            gesicht = "Gesicht erkannt ✓" if st.get("gesicht_erkannt") else "Gesicht wird geprüft …"
            if not st.get("hand"):
                hand = "jetzt ✌ zeigen"
            elif st.get("zeichen"):
                hand = "✌ erkannt, kurz halten"
            else:
                hand = "Hand gesehen, aber noch kein ✌"
            return f"{gesicht} · {hand}", bool(st.get("gesicht_erkannt") and st.get("zeichen"))
        grund = st.get("grund")
        if art == "gegenprobe" and grund == "ok" and st.get("wert") is not None:
            if st["wert"] >= self.zustand.schwelle - GEGENPROBE_ABSTAND:
                return "Achtung: Diese Person ähnelt dir für Winky stark", False
            return "Gut: Winky erkennt diese Person nicht", True
        tipp = TIPPS.get(grund, grund or "")
        if art == "einlernen" and grund == "ok":
            tipp = "Gut so, Kopf langsam weiter bewegen"
        return tipp, grund == "ok"

    def _g_ende(self, lauf, rc):
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
            a.vorschau.hinweis("Abgebrochen")
            a.ergebnis.set_label("")
        elif lauf.art == "einlernen":
            if erg.get("ok"):
                a.vorschau.hinweis("✓ Aufgenommen")
                a.fortschritt.set_fraction(1)
                a.ergebnis.set_label("✓ Dein Gesicht ist aufgenommen. Probier jetzt aus, ob "
                                     "Winky dich erkennt.")
                self.melde("Gesicht aufgenommen")
            else:
                a.vorschau.hinweis("Nicht gespeichert")
                a.ergebnis.set_label(lauf.fehlermeldung(rc))
        elif lauf.art == "testen":
            if erg.get("status") == "treffer":
                a.vorschau.hinweis("✓ Erkannt")
                a.ergebnis.set_label(f"✓ Erkannt nach {komma(erg.get('dauer_ms', 0) / 1000, 1)} "
                                     "Sekunden.")
            else:
                a.vorschau.hinweis("Nicht erkannt")
                a.ergebnis.set_label(
                    "Winky hat dich diesmal nicht erkannt. Schau gerade in die Kamera und "
                    "versuch es noch einmal. Klappt es öfter nicht, nimm dein Gesicht neu auf."
                    if erg.get("status") in ("kein_treffer", "kein_gesicht")
                    else lauf.fehlermeldung(rc))
        elif lauf.art == "geste-testen":
            if erg.get("ok"):
                a.vorschau.hinweis("✓ Erkannt")
                a.ergebnis.set_label("✓ Gesicht und ✌ erkannt. Jetzt kannst du sudo damit "
                                     "bestätigen lassen.")
                self.melde("Gesicht und ✌ erkannt")
            else:
                a.vorschau.hinweis("Nicht erkannt")
                a.ergebnis.set_label(lauf.fehlermeldung(rc))
        else:  # gegenprobe
            wert = erg.get("wert")
            if erg.get("ok"):
                a.vorschau.hinweis("✓ Bestanden")
                a.ergebnis.set_label("✓ Bestanden: Winky hat die andere Person nicht erkannt.")
            elif wert is not None and wert >= 0 and erg.get("status") != "kein_gesicht":
                a.vorschau.hinweis("Zu ähnlich")
                a.ergebnis.set_label("Diese Person ähnelt dir für Winky zu sehr. Stell Winky "
                                     "strenger ein, damit nur du die Sperre öffnen kannst.")
            else:
                a.vorschau.hinweis("Nicht geprüft")
                a.ergebnis.set_label(lauf.fehlermeldung(rc))
        self.aktualisieren()

    def strenger_einstellen(self):
        z = self.zustand
        if z.gegenprobe_wert is None:
            return
        neu = strengere_schwelle(z.gegenprobe_wert)
        if neu > SCHWELLE_MAX:
            self.melde("Diese Person ähnelt dir zu sehr. Winky kann euch nicht sicher "
                       "unterscheiden, nutz besser nur das Passwort.")
            return
        self._verwalten(["schwelle", f"{neu:.2f}"],
                        f"Winky ist jetzt strenger ({komma(neu, 2)}). Probier aus, ob er dich "
                        "weiterhin erkennt.", admin=True)

    def _seite_weg(self, _nav, page):
        """Wer eine Seite mit laufender Kamera verlässt, bricht den Ablauf ab."""
        if self.gesicht_lauf and page.get_tag() in ("einrichtung", "kamera"):
            self.gesicht_lauf.abbrechen()

    # ------------------------------------------------------------ Verwaltung

    def _store_oeffnen(self):
        try:
            Gio.AppInfo.launch_default_for_uri(f"appstream://{APP_ID}", None)
        except GLib.Error:
            self.melde("Die Software-Verwaltung ließ sich nicht öffnen")

    def _verwalten(self, args, erfolg, admin=False, danach=None):
        if self.beschaeftigt():
            self.melde("Bitte warten, gerade läuft noch etwas")
            return

        def ende(lauf, rc):
            self.aktion = None
            erg = lauf.ergebnis or {}
            ok = rc == 0 and bool(erg.get("ok"))
            meldung = (erg.get("hinweis") or erfolg) if ok else lauf.fehlermeldung(rc)
            self.melde(meldung)
            self.aktualisieren()
            if danach:
                danach(ok, erg, meldung)

        try:
            self.aktion = Prozess(umgebung.verwalten_befehl(args, admin=admin), bei_ende=ende,
                                  abbruch_ueber_eingabe=True)
        except OSError as e:
            self.melde(f"Start fehlgeschlagen: {e}")
        self.aktualisieren()

    def _kamera_suchen(self):
        def danach(ok, erg, meldung):
            if ok:
                self.kamera_name = (erg.get("kamera") or {}).get("name")
            self.w_kamera_status.set_label("" if ok else meldung)
            self.aktualisieren()

        if self.beschaeftigt():
            self.melde("Bitte warten, gerade läuft noch etwas")
            return
        self.w_kamera_status.set_label("Suche läuft …")
        self._verwalten(["kamera", "auto"], "Kamera eingerichtet", admin=True, danach=danach)

    def _kamera_auswahl(self):
        def gefunden(ok, erg, _meldung):
            if not ok:
                return
            liste = [k for k in erg.get("kameras", []) if not k.get("fehler")]
            if not liste:
                self.melde("Keine Infrarot-Kamera gefunden")
                return
            dialog = Adw.AlertDialog.new("Kamera wählen", "Gefundene Kameras mit Infrarot-Bild:")
            auswahl = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
            auswahl.add_css_class("boxed-list")
            for k in liste:
                strahler = ("Licht blinkt" if k.get("blinkt") else
                            "Licht leuchtet" if k.get("hell", 0) >= 10 else "Bild dunkel")
                zeile = Adw.ActionRow(title=k.get("name", "?"),
                                      subtitle=f"{k['pfad']} · {k.get('breite')}×{k.get('hoehe')}"
                                               f" · {strahler}")
                zeile.pfad = k["pfad"]
                zeile.name = k.get("name")
                auswahl.append(zeile)
            auswahl.select_row(auswahl.get_row_at_index(0))
            dialog.set_extra_child(auswahl)
            dialog.add_response("abbrechen", "Abbrechen")
            dialog.add_response("ok", "Übernehmen")
            dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_close_response("abbrechen")

            def antwort(_d, r):
                zeile = auswahl.get_selected_row()
                if r == "ok" and zeile is not None:
                    self.kamera_name = zeile.name
                    GLib.idle_add(lambda: self._verwalten(["kamera", zeile.pfad],
                                                          "Kamera übernommen", admin=True) and False)

            dialog.connect("response", antwort)
            dialog.present(self)

        self._verwalten(["kameras"], "Kameras gesucht", danach=gefunden)

    def _vorlagen_loeschen_fragen(self):
        dialog = Adw.AlertDialog.new("Deine Gesichtsdaten löschen?",
                                     "Danach öffnet dein Gesicht nichts mehr, bis du es neu "
                                     "aufnimmst. Dein Passwort funktioniert weiter.")
        dialog.add_response("abbrechen", "Abbrechen")
        dialog.add_response("weg", "Löschen")
        dialog.set_response_appearance("weg", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("abbrechen")
        dialog.connect("response", lambda _d, r: r == "weg" and self._verwalten(
            ["entfernen"], "Gesichtsdaten gelöscht"))
        dialog.present(self)

    def _aktiv_setzen(self, an):
        if an:
            self._verwalten(["aktivieren"], "Eingeschaltet. Probier es mit Super+L.", admin=True)
        else:
            self._verwalten(["deaktivieren"], "Ausgeschaltet, es gilt wieder nur das Passwort",
                            admin=True)

    def _aktiv_umgeschaltet(self, zeile, _pspec):
        if not self._schalter_sperre:
            self._aktiv_setzen(zeile.get_active())

    def _keepassxc_umgeschaltet(self, zeile, _pspec):
        if self._schalter_sperre:
            return
        if zeile.get_active():
            self._verwalten(["keepassxc", "an"], "KeePassXC lässt sich jetzt per Gesicht öffnen",
                            admin=True)
        else:
            self._verwalten(["keepassxc", "aus"], "KeePassXC wieder nur mit Passwort", admin=True)

    def _keepassxc_geste_umgeschaltet(self, zeile, _pspec):
        if self._schalter_sperre:
            return
        if zeile.get_active():
            self._verwalten(["keepassxc", "geste-an"], "KeePassXC verlangt jetzt Gesicht und ✌",
                            admin=True)
        else:
            self._verwalten(["keepassxc", "geste-aus"], "KeePassXC öffnet jetzt mit dem Gesicht "
                            "allein", admin=True)

    def _sudo_umgeschaltet(self, zeile, _pspec):
        if self._schalter_sperre:
            return
        if zeile.get_active():
            self._verwalten(["sudo", "an"], "sudo lässt sich jetzt mit Gesicht und ✌ bestätigen",
                            admin=True, danach=lambda ok, _e, _m: ok and self._hinweis_starten())
        else:
            self._verwalten(["sudo", "aus"], "sudo wieder nur mit Passwort", admin=True)

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
        if self._schalter_sperre:
            return
        self._verwalten(["pausieren" if zeile.get_active() else "fortsetzen"],
                        "Pause: Es gilt überall nur das Passwort" if zeile.get_active()
                        else "Winky ist wieder da", admin=True)

    # ------------------------------------------------------------ Anzeige

    def _darf_aktivieren(self):
        z, s = self.zustand, stand(self.zustand)
        if not (z.installiert and z.dienst):
            return False, "Winky ist nicht vollständig installiert."
        if not z.kamera:
            return False, "Zuerst die Kamera einrichten."
        if not z.eingelernt:
            return False, "Zuerst dein Gesicht aufnehmen."
        if not s["testen"]:
            return False, "Zuerst einmal erfolgreich ausprobieren."
        if z.schwelle <= 0:
            return False, "Keine Strenge festgelegt (Erweitert)."
        if s["gegenprobe"] is False:
            return False, ("Die zweite Person war dir zu ähnlich. Stell Winky im Schritt davor "
                           "strenger ein.")
        return True, "Bereit zum Einschalten."

    def aktualisieren(self):
        self.zustand = z = system.lese_zustand()
        s = stand(z)
        laeuft = self.beschaeftigt()
        bereit = z.installiert and z.dienst
        fertig_eingerichtet = z.eingelernt and s["testen"] and z.aktiv

        self.banner.set_revealed(not bereit)
        if not bereit:
            symbol, titel, inhalt = ("dialog-warning-symbolic", "Winky fehlt etwas",
                                     "Ohne diesen Teil kann Winky nichts prüfen. Bis dahin gilt "
                                     "überall dein Passwort.")
        elif z.pausiert:
            symbol, titel, inhalt = ("media-playback-pause-symbolic", "Winky macht Pause",
                                     "Gerade gilt überall nur dein Passwort.")
        elif fertig_eingerichtet:
            symbol, titel, inhalt = ("emblem-ok-symbolic", "Winky ist an",
                                     "Sperre den Bildschirm mit Super+L. Zum Öffnen eine Taste "
                                     "drücken und in die Kamera schauen.")
        elif z.aktiv and not z.eingelernt:
            symbol, titel, inhalt = (APP_ID, "Noch nicht für dich eingerichtet",
                                     "Auf diesem Rechner ist Winky an. Nimm dein Gesicht auf, "
                                     "dann kannst du es auch nutzen.")
        elif z.eingelernt:
            symbol, titel, inhalt = (APP_ID, "Fast fertig",
                                     "Dein Gesicht ist aufgenommen. Führ die Einrichtung zu Ende, "
                                     "um Winky einzuschalten.")
        else:
            symbol, titel, inhalt = (APP_ID, "Willkommen bei Winky",
                                     "Öffne die Bildschirmsperre mit einem Blick in die Kamera. "
                                     "Die Einrichtung dauert etwa zwei Minuten.")
        self.s_symbol.set_from_icon_name(symbol)
        if symbol == "emblem-ok-symbolic":
            self.s_symbol.add_css_class("success")
        else:
            self.s_symbol.remove_css_class("success")
        self.s_titel.set_label(titel)
        self.s_text.set_label(inhalt)
        self.s_einrichten.set_visible(bereit and not fertig_eingerichtet and not z.pausiert)
        self.s_einrichten.set_label("Einrichtung fortsetzen" if z.eingelernt or z.kamera
                                    else "Einrichtung starten")
        self.s_einrichten.set_sensitive(not laeuft)

        # Schalter
        darf, grund = self._darf_aktivieren()
        info = system.keepassxc_info() if bereit else {"polkit_aktion": False, "gefunden": None}
        self.g_schalter.set_visible(bereit and (z.aktiv or z.pausiert or s["testen"]))
        self._schalter_sperre = True
        self.r_aktiv.set_active(z.aktiv)
        self.r_aktiv.set_sensitive((darf or z.aktiv) and not laeuft)
        self.r_aktiv.set_subtitle("mit einem Blick in die Kamera öffnen" if darf or z.aktiv
                                  else grund)
        self.s_sudo.set_active(z.sudo)
        self.s_sudo.set_sensitive(((z.aktiv and s["geste"]) or z.sudo) and not laeuft)
        self.k_sudo_einrichten.set_visible(not s["geste"] and not z.sudo)
        self.k_sudo_einrichten.set_sensitive(z.eingelernt and not laeuft)
        self.r_sudo.set_subtitle(
            "Befehle mit Gesicht und ✌ bestätigen" if z.sudo or (z.aktiv and s["geste"]) else
            "Zuerst die Bildschirmsperre einschalten" if not z.aktiv else
            "Erst einmal Gesicht und ✌ testen")
        self.w_sudo.set_active(z.sudo)
        self.w_sudo.set_sensitive(((z.aktiv and s["geste"]) or z.sudo) and not laeuft)
        self.w_sudo.set_subtitle("Administrator-Passwort zum Ändern" if z.aktiv and s["geste"]
                                 else "Zuerst den Test oben bestehen" if z.aktiv else
                                 "Zuerst die Bildschirmsperre einschalten")
        kp_geste_fehlt = z.keepassxc_geste and not s["geste"]
        kp_bereit = bereit and z.eingelernt and s["testen"] and not kp_geste_fehlt
        kp_sichtbar = z.keepassxc or bool(info.get("gefunden")) or bool(info.get("polkit_aktion"))
        self.r_keepassxc.set_visible(kp_sichtbar)
        self.r_keepassxc.set_active(z.keepassxc)
        self.r_keepassxc.set_sensitive((kp_bereit or z.keepassxc) and not laeuft)
        mit = "Gesicht und ✌" if z.keepassxc_geste else "dem Gesicht"
        self.r_keepassxc.set_subtitle(
            "Erst einmal Gesicht und ✌ testen" if kp_geste_fehlt and not z.keepassxc else
            f"Passwort-Datenbank mit {mit} öffnen" if info.get("polkit_aktion") else
            f"Passwort-Datenbank mit {mit} öffnen (braucht KeePassXC ab 2.8, siehe Erweitert)")
        self.r_keepassxc_geste.set_visible(kp_sichtbar)
        self.r_keepassxc_geste.set_active(z.keepassxc_geste)
        self.r_keepassxc_geste.set_sensitive(bereit and not laeuft)
        gefunden = info.get("gefunden")
        self.r_keepassxc_version.set_visible(kp_sichtbar and not info.get("polkit_aktion"))
        self.r_keepassxc_version.set_subtitle(
            ("Gefunden: " + gefunden + ". " if gefunden else "") +
            "Ältere Versionen und die Flatpak-Version können das nicht: Dort fragt KeePassXC wie "
            "gewohnt nach dem Master-Passwort, Winky wird gar nicht gefragt.")
        self.r_pause.set_active(z.pausiert)
        self.r_pause.set_sensitive(bereit and (z.aktiv or z.pausiert) and not laeuft)
        self._schalter_sperre = False

        # Ausprobieren und pflegen
        self.g_pflege.set_visible(bereit and z.eingelernt)
        for r in (self.r_probe, self.r_neu, self.r_zweite, self.r_geste):
            r.set_sensitive(not laeuft)
        self.r_zweite.set_subtitle({None: "Empfohlen: Prüft, dass Winky nur dich erkennt",
                                    True: "Bestanden, Winky erkennt nur dich",
                                    False: "Zu ähnlich. Hier strenger einstellen."}
                                   [s["gegenprobe"]])
        self.r_geste.set_subtitle(f"Bestanden ({datum(z.geste_ok)})" if s["geste"] else
                                  "Nötig, wenn du sudo mit ✌ bestätigen willst")

        self._verlauf_zeigen(bereit and z.eingelernt)

        # Assistent und Kameraabläufe
        if z.kamera:
            name = f": {self.kamera_name}" if self.kamera_name else ""
            self.w_kamera_status.set_label(f"✓ Kamera ist eingerichtet{name}")
        elif self.w_kamera_status.get_label().startswith("✓"):
            self.w_kamera_status.set_label("")
        self.w_kamera_knopf.set_label("Noch einmal suchen" if z.kamera else "Kamera suchen")
        self.w_kamera_knopf.set_sensitive(bereit and not laeuft)
        self.w_einschalten.set_visible(not z.aktiv)
        self.w_einschalten.set_sensitive(darf and not laeuft)
        self.w_einschalten_status.set_label(
            "✓ Eingeschaltet" if z.aktiv else "" if darf else grund)
        for a in self.ablaeufe:
            a.aktualisieren(z, s, bereit, laeuft)
        self._assistent_anzeigen()

        # Erweitert
        self.r_kamera.set_subtitle(z.kamera or "noch keine eingerichtet")
        self.k_kamera_suchen.set_sensitive(bereit and not laeuft)
        self.k_kamera_wahl.set_sensitive(bereit and not laeuft)
        if z.schwelle > 0 and not self.r_spin.has_focus():
            self.r_spin.set_value(z.schwelle)
        self.r_spin.set_sensitive(bereit and not laeuft)
        self.k_speichern.set_sensitive(bereit and not laeuft)
        self.r_speichern.set_subtitle(f"Gerade eingestellt: {komma(z.schwelle, 2)}"
                                      if z.schwelle > 0 else "Noch nicht festgelegt")
        werte = []
        if s["testen"]:
            werte.append(f"du beim letzten Ausprobieren {komma(z.test_wert, 2)}")
        if z.gegenprobe_wert is not None:
            werte.append(f"die zweite Person {komma(z.gegenprobe_wert, 2)}")
        self.r_messwerte.set_subtitle(("Ähnlichkeit: " + ", ".join(werte)) if werte else
                                      "Noch keine")
        self.r_vorlagen.set_subtitle(f"aufgenommen {datum(z.eingelernt_am)}, nur für das System "
                                     "lesbar, keine Fotos" if z.eingelernt else "keine")
        self.k_daten_weg.set_sensitive(z.eingelernt and not laeuft)
        if info.get("polkit_aktion"):
            self.r_keepassxc_symbol.set_from_icon_name("emblem-ok-symbolic")
            self.r_keepassxc_info.set_subtitle(
                "KeePassXC mit Schnellentsperren gefunden. In KeePassXC unter Einstellungen, "
                "Sicherheit das Schnellentsperren einschalten.")
        else:
            self.r_keepassxc_symbol.set_from_icon_name("dialog-information-symbolic")
            gefunden = info.get("gefunden")
            self.r_keepassxc_info.set_subtitle(
                ("Gefunden: " + gefunden + ". " if gefunden else "Kein KeePassXC gefunden. ") +
                "Nötig ist KeePassXC ab 2.8 als normales Paket, denn nur das meldet das "
                "Schnellentsperren am System an. Einschalten geht schon vorab.")
        v = umgebung.version()
        self.r_version.set_subtitle(f"{v.get('version')} · Stand {v.get('commit')} · gebaut "
                                    f"{v.get('gebaut')}")
        self.r_dienst.set_subtitle("bereit (startet bei Bedarf)" if z.dienst else "nicht aktiv")

    def _verlauf_zeigen(self, sichtbar):
        self.g_verlauf.set_visible(sichtbar)
        for r in self._verlauf_zeilen:
            self.g_verlauf.remove(r)
        self._verlauf_zeilen = []
        if not sichtbar:
            return
        eintraege = system.verlauf(5)
        if eintraege is None:
            zeilen = [textzeile("Verlauf nicht lesbar",
                                "Das Systemprotokoll ist für dein Konto nicht zugänglich.")]
        elif not eintraege:
            zeilen = [textzeile("Noch nichts passiert", "Sperre den Bildschirm mit Super+L.")]
        else:
            zeilen = []
            for e in eintraege:
                ok = e["status"] == "treffer"
                if e.get("zweck") == "sudo":
                    titel = ("sudo bestätigt" if ok else "sudo nicht bestätigt") + \
                        (f": {e['befehl']}" if e.get("befehl") else "")
                elif e.get("zweck") == "keepassxc":
                    titel = "KeePassXC geöffnet" if ok else "KeePassXC: Passwort nötig"
                else:
                    titel = system.STATUS_TEXTE.get(e["status"], e["status"])
                zeilen.append(textzeile(
                    titel, f"{datum(e['zeit'])}, nach {komma(e['dauer_ms'] / 1000, 1)} s",
                    "emblem-ok-symbolic" if ok else "dialog-information-symbolic"))
        for r in zeilen:
            self.g_verlauf.add(r)
            self._verlauf_zeilen.append(r)

    def _schliessen(self, *_):
        for lauf in (self.gesicht_lauf, self.aktion):
            if lauf:
                lauf.abbrechen()
        return False


# Seite „Sicherheit und Hilfe“: kurz und ohne Fachbegriffe. Die ausführliche Fassung steht in
# SICHERHEIT.md im Projekt.
SICHERHEIT = [
    ("Das kann Winky", None, "emblem-ok-symbolic", [
        ("Die Bildschirmsperre mit deinem Gesicht öffnen",
         "Nur die Sperre einer laufenden Sitzung. Nach dem Einschalten des Rechners brauchst du "
         "dein Passwort, damit auch dein Schlüsselbund aufgeht."),
        ("Wahlweise sudo mit Gesicht und ✌ bestätigen",
         "Nur im Terminal am Rechner selbst, nur mit beidem zusammen und nur, wenn du es "
         "einschaltest."),
        ("Wahlweise KeePassXC öffnen",
         "Nur ab KeePassXC 2.8 als normales Paket, nach dem ersten Öffnen mit dem "
         "Master-Passwort. Standardmäßig nur mit Gesicht und ✌."),
        ("Mehrere Personen am selben Rechner",
         "Jede Person nimmt ihr eigenes Gesicht mit ihrem eigenen Passwort auf."),
    ]),
    ("Das kann Winky nicht", None, "dialog-information-symbolic", [
        ("Das Passwort ersetzen",
         "Das Passwort funktioniert immer und ist nach dem Einschalten des Rechners, bei "
         "Fehlversuchen und bei der Pause der einzige Weg."),
        ("Zwillinge oder sehr ähnliche Geschwister sicher unterscheiden",
         "Das kann kein Gesichtssystem. Die Prüfung mit einer zweiten Person zeigt, ob es "
         "knapp wird."),
        ("Mit einer normalen Webcam arbeiten",
         "Winky braucht eine Infrarot-Kamera, wie sie für Windows Hello verbaut wird."),
        ("Erkennen, ob du einverstanden bist",
         "Jemand könnte den Rechner vor dein Gesicht halten. Für sudo gibt es deshalb das ✌."),
    ]),
    ("Darauf solltest du achten", None, "dialog-warning-symbolic", [
        ("Sperr den Bildschirm, wenn du weggehst",
         "Super+L. Winky schützt nur, was gesperrt ist."),
        ("Mach die Prüfung mit einer zweiten Person",
         "Am besten mit jemandem aus der Familie, der dir ähnlich sieht."),
        ("Kommt eine sudo-Meldung, die du nicht erwartest: kein ✌ zeigen",
         "Dann hat ein Programm ohne dich nach Administratorrechten gefragt. Einfach "
         "ignorieren, nach wenigen Sekunden ist die Anfrage vorbei."),
        ("Wer dir sehr ähnlich sieht, sollte Winky nicht nutzen dürfen",
         "Stell Winky dann strenger ein (Erweitert) oder lass es aus."),
    ]),
    ("Grenzen der Technik", None, "security-medium-symbolic", [
        ("Ein Foto auf einem Bildschirm oder Handy täuscht Winky nicht",
         "Bildschirme sind im Infrarot-Bild schwarz. Ein aufwendig gemachter Ausdruck oder eine "
         "Maske könnte es aber, wie bei Windows Hello ohne Zusatzschutz."),
        ("Winky schützt nicht gegen jemanden, der den Rechner mitnimmt",
         "Dafür braucht es eine verschlüsselte Festplatte. Winky ist ein Komfort für die "
         "Bildschirmsperre, kein Diebstahlschutz."),
        ("Ein Schadprogramm mit deinen Rechten kann eine sudo-Anfrage auslösen",
         "Ohne dein ✌ passiert aber nichts, und jede Anfrage erscheint als Meldung mit dem "
         "Befehl. Nach drei unbestätigten Anfragen gilt 10 Minuten nur das Passwort."),
    ]),
    ("Wenn etwas klemmt", None, "help-browser-symbolic", [
        ("Das Passwort geht immer",
         "Erkennt Winky dich nicht, erscheint nach spätestens drei Sekunden das Passwortfeld."),
        ("Pause auf der Startseite",
         "Schaltet sofort alles ab, ohne etwas zu löschen."),
        ("Notausschalter ohne diese App",
         "Strg+Alt+F3, mit Benutzername und Passwort anmelden, dann eingeben:\n"
         "sudo touch /etc/winky/disabled"),
        ("Deinstallieren",
         "In der Software-Verwaltung unter „Installiert“. Danach gilt überall wieder nur das "
         "Passwort."),
    ]),
    ("Hinweis", None, "dialog-information-symbolic", [
        ("Nutzung auf eigenes Risiko",
         "Winky ist ein Komfortmerkmal und ersetzt weder ein starkes Passwort noch eine "
         "verschlüsselte Festplatte."),
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
