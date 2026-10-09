"""Umgebung des Kalibrierwerkzeugs (Entwicklung, nicht Teil des Pakets): misst als normaler
Benutzer mit dem Messwerkzeug aus /usr/libexec/winky oder dem Bau-Container des Projekts.
"""

import os
import shutil
from pathlib import Path

PROJEKT = Path(__file__).resolve().parents[2]
ATTRAPPE = os.environ.get("WINKY_ATTRAPPE") == "1"
MESSWERKZEUG = Path("/usr/libexec/winky/winky-messung")
MODELLE = Path("/usr/share/winky/models")
def _ir_kamera():
    """Infrarot-Kamera: WINKY_KAMERA oder die erste Kamera, deren Name „IR“ enthält
    (stabiler Pfad unter /dev/v4l/by-path)."""
    if os.environ.get("WINKY_KAMERA"):
        return os.environ["WINKY_KAMERA"]
    for pfad in sorted(Path("/dev/v4l/by-path").glob("*-video-index0")):
        name = Path("/sys/class/video4linux", os.path.basename(os.path.realpath(pfad)), "name")
        try:
            if "IR" in name.read_text().upper().replace(":", " ").split():
                return str(pfad)
        except OSError:
            continue
    return "/dev/video-ir-nicht-gefunden"


BYPATH = _ir_kamera()
ABBILD = "localhost/winky-bau:1"
APP = PROJEKT / "src" / "app"


def _daten_ordner():
    basis = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(basis) / "winky"


MESSUNGEN = Path(os.environ.get("WINKY_MESSUNGEN") or _daten_ordner() / "messungen").resolve()


def messwerkzeug_modus():
    if ATTRAPPE:
        return "attrappe"
    if MESSWERKZEUG.exists():
        return "system"
    if PROJEKT and (PROJEKT / "bau" / "winky-messung").exists() and shutil.which("podman"):
        return "container"
    return None


def messwerkzeug_befehl(args):
    modus = messwerkzeug_modus()
    if modus == "attrappe":
        return ["python3", str(PROJEKT / "werkzeuge" / "test" / "attrappe.py"), *args]
    if modus == "system":
        return [str(MESSWERKZEUG), *args, "--geraet", BYPATH, "--modelle", str(MODELLE),
                "--vorschau"]
    if modus == "container":
        ir = os.path.realpath(BYPATH)
        MESSUNGEN.mkdir(mode=0o700, parents=True, exist_ok=True)
        return ["podman", "run", "--rm", "--init", "--network=none",
                "--device", f"{ir}:/dev/video-ir",
                "-v", f"{PROJEKT}:/src:Z", "-v", f"{MESSUNGEN}:/messungen:Z",
                "-v", "/etc/localtime:/etc/localtime:ro", "-w", "/src", ABBILD,
                "bau/winky-messung", *args, "--geraet", "/dev/video-ir",
                "--modelle", "vendor", "--vorschau"]
    raise RuntimeError("Messwerkzeug nicht gefunden. Bitte das Paket installieren.")


def werkzeug_pfad(p: Path) -> str:
    """Pfad, wie ihn das Messwerkzeug sieht (im Container anders gemountet)."""
    if messwerkzeug_modus() == "container":
        return "/messungen/" + str(p.relative_to(MESSUNGEN))
    return str(p)


def kamera_vorhanden():
    return ATTRAPPE or os.path.exists(BYPATH)
