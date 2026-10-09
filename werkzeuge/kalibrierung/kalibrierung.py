#!/usr/bin/env python3
"""Kalibrierwerkzeug (Entwicklung, nicht Teil des Pakets): Messreihen für die Vorgabe-Strenge
der App (SFace auf dem IR-Bild; bei anderem Modell oder anderer Kameraklasse neu messen) und
für das Handzeichen ✌.

Aufruf: ./scripts/kalibrierung.sh
"""

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio  # noqa: E402

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parents[1] / "src" / "app"))
import hand  # noqa: E402
import messung  # noqa: E402
from vorschau import css_laden  # noqa: E402


class Fenster(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Kalibrierung (Entwicklung)")
        self.set_default_size(1180, 860)
        css_laden()
        self.toasts = Adw.ToastOverlay()
        ansicht = Adw.ToolbarView()
        self.stapel = Adw.ViewStack()
        ansicht.add_top_bar(Adw.HeaderBar(title_widget=Adw.ViewSwitcher(
            stack=self.stapel, policy=Adw.ViewSwitcherPolicy.WIDE)))
        self.seite = messung.MessungSeite(self.melde, lambda: None)
        self.hand = hand.HandSeite(self.melde)
        self.stapel.add_titled_with_icon(self.seite, "erkennung", "Erkennung",
                                         "camera-web-symbolic")
        self.stapel.add_titled_with_icon(self.hand, "hand", "Handzeichen ✌", "emblem-ok-symbolic")
        ansicht.set_content(self.stapel)
        self.toasts.set_child(ansicht)
        self.set_content(self.toasts)
        self.connect("close-request", self._schliessen)

    def _schliessen(self, *_):
        self.seite.abbrechen()
        self.hand.abbrechen()
        return False

    def melde(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=4))


def main():
    app = Adw.Application(application_id="io.github.dieschatten.WinkyKalibrierung",
                          flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
    app.connect("activate", lambda a: (a.get_active_window() or Fenster(a)).present())
    return app.run(sys.argv[:1])


if __name__ == "__main__":
    sys.exit(main())
