#!/usr/bin/env python3
"""Ablauftest der App mit Attrappe (ohne Kamera, root und Systemänderung): Assistent komplett,
dann Startseite, Erweitert und Fehlerfälle.

Aufruf (braucht ein GTK-Display, z. B. Broadway):
  gtk4-broadwayd :9 &
  WINKY_ATTRAPPE=1 WINKY_TESTWURZEL=/tmp/w GDK_BACKEND=broadway BROADWAY_DISPLAY=:9 \\
    python3 werkzeuge/test/gui_logik_test.py
"""

import os
import sys
import time
import traceback
from pathlib import Path

assert os.environ.get("WINKY_ATTRAPPE") == "1", "nur mit Attrappe ausführen"
os.environ["LANGUAGE"] = "de"   # die Prüfungen vergleichen deutsche Texte (bau/locale)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "app"))

import gesicht_app  # noqa: E402
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

W = Path(os.environ["WINKY_TESTWURZEL"])
FEHLER = []
DIALOGE = []
Adw.AlertDialog.present = lambda self, parent: DIALOGE.append(self)
FACHBEGRIFFE = ("Schwelle", "Vorlage", "Prüfdienst", "PAM", "Polkit", "/dev/", "Ähnlichkeit")


def pruefe(bed, inhalt):
    print(("ok    " if bed else "FEHLER") + "  " + inhalt, flush=True)
    if not bed:
        FEHLER.append(inhalt)


def warte(bedingung, sekunden=30):
    ctx = GLib.MainContext.default()
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        if bedingung():
            return True
        ctx.iteration(False)
        time.sleep(0.01)
    return bedingung()


def fertig(f, sekunden=20):
    return warte(lambda: f.aktion is None and f.gesicht_lauf is None, sekunden)


def gegenprobe_starten(g):
    """Startknopf der zweiten Person: erst Rückfrage, dann bestätigen."""
    g.k_start.emit("clicked")
    pruefe(getattr(g, "bestaetigung", None) is not None, "zweite Person: erst Rückfrage, nie direkt")
    g.bestaetigung.emit("response", "los")
    g.bestaetigung.close()
    g.bestaetigung = None


def schritt(f):
    return f.w_stapel.get_visible_child_name()


def seite(f):
    return f.nav.get_visible_page().get_tag()


def weiter(f):
    f.w_weiter.emit("clicked")
    warte(lambda: False, 0.1)


def texte(widget):
    """Alle sichtbaren Texte unter einem Widget (für die Fachbegriff-Prüfung)."""
    gefunden = []

    def lauf(w):
        if not w.get_visible():
            return
        if isinstance(w, Gtk.Label):
            gefunden.append(w.get_label())
        if isinstance(w, Adw.PreferencesRow):
            gefunden.append(w.get_title())
        if isinstance(w, Adw.ActionRow):
            gefunden.append(w.get_subtitle() or "")
        kind = w.get_first_child()
        while kind is not None:
            lauf(kind)
            kind = kind.get_next_sibling()

    lauf(widget)
    return " ".join(t for t in gefunden if t)


def test(f):
    z = f.zustand
    # --- Erster Start: Assistent öffnet sich von selbst
    pruefe(z.installiert and z.dienst and not z.kamera, "Anfang: Dienst bereit, keine Kamera")
    pruefe(seite(f) == "einrichtung" and schritt(f) == "willkommen",
           "erster Start öffnet den Assistenten bei „Willkommen“")
    pruefe(f.w_weiter.get_sensitive() and "Los" in f.w_weiter.get_label()
           and not f.w_zurueck.get_visible(), "Willkommen: nur „Los geht’s“")
    weiter(f)
    pruefe(schritt(f) == "kamera" and "1 von 6" in f.w_zaehler.get_label(),
           "Schritt 1 von 6: Kamera")
    pruefe(not f.w_weiter.get_sensitive(), "ohne Kamera geht es nicht weiter")

    f.w_kamera_knopf.emit("clicked")
    pruefe(fertig(f) and f.zustand.kamera.startswith("/dev/v4l/by-path/"),
           "Kamera automatisch eingerichtet (stabiler Pfad)")
    pruefe("Test-Kamera" in f.w_kamera_status.get_label() and f.w_weiter.get_sensitive(),
           "Kamera mit Namen bestätigt, Weiter frei")
    weiter(f)

    # --- Gesicht aufnehmen
    a = f.w_ablauf["einlernen"]
    pruefe(schritt(f) == "einlernen" and a.k_start.get_sensitive()
           and not f.w_weiter.get_sensitive(), "Aufnehmen: Start frei, Weiter gesperrt")
    bilder = []
    alt = f._g_bild
    f._g_bild = lambda w, h, d: (bilder.append(1), alt(w, h, d))
    a.k_start.emit("clicked")
    pruefe(f.gesicht_lauf is not None and a.k_abbruch.get_visible()
           and not f.w_zurueck.get_sensitive(), "Aufnahme läuft, Navigation gesperrt")
    pruefe(fertig(f) and f.zustand.eingelernt and len(bilder) > 3
           and "aufgenommen" in a.ergebnis.get_label(), "Aufnahme mit Kamerabild abgeschlossen")
    f._g_bild = alt
    pruefe(f.w_weiter.get_sensitive() and a.k_start.get_label() == "Neu aufnehmen",
           "nach der Aufnahme: Weiter frei, Knopf heißt „Neu aufnehmen“")
    a.k_start.emit("clicked")
    warte(lambda: False, 0.5)
    a.k_abbruch.emit("clicked")
    pruefe(fertig(f) and "Abgebrochen" in a.vorschau.label.get_label(), "Abbruch greift")
    weiter(f)

    # --- Ausprobieren
    t = f.w_ablauf["testen"]
    pruefe(schritt(f) == "testen" and not f.w_weiter.get_sensitive(),
           "Ausprobieren: Weiter erst nach Erfolg")
    tipps = []
    alt_status = f._g_status
    f._g_status = lambda st: (alt_status(st), tipps.append(t.live.get_label()))
    t.k_start.emit("clicked")
    pruefe(fertig(f) and "Erkannt nach" in t.ergebnis.get_label() and f.w_weiter.get_sensitive(),
           "Ausprobieren erfolgreich, Weiter frei")
    f._g_status = alt_status
    pruefe(tipps and not any("Ähnlichkeit" in x or "0," in x for x in tipps),
           "Hinweise unter dem Bild ohne Messzahlen")
    weiter(f)

    # --- Zweite Person (freiwillig)
    g = f.w_ablauf["gegenprobe"]
    pruefe(schritt(f) == "gegenprobe" and f.w_weiter.get_label() == "Überspringen"
           and f.w_weiter.get_sensitive(), "zweite Person lässt sich überspringen")
    os.environ["WINKY_ATTRAPPE_FREMD"] = "0.60"
    hinweise = []
    alt_hinweis = g.vorschau.hinweis
    g.vorschau.hinweis = lambda x, bis_bild=False: (hinweise.append(x), alt_hinweis(x, bis_bild))
    gegenprobe_starten(g)
    pruefe(fertig(f) and any("aus dem Bild" in x for x in hinweise),
           "Countdown: erst aus dem Bild gehen")
    g.vorschau.hinweis = alt_hinweis
    pruefe("zu sehr" in g.ergebnis.get_label() and g.k_strenger.get_visible(),
           "zu ähnliche Person: Hinweis und Knopf „strenger einstellen“")
    weiter(f)
    pruefe(schritt(f) == "einschalten" and not f.w_einschalten.get_sensitive()
           and "zu ähnlich" in f.w_einschalten_status.get_label(),
           "Einschalten gesperrt, solange die zweite Person zu ähnlich war")
    f._schritt_wechseln(-1)
    g.k_strenger.emit("clicked")
    pruefe(fertig(f) and abs(f.zustand.schwelle - 0.72) < 1e-9 and not g.k_strenger.get_visible(),
           "strenger eingestellt (0,72), Hinweis verschwindet")
    weiter(f)
    pruefe(f.w_einschalten.get_sensitive(), "danach ist Einschalten frei")

    # Strenge über dem eigenen Testwert macht den Test ungültig
    f.r_spin.set_value(0.95)
    f.k_speichern.emit("clicked")
    pruefe(fertig(f) and not f.w_einschalten.get_sensitive()
           and "ausprobieren" in f.w_einschalten_status.get_label(),
           "zu strenge Einstellung verlangt neues Ausprobieren")
    f.r_spin.set_value(0.65)
    f.k_speichern.emit("clicked")
    fertig(f)
    os.environ["WINKY_ATTRAPPE_FREMD"] = "0.88"
    f.w_stapel.set_visible_child_name("gegenprobe")
    gegenprobe_starten(g)
    pruefe(fertig(f) and "noch im Bild" in g.ergebnis.get_label()
           and f.zustand.gegenprobe_wert != 0.88, "so ähnlich wie das eigene Gesicht: „warst du das?“, nichts gespeichert")
    os.environ["WINKY_ATTRAPPE_FREMD"] = "0.31"
    gegenprobe_starten(g)
    pruefe(fertig(f) and "Bestanden" in g.ergebnis.get_label() and f.w_weiter.get_label() == "Weiter",
           "zweite Person klar fremd: bestanden")
    weiter(f)

    # --- Einschalten
    pruefe(f.w_einschalten.get_sensitive() and not f.w_weiter.get_sensitive(),
           "Einschalten frei, Weiter erst danach")
    os.environ["WINKY_ATTRAPPE_PASSWORT"] = "abbrechen"
    f.w_einschalten.emit("clicked")
    pruefe(fertig(f) and not f.zustand.aktiv and f.w_einschalten.get_visible(),
           "abgebrochene Passwortabfrage ändert nichts")
    del os.environ["WINKY_ATTRAPPE_PASSWORT"]
    f.w_einschalten.emit("clicked")
    pruefe(fertig(f) and f.zustand.aktiv and "Eingeschaltet" in f.w_einschalten_status.get_label()
           and f.w_weiter.get_sensitive(), "eingeschaltet")
    weiter(f)

    # --- sudo mit ✌ (freiwillig)
    s = f.w_ablauf["sudo"]
    pruefe(schritt(f) == "sudo" and f.w_weiter.get_label() == "Überspringen"
           and not f.w_sudo.get_sensitive(), "sudo: Schalter erst nach dem ✌-Test")
    tipps = []
    f._g_status = lambda st: (alt_status(st), tipps.append(s.live.get_label()))
    s.k_start.emit("clicked")
    pruefe(fertig(f) and f.zustand.geste_ok and "✓" in s.vorschau.label.get_label(),
           "✌-Test bestanden, Ergebnis im Bild")
    f._g_status = alt_status
    pruefe(any("✌ erkannt" in x for x in tipps) and any("Gesicht erkannt" in x for x in tipps),
           "Live-Hinweis meldet Gesicht und ✌")
    pruefe(f.w_sudo.get_sensitive(), "sudo-Schalter im Assistenten frei")
    f.w_sudo.set_active(True)
    pruefe(fertig(f) and f.zustand.sudo and f.w_weiter.get_label() == "Weiter",
           "sudo mit Gesicht und ✌ eingeschaltet")
    weiter(f)
    pruefe(schritt(f) == "fertig" and f.w_weiter.get_label() == "Zur Übersicht", "Fertig-Seite")
    weiter(f)
    pruefe(warte(lambda: seite(f) == "start", 3), "zurück zur Startseite")

    # --- Startseite
    pruefe("Winky ist an" in f.s_titel.get_label() and not f.s_einrichten.get_visible(),
           "Startseite: „Winky ist an“, kein Einrichtungsknopf mehr")
    start = "".join(texte(f.abschnitte.get_child_by_name(sid))
                    for sid in ("uebersicht", "freigaben", "gesicht"))
    gefunden = [b for b in FACHBEGRIFFE if b in start]
    pruefe(not gefunden, f"Übersicht, Freigaben, Gesicht ohne Fachbegriffe {gefunden or ''}".strip())
    pruefe(f.abschnitte.get_visible_child_name() == "uebersicht" and f.s_kreis.get_visible()
           and f.s_kreis.has_css_class("an"), "Übersicht mit Statuszeichen am Winky-Symbol")
    f.abschnitt_zeigen("erweitert")
    pruefe(f.abschnitte.get_visible_child_name() == "erweitert"
           and f.inhalt_titel.get_title() == "Erweitert", "Seitenleiste wechselt den Abschnitt")
    f.abschnitt_zeigen("uebersicht")
    pruefe(f.s_sudo.get_active() and not f.k_sudo_einrichten.get_visible(),
           "sudo-Schalter an, „Einrichten“ ausgeblendet")
    pruefe(f.r_keepassxc.get_visible() and "2.8" in f.r_keepassxc.get_subtitle(),
           "KeePassXC sichtbar (Flatpak gefunden) mit Hinweis auf 2.8")
    pruefe(f.r_keepassxc_version.get_visible() and "2.8" in f.r_keepassxc_version.get_title()
           and "Flatpak 2.7.12" in f.r_keepassxc_version.get_subtitle(),
           "deutlicher Hinweis: erst ab KeePassXC 2.8, gefundene Version genannt")
    (W / "keepassxc.json").write_text('{"polkit_aktion": true, "gefunden": "Paket 2.8.0"}')
    f.aktualisieren()
    pruefe(not f.r_keepassxc_version.get_visible(), "mit KeePassXC 2.8 verschwindet der Hinweis")
    (W / "keepassxc.json").unlink()
    f.aktualisieren()
    pruefe(f.r_keepassxc_geste.get_visible() and f.r_keepassxc_geste.get_active()
           and "✌" in f.r_keepassxc.get_subtitle(), "KeePassXC verlangt standardmäßig Gesicht und ✌")
    f.r_keepassxc_geste.set_active(False)
    pruefe(fertig(f) and not f.zustand.keepassxc_geste
           and "Gesicht öffnen" in f.r_keepassxc.get_subtitle(), "✌ für KeePassXC abschaltbar")
    f.r_keepassxc_geste.set_active(True)
    pruefe(fertig(f) and f.zustand.keepassxc_geste, "✌ für KeePassXC wieder an")
    f.r_keepassxc.set_active(True)
    pruefe(fertig(f) and f.zustand.keepassxc, "KeePassXC eingeschaltet")
    f.r_keepassxc.set_active(False)
    pruefe(fertig(f) and not f.zustand.keepassxc, "KeePassXC ausgeschaltet")
    pruefe(f.r_geste_zeit.get_value() == 8, "Zeit für das ✌: Vorgabe 8 Sekunden")
    f.r_geste_zeit.set_value(20)
    f.k_geste_zeit.emit("clicked")
    pruefe(fertig(f) and f.zustand.geste_zeit == 20 and f.r_geste_zeit.get_value() == 20,
           "Zeit für das ✌ auf 20 Sekunden gespeichert")
    os.environ["WINKY_ATTRAPPE_PASSWORT"] = "kein_dialog"
    f.r_pause.set_active(True)
    pruefe(fertig(f) and getattr(f, "hilfe_dialog", None) is not None and not f.zustand.pausiert,
           "kein Passwortdialog: klarer Hinweis mit Abmelden statt stummem Fehlschlag")
    del os.environ["WINKY_ATTRAPPE_PASSWORT"]
    f.hilfe_dialog.close()
    f._hilfe_offen = False
    f.aktualisieren()
    f.ueber_zeigen()
    pruefe(f.ueber.get_application_name() == "Winky" and f.ueber.get_version(),
           "„Über Winky“ zeigt Name und Version")
    f.ueber.close()
    pruefe(not f.r_anmeldung.get_active() and f.r_anmeldung.get_sensitive(),
           "Erstanmeldung: ab Werk aus, schaltbar")
    f.r_anmeldung.set_active(True)
    pruefe(f.anmeldung_dialog is not None and f.aktion is None and "keyring" not in
           f.anmeldung_dialog.get_body() and "Schlüsselbund" in f.anmeldung_dialog.get_body(),
           "Erstanmeldung: erst Risikohinweis, noch keine Passwortabfrage")
    f.anmeldung_dialog.emit("response", "abbrechen")
    pruefe(not f.zustand.anmeldung and not f.r_anmeldung.get_active(),
           "Risikohinweis abgebrochen: Schalter bleibt aus")
    f.r_anmeldung.set_active(True)
    f.anmeldung_dialog.emit("response", "an")
    warte(lambda: f.aktion is not None, 2)
    pruefe(fertig(f) and f.zustand.anmeldung, "Erstanmeldung per Gesicht eingeschaltet")
    pruefe(f.r_schluesselbund.get_visible() and not f.r_schluesselbund.get_active(),
           "Schlüsselbund-Schalter erscheint mit der Erstanmeldung, ab Werk aus")
    f.r_schluesselbund.set_active(True)
    f._schluesselbund_umgeschaltet(f.r_schluesselbund, None)   # doppelte Meldung von GTK
    dialoge = [d for d in [getattr(f, "schluessel_dialog", None)] if d]
    pruefe(len(dialoge) == 1, "Schlüsselbund: doppeltes Umschalten öffnet nur einen Dialog")
    vorher = f.r_schluesselbund.get_active()
    f._regelmaessig()
    pruefe(f.r_schluesselbund.get_active() == vorher and f.get_visible_dialog() is not None,
           "kein Auffrischen, solange der Dialog offen ist")
    pruefe(f.schluessel_dialog.get_default_response() == "ok" and f.e_passwort.get_activates_default(),
           "Enter im Passwortfeld versiegelt")
    f.schluessel_dialog.emit("response", "abbrechen")
    f.schluessel_dialog = None
    f.aktualisieren()
    pruefe(not f.r_schluesselbund.get_active(), "Abbrechen lässt den Schalter aus")
    f.schluesselbund_versiegeln("falsch")
    pruefe(fertig(f) and not f.zustand.schluesselbund, "falsches Passwort: nichts versiegelt")
    f.schluesselbund_versiegeln("richtig")
    pruefe(fertig(f) and f.zustand.schluesselbund and f.r_schluesselbund.get_active(),
           "Passwort versiegelt, Schalter an")
    f.r_schluesselbund.set_active(False)
    pruefe(fertig(f) and not f.zustand.schluesselbund, "Versiegelung wieder entfernt")
    f.r_anmeldung.set_active(False)
    pruefe(fertig(f) and not f.zustand.anmeldung, "Erstanmeldung wieder mit Passwort")
    pruefe(not f.r_dialoge.get_active() and f.r_dialoge.get_sensitive(),
           "Administrator-Dialoge: ab Werk aus, nach ✌-Test schaltbar")
    f.r_dialoge.set_active(True)
    pruefe(fertig(f) and f.zustand.dialoge, "Administrator-Dialoge mit ✌ eingeschaltet")
    f.r_dialoge.set_active(False)
    pruefe(fertig(f) and not f.zustand.dialoge, "Administrator-Dialoge wieder Passwort")
    pruefe(any("entsperrt" in r.get_title() for r in f._verlauf_zeilen), "Verlauf zeigt den Test")
    f.r_pause.set_active(True)
    pruefe(fertig(f) and f.zustand.pausiert and "Pause" in f.s_titel.get_label(), "pausiert")
    f.r_pause.set_active(False)
    pruefe(fertig(f) and not f.zustand.pausiert, "fortgesetzt")

    # Kameraseite verlassen bricht den Ablauf ab
    f.kamera_oeffnen("testen")
    pruefe(seite(f) == "kamera" and f.k_seite.get_title() == "Ausprobieren",
           "„Erkennung ausprobieren“ öffnet die Kameraseite")
    f.k_ansicht.k_start.emit("clicked")
    warte(lambda: False, 0.3)
    f.nav.pop()
    pruefe(fertig(f) and seite(f) == "start", "Kameraseite verlassen bricht die Aufnahme ab")

    # Ausschalten: abgebrochene Passwortabfrage, dann wirklich
    os.environ["WINKY_ATTRAPPE_PASSWORT"] = "abbrechen"
    f.r_aktiv.set_active(False)
    fertig(f)
    pruefe(f.zustand.aktiv and f.r_aktiv.get_active(),
           "abgebrochene Passwortabfrage: Schalter springt zurück")
    del os.environ["WINKY_ATTRAPPE_PASSWORT"]
    f.r_aktiv.set_active(False)
    pruefe(fertig(f) and not f.zustand.aktiv, "ausgeschaltet")
    pruefe(not f.zustand.sudo, "Ausschalten schaltet sudo mit ✌ mit aus")
    pruefe("Fast fertig" in f.s_titel.get_label() and f.s_einrichten.get_visible()
           and f.s_einrichten.get_label() == "Einrichtung fortsetzen",
           "danach: „Einrichtung fortsetzen“")

    # Erweitert: Kamera wählen
    f._kamera_auswahl()
    pruefe(fertig(f) and DIALOGE, "Kameraliste erscheint")
    DIALOGE.pop().emit("response", "ok")
    warte(lambda: f.aktion is not None, 2)
    pruefe(fertig(f) and f.zustand.kamera, "gewählte Kamera übernommen")

    # Neu aufnehmen verlangt neues Ausprobieren und einen neuen ✌-Test
    f.kamera_oeffnen("einlernen")
    f.k_ansicht.k_start.emit("clicked")
    fertig(f)
    pruefe("Nötig" in f.r_geste.get_subtitle(), "nach neuer Aufnahme ist der ✌-Test neu fällig")
    pruefe(not f.r_keepassxc.get_sensitive() and "✌ testen" in f.r_keepassxc.get_subtitle(),
           "KeePassXC mit ✌ erst nach neuem ✌-Test")
    pruefe(not f.r_aktiv.get_sensitive() and "ausprobieren" in f.r_aktiv.get_subtitle(),
           "nach neuer Aufnahme ist neues Ausprobieren nötig")
    f.nav.pop()
    f.einrichtung_oeffnen()
    pruefe(schritt(f) == "testen", "Einrichtung fortsetzen springt zum offenen Schritt")
    f.nav.pop_to_tag("start")

    # Gesichtsdaten löschen (eigenes Passwort genügt)
    f._vorlagen_loeschen_fragen()
    DIALOGE.pop().emit("response", "weg")
    warte(lambda: f.aktion is not None, 2)
    pruefe(fertig(f) and not f.zustand.eingelernt
           and f.gesicht_stapel.get_visible_child_name() == "leer",
           "Gesichtsdaten gelöscht, „Gesicht“ zeigt den Weg zur Einrichtung")

    pruefe((f.k_store is not None) == bool(Gio.AppInfo.get_default_for_uri_scheme("appstream")),
           "Knopf zur Software-Verwaltung genau dann, wenn eine vorhanden ist")

    # Prüfdienst fehlt
    (W / "run/winky.sock").unlink()
    f.aktualisieren()
    pruefe(f.banner.get_revealed() and not f.w_kamera_knopf.get_sensitive()
           and not f.s_einrichten.get_visible(), "ohne Prüfdienst: Hinweis sichtbar, alles gesperrt")


def main():
    for pfad in ("usr/libexec/winky/winky-matcher", "run/winky.sock"):
        (W / pfad).parent.mkdir(parents=True, exist_ok=True)
        (W / pfad).touch()
    (W / "etc/pam.d").mkdir(parents=True, exist_ok=True)
    (W / "etc/pam.d/common-auth").write_text("auth [success=1 default=ignore] pam_unix.so\n")
    (W / "etc/winky").mkdir(parents=True, exist_ok=True)
    (W / "etc/winky/winky.conf").write_text("schwelle = 0.65\nkamera =\n")
    Gtk.Settings.get_default().set_property("gtk-enable-animations", False)
    app = Adw.Application(application_id="io.github.dieschatten.WinkyTest")

    def los(a):
        try:
            f = gesicht_app.Fenster(a)
            f.present()
            warte(lambda: False, 0.5)
            test(f)
            f.close()
        except Exception as e:
            traceback.print_exc()
            FEHLER.append(f"Absturz: {e}")
        a.quit()
        return False

    app.connect("activate", lambda a: GLib.idle_add(los, a))
    app.run([])
    print(f"\n{len(FEHLER)} Fehler")
    return 1 if FEHLER else 0


if __name__ == "__main__":
    sys.exit(main())
