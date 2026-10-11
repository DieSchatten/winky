"""Bausteine der Startseite: Kacheln mit Schalter, Aktionskacheln, Kennzahlen."""

from gi.repository import GObject, Gtk

FARBEN = ("gruen", "blau", "indigo", "orange", "gelb", "rot", "teal", "pink", "lila", "grau")


def symbol(name, farbe, groesse=18):
    """Farbiges Quadrat mit weißem Symbol; name ist ein Symbolname oder ein Zeichen wie ✌."""
    box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.START)
    box.add_css_class("symbolkachel")
    box.add_css_class(f"farbe-{farbe}")
    if name.endswith("-symbolic"):
        inhalt = Gtk.Image(icon_name=name, pixel_size=groesse, hexpand=True,
                           halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
    else:
        inhalt = Gtk.Label(label=name, hexpand=True, halign=Gtk.Align.CENTER,
                           valign=Gtk.Align.CENTER)
        inhalt.add_css_class("symbolzeichen")
    box.append(inhalt)
    box.set_hexpand(False)   # das zentrierte Innere soll das Quadrat nicht strecken
    return box


def _info_knopf(text):
    """ⓘ mit dem ausführlichen Hinweis; bleibt auch bei gesperrtem Schalter lesbar."""
    label = Gtk.Label(label=text, wrap=True, max_width_chars=44, xalign=0, selectable=True,
                      margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
    knopf = Gtk.MenuButton(icon_name="dialog-information-symbolic", valign=Gtk.Align.START,
                           popover=Gtk.Popover(child=label))
    knopf.add_css_class("flat")
    knopf.add_css_class("circular")
    knopf.set_tooltip_text(text)
    return knopf


class SchalterKachel(Gtk.Box):
    """Kachel mit Symbol, Titel, Untertitel, optionalem ⓘ und Schalter. Verhält sich nach außen
    wie Adw.SwitchRow (active, notify::active, get/set_title, get/set_subtitle); gesperrt wird
    nur der Schalter, damit der Hinweis lesbar bleibt."""

    __gtype_name__ = "WinkySchalterKachel"
    active = GObject.Property(type=bool, default=False)

    def __init__(self, titel, untertitel="", name="emblem-ok-symbolic", farbe="blau", info=None,
                 warnung=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("card")
        self.add_css_class("kachel")
        kopf = Gtk.Box(spacing=12)
        kopf.append(symbol(name, farbe))
        texte = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        self._titel = Gtk.Label(label=titel, xalign=0, wrap=True)
        self._titel.add_css_class("kacheltitel")
        self._untertitel = Gtk.Label(label=untertitel, xalign=0, wrap=True)
        self._untertitel.add_css_class("kacheltext")
        if warnung:
            self._untertitel.add_css_class("warnung")
        texte.append(self._titel)
        texte.append(self._untertitel)
        kopf.append(texte)
        if info:
            kopf.append(_info_knopf(info))
        self.schalter = Gtk.Switch(valign=Gtk.Align.START)
        self.bind_property("active", self.schalter, "active",
                           GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        kopf.append(self.schalter)
        self.append(kopf)
        # Platz für Zusätze (Knopf „Einrichten“, Unterschalter, Hinweis)
        self.zusatz = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, visible=False)
        self.append(self.zusatz)

    def zusatz_anhaengen(self, widget):
        self.zusatz.append(widget)
        self.zusatz.set_visible(True)

    def get_active(self):
        return self.active

    def set_active(self, wert):
        self.active = bool(wert)

    def get_title(self):
        return self._titel.get_label()

    def set_title(self, text):
        self._titel.set_label(text)

    def get_subtitle(self):
        return self._untertitel.get_label()

    def set_subtitle(self, text):
        self._untertitel.set_label(text)
        self._untertitel.set_visible(bool(text))

    def set_sensitive(self, wert):
        self.schalter.set_sensitive(wert)
        self._titel.set_opacity(1.0 if wert or self.active else 0.55)

    def get_sensitive(self):
        return self.schalter.get_sensitive()


class KleinSchalter(Gtk.Box):
    """Unterschalter innerhalb einer Kachel (z. B. „KeePassXC nur mit ✌“)."""

    __gtype_name__ = "WinkyKleinSchalter"
    active = GObject.Property(type=bool, default=False)

    def __init__(self, titel, untertitel=""):
        super().__init__(spacing=12)
        self.add_css_class("unterzeile")
        texte = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        self._titel = Gtk.Label(label=titel, xalign=0, wrap=True)
        self._titel.add_css_class("kacheltitel-klein")
        self._untertitel = Gtk.Label(label=untertitel, xalign=0, wrap=True,
                                     visible=bool(untertitel))
        self._untertitel.add_css_class("kacheltext")
        texte.append(self._titel)
        texte.append(self._untertitel)
        self.append(texte)
        self.schalter = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.bind_property("active", self.schalter, "active",
                           GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        self.append(self.schalter)

    def get_active(self):
        return self.active

    def set_active(self, wert):
        self.active = bool(wert)

    def get_title(self):
        return self._titel.get_label()

    def get_subtitle(self):
        return self._untertitel.get_label()

    def set_sensitive(self, wert):
        self.schalter.set_sensitive(wert)

    def get_sensitive(self):
        return self.schalter.get_sensitive()


class Hinweiszeile(Gtk.Box):
    """Deutlicher Hinweis innerhalb einer Kachel (Titel fett, Untertitel)."""

    def __init__(self, titel, untertitel=""):
        super().__init__(spacing=10)
        self.add_css_class("hinweiszeile")
        bild = Gtk.Image(icon_name="dialog-warning-symbolic", valign=Gtk.Align.START)
        bild.add_css_class("warning")
        self.append(bild)
        texte = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        self._titel = Gtk.Label(label=titel, xalign=0, wrap=True)
        self._titel.add_css_class("kacheltitel-klein")
        self._untertitel = Gtk.Label(label=untertitel, xalign=0, wrap=True, selectable=True)
        self._untertitel.add_css_class("kacheltext")
        texte.append(self._titel)
        texte.append(self._untertitel)
        self.append(texte)

    def get_title(self):
        return self._titel.get_label()

    def get_subtitle(self):
        return self._untertitel.get_label()

    def set_subtitle(self, text):
        self._untertitel.set_label(text)


class AktionsKachel(Gtk.Button):
    """Anklickbare Kachel mit Symbol, Titel und erklärendem Text."""

    def __init__(self, titel, untertitel, name, farbe, aktion):
        super().__init__()
        self.add_css_class("card")
        self.add_css_class("aktionskachel")
        box = Gtk.Box(spacing=12)
        box.append(symbol(name, farbe))
        texte = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        self._titel = Gtk.Label(label=titel, xalign=0, wrap=True)
        self._titel.add_css_class("kacheltitel")
        self._untertitel = Gtk.Label(label=untertitel, xalign=0, wrap=True)
        self._untertitel.add_css_class("kacheltext")
        texte.append(self._titel)
        texte.append(self._untertitel)
        box.append(texte)
        pfeil = Gtk.Image(icon_name="go-next-symbolic", valign=Gtk.Align.CENTER)
        pfeil.add_css_class("dim-label")
        box.append(pfeil)
        self.set_child(box)
        self.connect("clicked", lambda *_: aktion())

    def get_title(self):
        return self._titel.get_label()

    def get_subtitle(self):
        return self._untertitel.get_label()

    def set_subtitle(self, text):
        self._untertitel.set_label(text)


class Kennzahl(Gtk.Box):
    """Kleine Kennzahl: Beschriftung oben, Wert groß."""

    def __init__(self, beschriftung):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        self.add_css_class("card")
        self.add_css_class("kennzahl")
        oben = Gtk.Label(label=beschriftung, xalign=0)
        oben.add_css_class("kacheltext")
        self.wert = Gtk.Label(label="–", xalign=0)
        self.wert.add_css_class("kennzahl-wert")
        self.append(oben)
        self.append(self.wert)

    def setze(self, text):
        self.wert.set_label(text)


def raster(kacheln, spalten=2):
    """Sichtbare Kacheln in ein Raster ordnen (versteckte belegen keinen Platz)."""
    gitter = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
    gitter.kacheln = list(kacheln)
    gitter.spalten = spalten
    raster_ordnen(gitter)
    return gitter


def raster_ordnen(gitter):
    while (kind := gitter.get_first_child()) is not None:
        gitter.remove(kind)
    sichtbar = [k for k in gitter.kacheln if k.get_visible()]
    for i, k in enumerate(sichtbar):
        # Eine einzelne letzte Kachel geht über die ganze Breite
        breite = gitter.spalten if i == len(sichtbar) - 1 and i % gitter.spalten == 0 else 1
        gitter.attach(k, i % gitter.spalten, i // gitter.spalten, breite, 1)
