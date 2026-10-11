"""Kamerabild mit Hinweistext darüber (nur Anzeige, nichts wird gespeichert)."""

import math

from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk

from sprache import DEUTSCH, _, ngettext

CSS = b"""
.hinweis { background-color: alpha(black, 0.6); color: white; padding: 14px 22px;
           border-radius: 14px; font-size: 22pt; font-weight: bold; }
.gut { color: #1fa855; }
.warnung { color: #e07800; }
.bildrahmen { background-color: black; border-radius: 12px; }

/* Startseite: Statuskarte */
.held { border-radius: 24px; padding: 22px 24px; }
.held.an { background-image: linear-gradient(135deg, alpha(#30d158, 0.20), alpha(#64d2ff, 0.14)); }
.held.pause { background-image: linear-gradient(135deg, alpha(#ff9f0a, 0.22), alpha(#ffd60a, 0.12)); }
.held.neu { background-image: linear-gradient(135deg, alpha(#0a84ff, 0.18), alpha(#bf5af2, 0.14)); }
.held.fehlt { background-image: linear-gradient(135deg, alpha(#ff453a, 0.20), alpha(#ff9f0a, 0.12)); }
.statuskreis { border-radius: 999px; min-width: 76px; min-height: 76px; color: white; }
.statuskreis.an { background-image: linear-gradient(135deg, #30d158, #00b7c3); }
.statuskreis.pause { background-image: linear-gradient(135deg, #ffb340, #ff7a00); }
.statuskreis.neu { background-image: linear-gradient(135deg, #0a84ff, #8e5cf7); }
.statuskreis.fehlt { background-image: linear-gradient(135deg, #ff6a5f, #ff2d55); }
.held-titel { font-size: 20pt; font-weight: 800; }

/* Kacheln */
.kachel { border-radius: 18px; padding: 14px 16px; }
.aktionskachel { border-radius: 18px; padding: 14px 16px; }
.kennzahl { border-radius: 16px; padding: 10px 16px; }
.kennzahl-wert { font-size: 19pt; font-weight: 800; font-feature-settings: "tnum"; }
.kacheltitel { font-weight: 700; }
.kacheltitel-klein { font-weight: 600; }
.kacheltext { font-size: 9.5pt; opacity: 0.72; }
.kacheltext.warnung { opacity: 1; }
.abschnitt { font-size: 12.5pt; font-weight: 800; margin-top: 10px; }
.abschnitt-text { font-size: 9.5pt; opacity: 0.72; }
.unterzeile, .hinweiszeile { border-top: 1px solid alpha(currentColor, 0.10); padding-top: 10px; }
.symbolkachel { border-radius: 10px; min-width: 34px; min-height: 34px; color: white; }
.symbolzeichen { font-size: 15pt; color: white; }
.farbe-gruen { background-image: linear-gradient(180deg, #3ddc6a, #1fb54c); }
.farbe-blau { background-image: linear-gradient(180deg, #3a9bff, #0a6cff); }
.farbe-indigo { background-image: linear-gradient(180deg, #7f7cff, #5150e6); }
.farbe-orange { background-image: linear-gradient(180deg, #ffb340, #ff8400); }
.farbe-gelb { background-image: linear-gradient(180deg, #ffd23f, #ffad0a); }
.farbe-rot { background-image: linear-gradient(180deg, #ff6a5f, #ff3b30); }
.farbe-teal { background-image: linear-gradient(180deg, #4fd8e8, #12acc8); }
.farbe-pink { background-image: linear-gradient(180deg, #ff6b9a, #ff2d6f); }
.farbe-lila { background-image: linear-gradient(180deg, #cf7bff, #a64bf0); }
.farbe-grau { background-image: linear-gradient(180deg, #a8a8b0, #82828c); }
.punkt { min-width: 9px; min-height: 9px; border-radius: 99px; }
.punkt.gut { background-color: #30d158; }
.punkt.sudo { background-color: #7f7cff; }
.punkt.nein { background-color: #ff9f0a; }

/* Kameraablaeufe */
.schrittnummer { border-radius: 999px; min-width: 24px; min-height: 24px; font-weight: 800;
                 font-size: 9.5pt; color: white;
                 background-image: linear-gradient(180deg, #3a9bff, #0a6cff); }
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


GRUENDE = {
    "ok": _("face recognized well"),
    "kein_gesicht": _("no face in the picture"),
    "zu_klein": _("too far away"),
    "gedreht": _("head turned too far to the side"),
    "geneigt": _("head tilted too much"),
    "unsicher": _("face not clearly recognized"),
    "punkte_unsicher": _("face partly covered"),
    "ueberbelichtet": _("overexposed, a little too close to the camera"),
    "keine_punkte": _("face incomplete"),
}


def komma(v, stellen=3):
    """Zahl mit festen Nachkommastellen, auf Deutsch mit Komma, sonst mit Punkt."""
    text = f"{v:.{stellen}f}"
    return text.replace(".", ",") if DEUTSCH else text


class Vorschau(Gtk.Box):
    def __init__(self, breite=640, hoehe=360):
        super().__init__(halign=Gtk.Align.START)
        css_laden()
        self.bild = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN)
        self.bild.set_size_request(breite, hoehe)
        overlay = Gtk.Overlay(child=self.bild)
        overlay.add_css_class("bildrahmen")
        self.label = Gtk.Label(label=_("Camera off"), halign=Gtk.Align.CENTER,
                               valign=Gtk.Align.CENTER)
        self.label.add_css_class("hinweis")
        overlay.add_overlay(self.label)
        self.append(overlay)
        self._bis_bild = False

    def zeige(self, w, h, daten):
        textur = Gdk.MemoryTexture.new(w, h, Gdk.MemoryFormat.R8G8B8, GLib.Bytes.new(daten), w * 3)
        self.bild.set_paintable(textur)
        # Vergleichswerte der (nur deutschen) Messwerkzeuge in werkzeuge/kalibrierung, nicht
        # übersetzen; die App nutzt bis_bild
        if self._bis_bild or self.label.get_label() in ("Kamera startet …",
                                                         "Kamera wird umgeschaltet …"):
            self.label.set_visible(False)
            self._bis_bild = False

    def hinweis(self, text, bis_bild=False):
        """bis_bild: verschwindet mit dem ersten Kamerabild (Countdown, Kamerastart)."""
        self.label.set_label(text)
        self.label.set_visible(True)
        self._bis_bild = bis_bild

    def leeren(self, text=None):
        self.bild.set_paintable(None)
        self.hinweis(_("Camera off") if text is None else text)


def live_text(st):
    """Kurzer Text aus einer STATUS-Zeile für die Anzeige unter dem Bild."""
    if st.get("fehler"):
        return st["fehler"], False
    teile = [GRUENDE.get(st.get("grund"), st.get("grund", ""))]
    if st.get("wert") is not None:
        teile.append(_("similarity {value}").format(value=komma(st["wert"])))
    if st.get("modus") == "einlernen":
        n = int(st.get("gesammelt", st.get("brauchbar", 0)) or 0)
        teile.append(ngettext("{n} image collected", "{n} images collected", n).format(n=n))
    elif st.get("modus") == "messen":
        teile.append(_("{usable} usable out of {lit}").format(
            usable=st.get("brauchbar", 0), lit=st.get("beleuchtet", 0)))
    return " · ".join(t for t in teile if t), st.get("grund") == "ok"
