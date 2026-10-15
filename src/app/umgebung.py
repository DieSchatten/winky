"""Pfade und Betriebsart der App; installiert unter /usr/share/winky/app mit Programmen aus
/usr/libexec/winky. Tests ohne Kamera und root: WINKY_ATTRAPPE=1 (Attrappe des
Verwaltungshelfers), WINKY_TESTWURZEL=Ordner (statt / für Systemdateien).
"""

import json
import os
import subprocess
from pathlib import Path

from sprache import _

APP = Path(__file__).resolve().parent
INSTALLIERT = APP == Path("/usr/share/winky/app")
PROJEKT = None if INSTALLIERT else APP.parent.parent
ATTRAPPE = os.environ.get("WINKY_ATTRAPPE") == "1"

LIBEXEC = Path("/usr/libexec/winky")
VERWALTEN = LIBEXEC / "winky-verwalten"   # Systemeinstellungen, Administratorpasswort
GESICHT = LIBEXEC / "winky-gesicht"       # eigenes Gesicht, eigenes Passwort
WURZEL = Path(os.environ.get("WINKY_TESTWURZEL", "/")) if ATTRAPPE else Path("/")


def systempfad(pfad: str) -> Path:
    """Systemdatei, im Test unter WINKY_TESTWURZEL."""
    return WURZEL / pfad.lstrip("/")


def paket_installiert():
    if ATTRAPPE:
        return systempfad("/usr/libexec/winky/winky-matcher").exists()
    return (LIBEXEC / "winky-matcher").exists() and VERWALTEN.exists()


def version():
    try:
        return json.loads(Path("/usr/share/winky/version.json").read_text())
    except (FileNotFoundError, ValueError):
        pass
    if PROJEKT and (PROJEKT / ".git").exists():
        r = subprocess.run(["git", "-C", str(PROJEKT), "log", "-1", "--format=%h %ci"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            commit, datum = r.stdout.strip().split(" ", 1)
            return {"version": _("development"), "commit": commit, "gebaut": datum[:16]}
    return {"version": _("unknown"), "commit": "", "gebaut": ""}


def verwalten_befehl(args, admin=False):
    """Eigenes Gesicht: winky-gesicht (eigenes Passwort).
    Systemeinstellungen: winky-verwalten (Administratorpasswort)."""
    if ATTRAPPE:
        return ["python3", str(APP.parent.parent / "tests" / "app" / "attrappe_verwalten.py"),
                "--rolle", "verwalten" if admin else "gesicht", *args]
    return ["pkexec", str(VERWALTEN if admin else GESICHT), *args]
