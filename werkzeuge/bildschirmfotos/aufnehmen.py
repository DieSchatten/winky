#!/usr/bin/env python3
"""Bildschirmfotos der App für die Software-Verwaltung, mit Verwaltungs-Attrappe und gezeichnetem
Kamerabild. Ausgabe: packaging/bildschirmfotos/{startseite,einrichtung,sicherheit}.png
(WINKY_FOTO_ZIEL=Ordner; WINKY_FOTO_ALLE=1: zusätzlich jeder Assistentenschritt).

Aufruf: scripts/bildschirmfotos.sh (startet einen eigenen Broadway-Bildschirm)
"""

import json
import os
import sys
import time
from pathlib import Path

assert os.environ.get("WINKY_ATTRAPPE") == "1", "nur mit Attrappe ausführen"
PROJEKT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJEKT / "src" / "app"))
sys.path.insert(0, str(PROJEKT / "werkzeuge" / "bildschirmfotos"))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Graphene, Gsk, Gtk  # noqa: E402

import gesicht_app  # noqa: E402
import illustration  # noqa: E402

W = Path(os.environ["WINKY_TESTWURZEL"])
ZIEL = Path(os.environ.get("WINKY_FOTO_ZIEL", PROJEKT / "packaging" / "bildschirmfotos"))
ALLE = os.environ.get("WINKY_FOTO_ALLE") == "1"
GROESSE = (900, 768)   # höher zeichnet Broadway nicht


def schreibe(pfad, inhalt):
    p = W / pfad
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(inhalt, bytes):
        p.write_bytes(inhalt)
    else:
        p.write_text(inhalt)


def beispielzustand():
    """Ein fertig eingerichteter Rechner: aktiv, getestet, Gegenprobe bestanden."""
    jetzt = int(time.time())
    vor_drei_tagen = int(time.mktime(time.localtime(jetzt - 3 * 86400)[:3] + (19, 40, 0, 0, 0, -1)))
    schreibe("usr/libexec/winky/winky-matcher", "")
    schreibe("run/winky.sock", "")
    schreibe("etc/pam.d/common-auth",
             "auth [success=end default=ignore] pam_winky.so services=gdm-password\n"
             "auth [success=1 default=ignore] pam_unix.so nullok\n")
    schreibe("etc/winky/winky.conf",
             "schwelle = 0.65\nkamera = /dev/v4l/by-path/pci-0000:00:14.0-usb-0:5:1.2-video-index0\n"
             "blinkpruefung = ja\n")
    schreibe(f"var/lib/winky/status/{os.getuid()}.json", json.dumps({
        "vorlagen": 30, "eingelernt": vor_drei_tagen, "test_ok": vor_drei_tagen + 90,
        "test_wert": 0.912, "gegenprobe_wert": 0.284, "gegenprobe_ok": True,
        "gegenprobe_zeit": vor_drei_tagen + 300}))
    schreibe("keepassxc.json", json.dumps({"polkit_aktion": False, "gefunden": None}))
    heute = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
    verlauf = [(17, 42, "treffer", 0.903, 410), (13, 5, "treffer", 0.887, 380),
               (12, 58, "kein_gesicht", -1, 1200), (9, 31, "treffer", 0.921, 450),
               (8, 2, "treffer", 0.874, 520)]
    schreibe("verlauf.json", json.dumps([
        {"zeit": heute + h * 3600 + m * 60, "status": st, "wert": wert, "dauer_ms": dauer,
         "grund": "", "zweck": "sperrbildschirm"} for h, m, st, wert, dauer in verlauf]))
    _, rgb = illustration.zeichne()
    schreibe("kamerabild.rgb", f"{illustration.B} {illustration.H}\n".encode() + rgb)
    os.environ["WINKY_ATTRAPPE_BILD"] = str(W / "kamerabild.rgb")
    os.environ["WINKY_ATTRAPPE_DAUER"] = "30"


def warte(sekunden, bedingung=lambda: False):
    ctx = GLib.MainContext.default()
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende and not bedingung():
        ctx.iteration(False)
        time.sleep(0.01)


def foto(fenster, name):
    b, h = fenster.get_width(), fenster.get_height()
    for _ in range(100):  # leer, solange das Fenster gerade neu gezeichnet wird
        schnapp = Gtk.Snapshot()
        Gtk.WidgetPaintable.new(fenster).snapshot(schnapp, b, h)
        knoten = schnapp.to_node()
        if knoten is not None:
            break
        warte(0.05)
    else:
        raise RuntimeError(f"{name}: Fenster liefert kein Bild")
    renderer = Gsk.CairoRenderer()
    renderer.realize_for_display(Gdk.Display.get_default())
    try:
        textur = renderer.render_texture(knoten, Graphene.Rect().init(0, 0, b, h))
    finally:
        renderer.unrealize()
    ZIEL.mkdir(parents=True, exist_ok=True)
    textur.save_to_png(str(ZIEL / f"{name}.png"))
    print(f"{name}.png  {b}x{h}", flush=True)


def los(app):
    # Standarddesign statt des Desktop-Designs (Zorin lädt sein Design über gtk-theme-name)
    Gtk.Settings.get_default().set_property("gtk-theme-name", "Adwaita")
    # Ohne Überblendungen: Broadway zeichnet Übergänge nicht immer zu Ende
    Gtk.Settings.get_default().set_property("gtk-enable-animations", False)
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
    f = gesicht_app.Fenster(app)
    f.set_default_size(*GROESSE)
    f.present()
    warte(1.0)

    f.nav.pop_to_tag("start")
    warte(0.6)
    foto(f, "startseite")

    # Einrichtung: Schritt „Ausprobieren“ mit laufender Kamera
    f.einrichtung_oeffnen()
    f.w_stapel.set_visible_child_name("testen")
    warte(0.6)
    bilder = []
    alt = f._g_bild
    f._g_bild = lambda b, h, d: (bilder.append(1), alt(b, h, d))
    f.w_ablauf["testen"].starten()
    warte(10, lambda: len(bilder) >= 8)
    warte(0.5)
    foto(f, "einrichtung")
    f.gesicht_lauf.abbrechen()
    warte(5, lambda: f.gesicht_lauf is None)
    f._g_bild = alt

    f.nav.pop_to_tag("start")
    f.nav.push_by_tag("sicherheit")
    warte(0.6)
    foto(f, "sicherheit")

    if ALLE:  # zur Durchsicht, nicht für das Paket
        for sid in gesicht_app.SCHRITTE:
            f.nav.pop_to_tag("start")
            f.einrichtung_oeffnen()
            f.w_stapel.set_visible_child_name(sid)
            warte(0.6)
            foto(f, f"schritt-{sid}")
        f.nav.pop_to_tag("start")
        f.nav.push_by_tag("erweitert")
        warte(0.6)
        foto(f, "erweitert")
    f.close()
    app.quit()
    return False


def main():
    beispielzustand()
    app = Adw.Application(application_id="io.github.dieschatten.WinkyFotos")
    app.connect("activate", lambda a: GLib.idle_add(los, a))
    app.run([])


if __name__ == "__main__":
    main()
