"""Rundes Kamerabild mit Fortschrittsring und Stil der App (nur Anzeige, nichts gespeichert)."""

import math

from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk

from sprache import DEUTSCH, _

CSS = b"""
.gut { color: @success_color; }
.warnung { color: @warning_color; }
.statuszeichen { border-radius: 999px; min-width: 34px; min-height: 34px; color: white;
                 border: 3px solid @window_bg_color; }
.statuszeichen.an { background-color: #2ec27e; }
.statuszeichen.pause { background-color: #ff8c00; }
.statuszeichen.fehlt { background-color: #e01b24; }
.schrittnummer { border-radius: 999px; min-width: 24px; min-height: 24px; font-weight: 800;
                 font-size: 9.5pt; color: white; background-color: @accent_bg_color; }
.ringhinweis { background-color: alpha(black, 0.55); color: white; padding: 10px 18px;
               border-radius: 999px; font-size: 15pt; font-weight: 800; }
"""

_css_geladen = False


def css_laden():
    global _css_geladen
    if _css_geladen:
        return
    # Unter GTK-Broadway (Tests) fehlt die Schrift-DPI, libadwaita zeigte sonst alles sehr schmal
    anzeige = Gdk.Display.get_default()
    if "Broadway" in anzeige.__gtype__.name:
        einstellungen = Gtk.Settings.get_default()
        if einstellungen.get_property("gtk-xft-dpi") <= 0:
            einstellungen.set_property("gtk-xft-dpi", 96 * 1024)
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _css_geladen = True


RING_FARBEN = {"gut": (0.19, 0.82, 0.35), "warnung": (1.0, 0.62, 0.04),
               "laeuft": (0.04, 0.52, 1.0)}


class RingVorschau(Gtk.Widget):
    """Rundes Kamerabild mit einem Ring aus Strichen, der sich mit dem Fortschritt füllt
    (wie beim Einrichten von Face ID). Gleiche Bedienung wie Vorschau, dazu fortschritt()."""

    __gtype_name__ = "WinkyRingVorschau"
    STRICHE = 72

    def __init__(self, groesse=300):
        super().__init__()
        css_laden()
        self.set_layout_manager(Gtk.BinLayout())
        self.set_size_request(groesse, groesse)
        self.set_halign(Gtk.Align.CENTER)
        self.textur = None
        self.anteil = 0.0
        self.farbe = "laeuft"
        self.label = Gtk.Label(label=_("Camera off"), halign=Gtk.Align.CENTER,
                               valign=Gtk.Align.CENTER, wrap=True, max_width_chars=16,
                               justify=Gtk.Justification.CENTER)
        self.label.add_css_class("ringhinweis")
        self.label.set_parent(self)
        self._bis_bild = False

    def do_dispose(self):
        if self.label is not None:
            self.label.unparent()
            self.label = None

    def do_snapshot(self, s):
        w, h = self.get_width(), self.get_height()
        d = min(w, h)
        cx, cy = w / 2, h / 2
        r = d / 2 - 22
        rect = Graphene.Rect().init(cx - r, cy - r, 2 * r, 2 * r)
        rund = Gsk.RoundedRect()
        rund.init_from_rect(rect, r)
        s.push_rounded_clip(rund)
        grund = Gdk.RGBA()
        grund.parse("#1c1c1e")
        s.append_color(grund, rect)
        if self.textur is not None:
            tw, th = self.textur.get_width(), self.textur.get_height()
            f = 2 * r / min(tw, th)
            s.append_texture(self.textur, Graphene.Rect().init(cx - tw * f / 2, cy - th * f / 2,
                                                                 tw * f, th * f))
        s.pop()
        # Striche als zwei Pfade (gefüllt, offen) mit GTKs eigener Pfad-Zeichnung
        voll = round(self.anteil * self.STRICHE)
        an, aus = Gsk.PathBuilder.new(), Gsk.PathBuilder.new()
        for i in range(self.STRICHE):
            winkel = i / self.STRICHE * 2 * math.pi - math.pi / 2
            innen, aussen = r + 8, r + 18
            pb = an if i < voll else aus
            pb.move_to(cx + innen * math.cos(winkel), cy + innen * math.sin(winkel))
            pb.line_to(cx + aussen * math.cos(winkel), cy + aussen * math.sin(winkel))
        strich = Gsk.Stroke.new(3.2)
        strich.set_line_cap(Gsk.LineCap.ROUND)
        vorder = self.get_color()
        blass = Gdk.RGBA()
        blass.red, blass.green, blass.blue, blass.alpha = (vorder.red, vorder.green, vorder.blue,
                                                           0.18)
        farbe = Gdk.RGBA()
        farbe.red, farbe.green, farbe.blue = RING_FARBEN.get(self.farbe, RING_FARBEN["laeuft"])
        farbe.alpha = 1.0
        s.append_stroke(aus.to_path(), strich, blass)
        if voll:
            s.append_stroke(an.to_path(), strich, farbe)
        self.snapshot_child(self.label, s)

    def zeige(self, w, h, daten):
        self.textur = Gdk.MemoryTexture.new(w, h, Gdk.MemoryFormat.R8G8B8, GLib.Bytes.new(daten),
                                            w * 3)
        if self._bis_bild:
            self.label.set_visible(False)
            self._bis_bild = False
        self.queue_draw()

    def hinweis(self, text, bis_bild=False):
        """bis_bild: verschwindet mit dem ersten Kamerabild (Countdown, Kamerastart)."""
        self.label.set_label(text)
        self.label.set_visible(True)
        self._bis_bild = bis_bild

    def fortschritt(self, anteil, farbe="laeuft"):
        self.anteil = max(0.0, min(1.0, anteil))
        self.farbe = farbe
        self.queue_draw()

    def leeren(self, text=None):
        self.textur = None
        self.anteil = 0.0
        self.farbe = "laeuft"
        self.hinweis(_("Camera off") if text is None else text)
        self.queue_draw()


def komma(v, stellen=3):
    """Zahl mit festen Nachkommastellen, auf Deutsch mit Komma, sonst mit Punkt."""
    text = f"{v:.{stellen}f}"
    return text.replace(".", ",") if DEUTSCH else text
