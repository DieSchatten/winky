"""Übersetzungen über gettext (Domäne winky). Grundsprache Englisch, Deutsch in po/de.po."""

import gettext
import os
from pathlib import Path

_HIER = Path(__file__).resolve().parent
ORDNER = os.environ.get("WINKY_LOCALEDIR") or (
    "/usr/share/locale" if _HIER == Path("/usr/share/winky/app") else str(_HIER.parents[1] / "bau/locale"))
_uebersetzung = gettext.translation("winky", ORDNER, fallback=True)
_ = _uebersetzung.gettext
ngettext = _uebersetzung.ngettext
DEUTSCH = _uebersetzung.info().get("language", "").startswith("de")
