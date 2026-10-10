"""Systemzustand (ohne root) und Verlauf aus dem Journal nur lesen; Änderungen laufen
ausschließlich über den Verwaltungshelfer mit Passwortabfrage (umgebung.verwalten_befehl).
"""

import json
import os
import re
import subprocess
from dataclasses import dataclass

import umgebung
from sprache import _


@dataclass
class Zustand:
    installiert: bool = False
    dienst: bool = False
    aktiv: bool = False
    pausiert: bool = False
    eingelernt: bool = False
    vorlagen: int = 0
    eingelernt_am: int = 0
    schwelle: float = 0.0
    kamera: str = ""
    blinkpruefung: bool = True
    test_ok: int = 0
    test_wert: float = 0.0
    gegenprobe_wert: float = None
    keepassxc: bool = False
    keepassxc_geste: bool = True  # KeePassXC nur mit Gesicht und ✌
    sudo: bool = False        # sudo mit Gesicht und ✌ eingeschaltet (systemweit)
    geste_ok: int = 0         # eigener ✌-Test bestanden (Zeitpunkt)
    freigaben: tuple = ()     # Administrator-Dialoge mit Gesicht und ✌ (Gruppen)
    anmeldung: bool = False   # auch die erste Anmeldung nach dem Start per Gesicht
    geste_zeit: int = 8       # Wartezeit auf das ✌ in Sekunden


def _konfig(text, schluessel):
    for zeile in text.splitlines():
        zeile = zeile.split("#", 1)[0].strip()
        if "=" in zeile:
            k, v = (t.strip() for t in zeile.split("=", 1))
            if k == schluessel:
                return v
    return None


def lese_zustand(uid=None) -> Zustand:
    uid = os.getuid() if uid is None else uid
    w = umgebung.systempfad
    z = Zustand(installiert=umgebung.paket_installiert())
    try:
        status = json.loads(w(f"/var/lib/winky/status/{uid}.json").read_text())
    except (OSError, ValueError):
        status = {}
    z.eingelernt = bool(status.get("vorlagen"))
    z.vorlagen = int(status.get("vorlagen") or 0)
    z.eingelernt_am = int(status.get("eingelernt") or 0)
    if z.eingelernt:
        z.test_ok = int(status.get("test_ok") or 0)
        z.test_wert = float(status.get("test_wert") or 0)
        if status.get("gegenprobe_wert") is not None:
            z.gegenprobe_wert = float(status["gegenprobe_wert"])
        z.geste_ok = int(status.get("geste_ok") or 0)
    try:
        text = w("/etc/winky/winky.conf").read_text()
        z.schwelle = float(_konfig(text, "schwelle") or 0)
        z.kamera = _konfig(text, "kamera") or ""
        z.blinkpruefung = (_konfig(text, "blinkpruefung") or "ja") != "nein"
        z.keepassxc = _konfig(text, "keepassxc") == "ja"
        z.keepassxc_geste = _konfig(text, "keepassxc_geste") != "nein"
        z.freigaben = tuple(g for g in (_konfig(text, "freigaben") or "").split(",") if g)
        z.geste_zeit = int(_konfig(text, "sudo_ms") or 8000) // 1000
    except (OSError, ValueError):
        pass
    try:
        with open(w("/etc/pam.d/common-auth"), encoding="utf-8") as f:
            z.aktiv = any("pam_winky.so" in zeile and not zeile.lstrip().startswith("#")
                          for zeile in f)
    except OSError:
        z.aktiv = False
    z.pausiert = w("/etc/winky/disabled").exists()
    z.sudo = w("/etc/winky/sudo-ein").exists()
    z.anmeldung = w("/etc/winky/anmeldung-ein").exists()
    if umgebung.ATTRAPPE:
        z.dienst = w("/run/winky.sock").exists()
    elif z.installiert:
        z.dienst = subprocess.run(["systemctl", "is-active", "--quiet", "winky.socket"]
                                  ).returncode == 0
    return z


_keepassxc_cache = {"zeit": 0.0, "wert": None}


def keepassxc_info():
    """Welche KeePassXC-Version gibt es, und hat sie die Polkit-Aktion zum
    Schnellentsperren angemeldet (erst ab 2.8, nur als normales Paket)?"""
    import time
    if umgebung.ATTRAPPE:
        try:
            return json.loads(umgebung.systempfad("/keepassxc.json").read_text())
        except (OSError, ValueError):
            return {"polkit_aktion": False, "gefunden": "Flatpak 2.7.12"}
    if time.monotonic() - _keepassxc_cache["zeit"] < 60 and _keepassxc_cache["wert"]:
        return _keepassxc_cache["wert"]
    info = {"polkit_aktion": False, "gefunden": None}
    try:
        info["polkit_aktion"] = subprocess.run(
            ["pkaction", "--action-id", "org.keepassxc.KeePassXC.unlockDatabase"],
            capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        pass
    gefunden = []
    try:
        r = subprocess.run(["dpkg-query", "-W", "-f=${Version}", "keepassxc"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            version = r.stdout.strip().split('+')[0].split('-')[0]
            gefunden.append(_("Package {version}").format(version=version))
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        r = subprocess.run(["flatpak", "info", "org.keepassxc.KeePassXC"],
                           capture_output=True, text=True, timeout=5)
        for zeile in r.stdout.splitlines():
            if zeile.strip().startswith("Version:"):
                gefunden.append(f"Flatpak {zeile.split(':', 1)[1].strip()}")
    except (OSError, subprocess.TimeoutExpired):
        pass
    info["gefunden"] = ", ".join(gefunden) or None
    _keepassxc_cache.update(zeit=time.monotonic(), wert=info)
    return info


def verlauf(anzahl=8, uid=None):
    """Letzte Entsperrversuche aus dem Journal (Liste von dicts, neueste zuerst);
    None, wenn das Journal nicht lesbar ist."""
    uid = os.getuid() if uid is None else uid
    if umgebung.ATTRAPPE:
        try:
            eintraege = json.loads(umgebung.systempfad("/verlauf.json").read_text())
        except (OSError, ValueError):
            eintraege = []
        return eintraege[:anzahl]
    try:
        r = subprocess.run(["journalctl", "-t", "winky", "-o", "json", "-n", "300",
                            "--no-pager", "-q"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    eintraege = []
    for zeile in r.stdout.splitlines():
        try:
            obj = json.loads(zeile)
        except ValueError:
            continue
        msg = obj.get("MESSAGE")
        if not isinstance(msg, str) or not msg.startswith("Ergebnis "):
            continue
        felder = dict(t.split("=", 1) for t in msg.split()[1:] if "=" in t)
        if felder.get("uid") != str(uid):
            continue
        try:
            zeit = int(obj.get("__REALTIME_TIMESTAMP", "0")) / 1e6
            wert = float(felder.get("wert", "-1"))
            dauer = float(felder.get("dauer_ms", "0"))
        except ValueError:
            continue
        befehl = ""
        m = re.search(r'befehl=("(?:[^"\\]|\\.)*")', msg)
        if m:
            try:
                befehl = json.loads(m.group(1))
            except ValueError:
                pass
        eintraege.append({"zeit": zeit, "status": felder.get("status", "?"), "wert": wert,
                          "dauer_ms": dauer, "grund": felder.get("grund", ""),
                          "zweck": felder.get("zweck", "sperrbildschirm"), "befehl": befehl})
    eintraege.reverse()
    return eintraege[:anzahl]


STATUS_TEXTE = {
    "treffer": _("unlocked with your face"),
    "kein_treffer": _("face not recognized, password needed"),
    "kein_gesicht": _("no face in front of the camera"),
    "nicht_eingerichtet": _("not set up"),
    "gesperrt": _("locked after failed attempts, password needed"),
    "abgelehnt": _("refused (no local session)"),
    "fehler": _("error, password needed"),
}
