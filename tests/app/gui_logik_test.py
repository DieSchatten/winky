#!/usr/bin/env python3
"""Ablauftest der App mit Attrappe (ohne Kamera, root und Systemänderung): Assistent komplett,
dann Startseite, Erweitert und Fehlerfälle.

Aufruf (braucht ein GTK-Display, z. B. Broadway):
  gtk4-broadwayd :9 &
  WINKY_ATTRAPPE=1 WINKY_TESTWURZEL=/tmp/w GDK_BACKEND=broadway BROADWAY_DISPLAY=:9 \\
    python3 tests/app/gui_logik_test.py
"""

import json
import os
import sys
import time
import traceback
from pathlib import Path

assert os.environ.get("WINKY_ATTRAPPE") == "1", "nur mit Attrappe ausführen"
os.environ["GSETTINGS_BACKEND"] = "memory"   # Sperrzeit nie in den echten Einstellungen
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
    sitzung, sperre = f._desktop()
    pruefe(f.w_sperre.an.get_active()
           and f.w_sperre.zeit.get_value() * 60 == sitzung.get_uint("idle-delay"),
           "Einschalten-Schritt zeigt die automatische Sperre des Systems")
    f.w_sperre.zeit.set_value(4)
    pruefe(sitzung.get_uint("idle-delay") == 240
           and warte(lambda: f.r_sperrzeit.get_value() == 4, 2),
           "Sperrzeit im Assistenten gesetzt, Freigaben zeigen sie sofort")
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
    pruefe(set(f.w_mehr) == {"freigaben", "gesicht", "erweitert"},
           "Fertig-Seite nennt weitere Möglichkeiten (Freigaben, Gesicht, Erweitert)")
    weiter(f)
    pruefe(warte(lambda: seite(f) == "start", 3), "zurück zur Startseite")
    f.w_mehr["erweitert"].emit("clicked")
    pruefe(seite(f) == "start" and f.abschnitte.get_visible_child_name() == "erweitert",
           "„Öffnen“ auf der Fertig-Seite springt zum Abschnitt")
    f.abschnitt_zeigen("uebersicht")

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
    pruefe(not f.r_entsperren_geste.get_active() and f.r_entsperren_geste.get_sensitive(),
           "Entsperren nur mit ✌: ab Werk aus, nach ✌-Test schaltbar")
    f.r_entsperren_geste.set_active(True)
    pruefe(fertig(f) and f.zustand.entsperren_geste and "✌" in f.s_text.get_label(),
           "Entsperren nur mit ✌ eingeschaltet, Übersicht sagt es")
    f.r_entsperren_geste.set_active(False)
    pruefe(fertig(f) and not f.zustand.entsperren_geste, "Entsperren wieder mit dem Gesicht allein")
    f.r_dialoge.set_active(False)
    pruefe(fertig(f) and not f.zustand.dialoge, "Administrator-Dialoge wieder Passwort")
    pruefe(any("entsperrt" in r.get_title() for r in f._verlauf_zeilen), "Verlauf zeigt den Test")
    v = json.loads((W / "verlauf.json").read_text())
    (W / "verlauf.json").write_text(json.dumps([
        {"zeit": time.time(), "status": "treffer", "wert": 0.9, "dauer_ms": 1500, "grund": "",
         "zweck": "dialog", "befehl": ""},
        {"zeit": time.time(), "status": "kein_treffer", "wert": 0.9, "dauer_ms": 8000,
         "grund": "kein_zeichen", "zweck": "sudo", "befehl": "sudo rm -rf /tmp/x"},
        {"zeit": time.time(), "status": "abgelehnt", "wert": -1, "dauer_ms": 2100,
         "grund": "passwort", "zweck": "sudo", "befehl": "sudo apt update"}] + v))
    f.aktualisieren()
    pruefe(f._verlauf_zeilen[0].get_title() == "Administrator-Dialog mit ✌ freigegeben"
           and f._verlauf_zeilen[1].get_title() == "sudo nicht bestätigt: sudo rm -rf /tmp/x",
           "Verlauf benennt Dialog-Freigaben und abgelehnte sudo-Befehle")
    pruefe(f._verlauf_zeilen[2].get_title() == "sudo: Passwort statt ✌ eingegeben: sudo apt update",
           "Verlauf: Passwort statt ✌ ist kein abgelehntes sudo")
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

    # Gesichtsdaten im TPM: erst Rückfrage mit Erklärung; ohne TPM klar abgelehnt; Fehler sichtbar
    pruefe(not f.r_vorlagen_tpm.get_active() and f.r_vorlagen_tpm.get_sensitive(),
           "TPM-Versiegelung: ab Werk aus, schaltbar")
    f.r_vorlagen_tpm.set_active(True)
    pruefe(f.tpm_dialog is not None and f.aktion is None and "Dual Boot" in f.tpm_dialog.get_body()
           and "BIOS" in f.tpm_dialog.get_body(), "TPM: erst ausführliche Rückfrage, noch kein Passwort")
    f.tpm_dialog.emit("response", "abbrechen")
    pruefe(not f.zustand.vorlagen_tpm and not f.r_vorlagen_tpm.get_active(),
           "TPM: Abbrechen lässt alles, wie es ist")
    os.environ["WINKY_ATTRAPPE_TPM"] = "fehlt"
    f.r_vorlagen_tpm.set_active(True)
    f.tpm_dialog.emit("response", "an")
    warte(lambda: f.aktion is not None, 2)
    pruefe(fertig(f) and not f.zustand.vorlagen_tpm, "TPM: ohne TPM-Chip abgelehnt")
    del os.environ["WINKY_ATTRAPPE_TPM"]
    f.r_vorlagen_tpm.set_active(True)
    f.tpm_dialog.emit("response", "an")
    warte(lambda: f.aktion is not None, 2)
    pruefe(fertig(f) and f.zustand.vorlagen_tpm and "verschlüsselt" in f.r_vorlagen_tpm.get_subtitle(),
           "TPM-Versiegelung eingeschaltet")
    st = json.loads((W / "var/lib/winky/status" / f"{os.getuid()}.json").read_text())
    (W / "var/lib/winky/status" / f"{os.getuid()}.json").write_text(
        json.dumps(dict(st, vorlagen_tpm_fehler=1)))
    f.aktualisieren()
    pruefe("neu auf" in f.s_titel.get_label() + f.s_text.get_label() + f.r_vorlagen_tpm.get_subtitle()
           and f.s_kreis.has_css_class("fehlt"), "TPM: nicht mehr entsiegelbar → klarer Hinweis, neu aufnehmen")
    (W / "var/lib/winky/status" / f"{os.getuid()}.json").write_text(json.dumps(st))
    f.r_vorlagen_tpm.set_active(False)
    pruefe(fertig(f) and not f.zustand.vorlagen_tpm, "TPM-Versiegelung wieder aus")

    # Automatisch sperren: setzt die GNOME-Werte (hier nur im Speicher)
    sitzung, sperre = f._desktop()
    sitzung.set_uint("idle-delay", 600)
    sperre.set_boolean("lock-enabled", True)
    sperre.set_uint("lock-delay", 0)
    f.aktualisieren()
    pruefe(f.r_sperre_an.get_active() and f.r_sperrzeit.get_value() == 10
           and f.r_sperrzeit.get_sensitive(), "Sperre: zeigt die Werte des Systems (an, 10 Minuten)")
    f.r_sperrzeit.set_value(7)
    pruefe(sitzung.get_uint("idle-delay") == 420 and sperre.get_boolean("lock-enabled")
           and "sperrt" in f.r_sperre_an.get_subtitle(), "Sperre: freie Zeit, 7 Minuten")
    sperre.set_uint("lock-delay", 30)
    f.aktualisieren()
    pruefe("30 s" in f.r_sperrzeit.get_subtitle(), "Sperre: nennt eine Verzögerung aus dem System")
    f.r_sperrzeit.set_value(1)
    pruefe(sitzung.get_uint("idle-delay") == 60 and sperre.get_uint("lock-delay") == 0
           and f.r_sperrzeit.get_subtitle() == "", "Sperre: neue Zeit sperrt sofort, 1 Minute")
    f.r_sperre_an.set_active(False)
    pruefe(not sperre.get_boolean("lock-enabled") and sitzung.get_uint("idle-delay") == 60
           and not f.r_sperrzeit.get_sensitive() and "Super+L" in f.r_sperre_an.get_subtitle(),
           "Sperre aus: Bildschirm geht weiter aus, sperrt nicht")
    f.r_sperrzeit.set_value(20)
    pruefe(sitzung.get_uint("idle-delay") == 60, "Sperre aus: Minutenfeld ändert nichts")
    sitzung.set_uint("idle-delay", 0)
    sperre.set_boolean("lock-enabled", True)
    f.aktualisieren()
    pruefe(not f.r_sperre_an.get_active(), "Bildschirm geht nie aus: Sperre gilt als aus")
    f.r_sperre_an.set_active(True)
    pruefe(sitzung.get_uint("idle-delay") == f.r_sperrzeit.get_value() * 60 > 0
           and sperre.get_boolean("lock-enabled"), "Sperre einschalten setzt die gewählte Zeit")
    sitzung.set_uint("idle-delay", 90)
    f.aktualisieren()
    pruefe("2 Minuten" in f.r_sperrzeit.get_subtitle(), "eigener Wert aus den Systemeinstellungen bleibt sichtbar")

    # Infrarot-Kamera nur für Winky: ab Werk aus; geteilter Anschluss wird abgelehnt; Wirkung sichtbar
    pruefe(not f.r_ir_schutz.get_active() and f.r_ir_schutz.get_sensitive()
           and "jedes Programm" in f.r_ir_schutz.get_subtitle(),
           "IR-Schutz: ab Werk aus, mit eingerichteter Kamera schaltbar")
    os.environ["WINKY_ATTRAPPE_IR"] = "geteilt"
    f.r_ir_schutz.set_active(True)
    pruefe(fertig(f) and not f.zustand.ir_schutz and not f.r_ir_schutz.get_active(),
           "IR-Schutz: teilt sich die IR-Kamera den Anschluss, bleibt alles, wie es ist")
    del os.environ["WINKY_ATTRAPPE_IR"]
    f.r_ir_schutz.set_active(True)
    pruefe(fertig(f) and f.zustand.ir_schutz and "können die Infrarot-Kamera nicht"
           in f.r_ir_schutz.get_subtitle(), "IR-Schutz eingeschaltet")
    (W / "ir-offen").touch()
    f.aktualisieren()
    pruefe("Wirkt nicht" in f.r_ir_schutz.get_subtitle(), "IR-Schutz: App warnt, wenn er nicht wirkt")
    (W / "ir-offen").unlink()
    f.r_ir_schutz.set_active(False)
    pruefe(fertig(f) and not f.zustand.ir_schutz, "IR-Schutz wieder aus")

    # Erweitert: Kamera wählen
    f._kamera_auswahl()
    pruefe(fertig(f) and DIALOGE, "Kameraliste erscheint")
    DIALOGE.pop().emit("response", "ok")
    warte(lambda: f.aktion is not None, 2)
    pruefe(fertig(f) and f.zustand.kamera, "gewählte Kamera übernommen")

    # Ergänzen: benannt, behält Ausprobieren und ✌-Test; ohne Erkennung wird nichts ergänzt
    vorher = f.zustand.vorlagen
    os.environ["WINKY_ATTRAPPE_ERGAENZEN"] = "fremd"
    f.kamera_oeffnen("ergaenzen")
    pruefe(f.k_seite.get_title() == "Gesicht ergänzen" and f.k_ansicht.k_start.get_sensitive()
           and f.k_ansicht.name_liste.get_visible(), "„Gesicht ergänzen“ mit Namensfeld")
    f.k_ansicht.e_name.set_text("Mit Brille")
    f.k_ansicht.k_start.emit("clicked")
    pruefe(fertig(f) and f.zustand.vorlagen == vorher and "nicht sicher erkannt"
           in f.k_ansicht.ergebnis.get_label(), "ohne sichere Erkennung wird nichts ergänzt")
    del os.environ["WINKY_ATTRAPPE_ERGAENZEN"]
    pruefe(f._tipp({"grund": "ok", "t": 2}, "ergaenzen")[0].startswith("Erst wie immer")
           and f._tipp({"grund": "ok", "t": 12}, "ergaenzen")[0].startswith("Jetzt ändern"),
           "Live-Hinweis: erst wie immer, dann „Jetzt ändern“")
    f.k_ansicht.k_start.emit("clicked")
    pruefe(fertig(f) and f.zustand.vorlagen == vorher + 11 and "11" in
           f.k_ansicht.ergebnis.get_label(), "ergänzt: 11 Bilder dazu")
    pruefe(f.k_ansicht.k_start.get_label() == "Weiter ergänzen" and f.r_aktiv.get_sensitive()
           and "Nötig" not in f.r_geste.get_subtitle(),
           "nach dem Ergänzen bleiben Ausprobieren und ✌-Test gültig")
    pruefe(f.g_ergaenzungen.get_visible() and [r.get_title() for r in f._ergaenzung_zeilen]
           == ["Mit Brille"], "Abschnitt Gesicht listet „Mit Brille“")
    f.k_ansicht.e_name.set_text("mit brille")
    f.k_ansicht.k_start.emit("clicked")
    pruefe(fertig(f) and len(f._ergaenzung_zeilen) == 1 and "ersetzt"
           in f.k_ansicht.ergebnis.get_label(), "gleicher Name ersetzt die Ergänzung")
    for name in ("Licht", "Bart"):
        f.k_ansicht.e_name.set_text(name)
        f.k_ansicht.k_start.emit("clicked")
        fertig(f)
    f.k_ansicht.e_name.set_text("Hut")
    f.k_ansicht.k_start.emit("clicked")
    pruefe(fertig(f) and len(f._ergaenzung_zeilen) == 3 and "drei" in
           f.k_ansicht.ergebnis.get_label(), "höchstens drei Ergänzungen")
    seite_liste = f.k_ansicht.ergaenzungen
    pruefe(seite_liste.get_visible() and [r.get_title() for r in seite_liste.zeilen]
           == ["mit brille", "Licht", "Bart"], "die Ergänzen-Seite zeigt, was schon drin ist")
    seite_liste.zeilen[2].knopf.emit("clicked")
    DIALOGE.pop().emit("response", "weg")
    warte(lambda: f.aktion is not None, 2)
    pruefe(fertig(f) and [r.get_title() for r in seite_liste.zeilen] == ["mit brille", "Licht"],
           "„Bart“ direkt auf der Ergänzen-Seite gelöscht")
    f.nav.pop()
    f._ergaenzung_zeilen[1].knopf.emit("clicked")
    DIALOGE.pop().emit("response", "weg")
    warte(lambda: f.aktion is not None, 2)
    pruefe(fertig(f) and [r.get_title() for r in f._ergaenzung_zeilen] == ["mit brille"],
           "„Licht“ im Abschnitt Gesicht gelöscht, „mit brille“ bleibt")
    f.kamera_oeffnen("testen")
    pruefe(not f.k_ansicht.ergaenzungen.get_visible(), "beim Ausprobieren keine Ergänzungsliste")
    f.nav.pop()

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
