"""Kamerabild mit Hinweistext darüber (nur Anzeige, nichts wird gespeichert)."""

from gi.repository import Gdk, GLib, Gtk

from sprache import DEUTSCH, _, ngettext

CSS = b"""
.hinweis { background-color: alpha(black, 0.6); color: white; padding: 14px 22px;
           border-radius: 14px; font-size: 22pt; font-weight: bold; }
.gut { color: @success_color; }
.warnung { color: @warning_color; }
.bildrahmen { background-color: black; border-radius: 12px; }
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
