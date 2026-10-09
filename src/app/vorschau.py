"""Kamerabild mit Hinweistext darüber (nur Anzeige, nichts wird gespeichert)."""

from gi.repository import Gdk, GLib, Gtk

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
    # Nur im Testweg über GTK-Broadway fehlt die Schrift-DPI; libadwaita rechnet
    # Seitenbreiten damit um und würde sonst alles sehr schmal darstellen.
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
    "ok": "Gesicht gut erkannt",
    "kein_gesicht": "kein Gesicht im Bild",
    "zu_klein": "zu weit weg",
    "gedreht": "Kopf zu stark zur Seite gedreht",
    "geneigt": "Kopf zu schräg",
    "unsicher": "Gesicht unsicher erkannt",
    "punkte_unsicher": "Gesicht teilweise verdeckt",
    "ueberbelichtet": "überbelichtet, etwas zu nah an der Kamera",
    "keine_punkte": "Gesicht unvollständig",
}


def komma(v, stellen=3):
    return f"{v:.{stellen}f}".replace(".", ",")


class Vorschau(Gtk.Box):
    def __init__(self, breite=640, hoehe=360):
        super().__init__(halign=Gtk.Align.START)
        css_laden()
        self.bild = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN)
        self.bild.set_size_request(breite, hoehe)
        overlay = Gtk.Overlay(child=self.bild)
        overlay.add_css_class("bildrahmen")
        self.label = Gtk.Label(label="Kamera aus", halign=Gtk.Align.CENTER,
                               valign=Gtk.Align.CENTER)
        self.label.add_css_class("hinweis")
        overlay.add_overlay(self.label)
        self.append(overlay)
        self._bis_bild = False

    def zeige(self, w, h, daten):
        textur = Gdk.MemoryTexture.new(w, h, Gdk.MemoryFormat.R8G8B8, GLib.Bytes.new(daten), w * 3)
        self.bild.set_paintable(textur)
        if self._bis_bild or self.label.get_label() in ("Kamera startet …",
                                                         "Kamera wird umgeschaltet …"):
            self.label.set_visible(False)
            self._bis_bild = False

    def hinweis(self, text, bis_bild=False):
        """bis_bild: verschwindet mit dem ersten Kamerabild (Countdown, Kamerastart)."""
        self.label.set_label(text)
        self.label.set_visible(True)
        self._bis_bild = bis_bild

    def leeren(self, text="Kamera aus"):
        self.bild.set_paintable(None)
        self.hinweis(text)


def live_text(st):
    """Kurzer Text aus einer STATUS-Zeile für die Anzeige unter dem Bild."""
    if st.get("fehler"):
        return st["fehler"], False
    teile = [GRUENDE.get(st.get("grund"), st.get("grund", ""))]
    if st.get("wert") is not None:
        teile.append(f"Ähnlichkeit {komma(st['wert'])}")
    if st.get("modus") == "einlernen":
        teile.append(f"{st.get('gesammelt', st.get('brauchbar', 0))} Bilder gesammelt")
    elif st.get("modus") == "messen":
        teile.append(f"{st.get('brauchbar', 0)} brauchbar von {st.get('beleuchtet', 0)}")
    return " · ".join(t for t in teile if t), st.get("grund") == "ok"
