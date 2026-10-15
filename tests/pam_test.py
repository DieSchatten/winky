#!/usr/bin/env python3
"""Test des PAM-Moduls mit echtem libpam, pamtester und nachgebautem Prüfdienst. Nur im
Wegwerf-Container als (Namensraum-)root, weil er /etc/pam.d, /run/winky.sock und
/etc/winky/disabled anlegt.
"""

import os
import socket
import struct
import subprocess
import sys
import threading
import time

MODUL = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "bau/pam_winky.so")
SOCKET = "/run/winky.sock"
MAGIC = 0x314B4E57
TREFFER, KEIN_TREFFER, OK = 0, 1, 7
FEHLER = []


def pruefe(bed, text):
    print(("ok    " if bed else "FEHLER") + "  " + text)
    if not bed:
        FEHLER.append(text)


class Attrappe:
    """Antwortet je nach Modus: treffer, kein, haengt, muell, schliesst; für sudo (Operation 7)
    geste-treffer, geste-kein, geste-ablehnen, geste-haengt. Merkt sich die Zusatznachricht."""

    def __init__(self):
        self.modus = "treffer"
        self.anfragen = []
        self.zusatz = []
        if os.path.exists(SOCKET):
            os.unlink(SOCKET)
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.s.bind(SOCKET)
        os.chmod(SOCKET, 0o600)
        self.s.listen(8)
        threading.Thread(target=self._schleife, daemon=True).start()

    def _schleife(self):
        while True:
            c, _ = self.s.accept()
            threading.Thread(target=self._verbindung, args=(c,), daemon=True).start()

    def _verbindung(self, c):
        with c:
            daten = c.recv(64)
            if len(daten) != 16:
                return
            magic, op, uid, _ = struct.unpack("IIII", daten)
            self.anfragen.append((op, uid))
            # sudo (mit Terminal und Befehl), Administrator-Dialog, Entsperren/Anmelden mit ✌
            if op in (7, 9, 12, 13):
                if op == 7:
                    c.settimeout(1)
                    try:
                        self.zusatz.append(c.recv(1024))
                    except OSError:
                        self.zusatz.append(b"")
                antwort = {"geste-treffer": TREFFER, "geste-kein": KEIN_TREFFER}
                if self.modus in ("geste-ablehnen", "geste-gesperrt"):
                    status = 6 if self.modus == "geste-ablehnen" else 4
                    c.send(struct.pack("IIfI", MAGIC, status, -1.0, 1))
                    return
                c.send(b"W")
                if self.modus == "geste-haengt":
                    time.sleep(8)
                    return
                time.sleep(0.3)
                c.send(struct.pack("IIfI", MAGIC, antwort.get(self.modus, KEIN_TREFFER), 0.9, 1500))
                return
            if op == 2:
                c.send(struct.pack("IIfI", MAGIC, OK, -1.0, 1))
                return
            if self.modus == "haengt":
                time.sleep(5)
            elif self.modus == "muell":
                c.send(b"\x00" * 7)
            elif self.modus == "schliesst":
                return
            elif self.modus == "treffer":
                c.send(struct.pack("IIfI", MAGIC, TREFFER, 0.91, 400))
            else:
                c.send(struct.pack("IIfI", MAGIC, KEIN_TREFFER, 0.31, 2600))


def dienst(name, zeilen):
    with open(f"/etc/pam.d/{name}", "w") as f:
        f.write("\n".join(zeilen) + "\n")


def pam(dienstname, user="ubuntu", ops=("authenticate",), env=None, items=()):
    e = dict(os.environ)
    e.pop("GDM_SESSION_FOR_REAUTH", None)
    e.update(env or {})
    args = ["pamtester"] + [f"-I{i}" for i in items] + [dienstname, user, *ops]
    t0 = time.monotonic()
    r = subprocess.run(args, env=e, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    pam.ausgabe = r.stdout + r.stderr
    return r.returncode == 0, time.monotonic() - t0


def main():
    # Im Ubuntu-Abbild hat der Benutzer "ubuntu" die uid 1000
    os.makedirs("/etc/winky", exist_ok=True)
    modul = f"{MODUL}"
    # Nur das Gesicht kann hier zum Erfolg führen (danach pam_deny)
    dienst("winky-test", [
        f"auth [success=done default=ignore] {modul} services=winky-test,gdm-password timeout_ms=1500",
        "auth requisite pam_deny.so"])
    # Wie auf dem echten System: Gesicht, sonst "Passwort" (hier pam_permit)
    dienst("gdm-password", [
        f"auth [success=done default=ignore] {modul} services=gdm-password timeout_ms=1500",
        "auth required pam_permit.so"])
    dienst("gdm-nurgesicht", [
        f"auth [success=done default=ignore] {modul} services=gdm-nurgesicht timeout_ms=1500",
        "auth requisite pam_deny.so"])
    for name in ("sudo", "login", "su", "polkit-1"):
        dienst(name, [
            f"auth [success=done default=ignore] {modul} services=gdm-password timeout_ms=1500",
            "auth requisite pam_deny.so"])
    dienst("falsches-argument", [
        f"auth [success=done default=ignore] {modul} services=falsches-argument debug",
        "auth requisite pam_deny.so"])

    a = Attrappe()
    reauth = {"GDM_SESSION_FOR_REAUTH": "1"}

    a.modus = "treffer"
    ok, _ = pam("winky-test")
    pruefe(ok, "Treffer des Prüfdienstes entsperrt (Testdienst)")
    pruefe(a.anfragen[-1] == (1, 1000), "Anfrage enthält Operation AUTH und die richtige uid")

    a.modus = "kein"
    ok, _ = pam("winky-test")
    pruefe(not ok, "kein Treffer: Modul gibt auf, Passwort wäre dran")

    for modus in ("haengt", "muell", "schliesst"):
        a.modus = modus
        ok, dauer = pam("winky-test")
        pruefe(not ok and dauer < 1.5 + 0.4, f"Prüfdienst {modus}: kein Erfolg, fertig nach {dauer:.2f} s")

    a.modus = "treffer"
    vorher = len(a.anfragen)
    for name in ("sudo", "login", "su", "polkit-1"):
        ok, _ = pam(name, env=reauth)
        pruefe(not ok, f"Dienst {name} nutzt das Gesicht nicht")
    pruefe(len(a.anfragen) == vorher, "keine einzige Verbindung für sudo, login, su, polkit-1")

    ok, _ = pam("gdm-nurgesicht")
    pruefe(not ok and len(a.anfragen) == vorher,
           "ohne GDM-Wiederanmeldung (Erstanmeldung) kein Gesicht und keine Verbindung")
    ok, _ = pam("gdm-nurgesicht", env=reauth)
    pruefe(ok, "Sperrbildschirm (GDM_SESSION_FOR_REAUTH=1) entsperrt per Gesicht")

    # Erste Anmeldung nach dem Start: nur mit eigenem Schalter und nur für gdm-password
    vorher = len(a.anfragen)
    ok, _ = pam("gdm-password")
    pruefe(len(a.anfragen) == vorher, "Erstanmeldung ohne Schalter: keine Verbindung")
    with open("/etc/winky/anmeldung-ein", "w") as f:
        f.write("an\n")
    os.chmod("/etc/winky/anmeldung-ein", 0o644)
    ok, _ = pam("gdm-nurgesicht")
    pruefe(len(a.anfragen) == vorher, "Schalter gilt nur für gdm-password")
    ok, _ = pam("gdm-password")
    pruefe(ok and a.anfragen[-1] == (10, 1000), "Erstanmeldung mit Schalter: Operation ANMELDUNG")
    pruefe("look at the camera" in pam.ausgabe and "recognized, logging in" in pam.ausgabe,
           "Anmeldemaske zeigt, was passiert")
    a.modus = "kein"
    pam("gdm-password")
    pruefe("not recognized, please enter your password" in pam.ausgabe,
           "nicht erkannt: Hinweis aufs Passwort")
    a.modus = "treffer"
    # Schlüsselbund: nach erkannter Erstanmeldung Passwort vom Schlüsselbund-Dienst als AUTHTOK
    schluessel = []

    def schluessel_dienst(s):
        while True:
            c, _ = s.accept()
            with c:
                daten = c.recv(64)
                schluessel.append(struct.unpack("IIII", daten)[1:3] if len(daten) == 16 else None)
                c.send(b"Kgeheim")
    if os.path.exists("/run/winky-schluessel.sock"):
        os.unlink("/run/winky-schluessel.sock")
    ss = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    ss.bind("/run/winky-schluessel.sock")
    ss.listen(4)
    threading.Thread(target=schluessel_dienst, args=(ss,), daemon=True).start()
    with open("/root/authtok.sh", "w") as f:
        f.write("#!/bin/sh\ncat > /root/authtok.txt\n")
    os.chmod("/root/authtok.sh", 0o755)
    dienst("gdm-password", [
        f"auth [success=ok default=ignore] {modul} services=gdm-password timeout_ms=1500",
        "auth optional pam_exec.so expose_authtok quiet /root/authtok.sh"])
    for alt_datei in ("/root/authtok.txt",):
        if os.path.exists(alt_datei):
            os.unlink(alt_datei)
    ok, _ = pam("gdm-password")
    pruefe(not schluessel, "ohne versiegeltes Passwort kein Kontakt zum Schlüsselbund-Dienst")
    os.makedirs("/var/lib/winky/1000", exist_ok=True)
    open("/var/lib/winky/1000/schluesselbund.cred", "w").close()
    ok, _ = pam("gdm-password")
    pruefe(schluessel and schluessel[-1] == (11, 1000), "Erstanmeldung holt das Schlüsselbund-Passwort")
    try:
        with open("/root/authtok.txt") as f:
            uebergeben = f.read().rstrip("\0\n")
    except OSError:
        uebergeben = ""
    pruefe(uebergeben == "geheim", "Passwort kommt als AUTHTOK beim nächsten Modul an (Schlüsselbund)")
    a.modus = "kein"
    vorher = len(schluessel)
    pam("gdm-password")
    pruefe(len(schluessel) == vorher, "ohne erkanntes Gesicht kein Kontakt zum Schlüsselbund-Dienst")
    a.modus = "treffer"
    os.unlink("/var/lib/winky/1000/schluesselbund.cred")
    dienst("gdm-password", [
        f"auth [success=done default=ignore] {modul} services=gdm-password timeout_ms=1500",
        "auth required pam_permit.so"])

    os.chmod("/etc/winky/anmeldung-ein", 0o666)
    vorher = len(a.anfragen)
    ok, _ = pam("gdm-password")
    pruefe(len(a.anfragen) == vorher, "für alle beschreibbarer Schalter wird ignoriert")
    os.unlink("/etc/winky/anmeldung-ein")

    vorher = len(a.anfragen)
    ok, _ = pam("gdm-nurgesicht", env=reauth, items=("rhost=192.168.1.5",))
    pruefe(not ok and len(a.anfragen) == vorher, "entfernter Rechner (PAM_RHOST) wird ignoriert")
    ok, _ = pam("gdm-nurgesicht", user="root", env=reauth)
    pruefe(not ok and len(a.anfragen) == vorher, "root wird nie per Gesicht angemeldet")
    ok, _ = pam("falsches-argument", env=reauth)
    pruefe(not ok and len(a.anfragen) == vorher, "unbekanntes Modulargument schaltet das Modul ab")

    open("/etc/winky/disabled", "w").close()
    ok, _ = pam("gdm-nurgesicht", env=reauth)
    pruefe(not ok and len(a.anfragen) == vorher, "Notschalter /etc/winky/disabled wirkt")
    os.unlink("/etc/winky/disabled")

    # Passwort-Erfolg setzt den Fehlversuchszähler zurück, Gesicht-Erfolg nicht
    a.modus = "kein"
    vorher = len(a.anfragen)
    ok, _ = pam("gdm-password", ops=("authenticate", "setcred"), env=reauth)
    neue = a.anfragen[vorher:]
    pruefe(ok and (2, 1000) in neue, "nach Passwort-Erfolg wird der Zähler zurückgesetzt")
    a.modus = "treffer"
    vorher = len(a.anfragen)
    ok, _ = pam("gdm-password", ops=("authenticate", "setcred"), env=reauth)
    neue = a.anfragen[vorher:]
    pruefe(ok and (2, 1000) not in neue, "nach Gesicht-Erfolg kein zusätzliches Zurücksetzen")

    # Ohne Prüfdienst: sofort weiter zum Passwort
    os.unlink(SOCKET)
    ok, dauer = pam("gdm-password", env=reauth)
    pruefe(ok and dauer < 0.5, f"ohne Prüfdienst sofort weiter zum Passwort ({dauer:.2f} s)")
    ok, dauer = pam("gdm-nurgesicht", env=reauth)
    pruefe(not ok, "ohne Prüfdienst kein Erfolg per Gesicht")

    # sudo mit ✌
    a = Attrappe()
    geste = (f"auth [success=done default=ignore] {modul} services=winky-test-geste,gdm-password "
             f"geste=winky-test-geste timeout_ms=1500 geste_timeout_ms=3000")
    dienst("winky-test-geste", [geste, "auth requisite pam_deny.so"])
    tty = ("tty=/dev/pts/7",)
    schalter = "/etc/winky/sudo-ein"
    if os.path.exists(schalter):
        os.unlink(schalter)
    a.modus = "geste-treffer"
    vorher = len(a.anfragen)
    ok, _ = pam("winky-test-geste", items=tty)
    pruefe(not ok and len(a.anfragen) == vorher, "sudo-Gestenweg ohne Schalter: keine Verbindung")
    with open(schalter, "w") as f:
        f.write("an\n")
    os.chmod(schalter, 0o644)
    ok, _ = pam("winky-test-geste", items=tty)
    pruefe(ok and a.anfragen[-1] == (7, 1000), "Gesicht und ✌ bestätigt sudo (Operation SUDO, uid 1000)")
    z = a.zusatz[-1]
    pruefe(z.startswith(b"C/dev/pts/7\x00") and b"pamtester" in z and z.endswith(b"\x00"),
           "Terminal und Befehlszeile werden mitgeschickt")
    pruefe("to the camera" in pam.ausgabe and "\u2713 confirmed" in pam.ausgabe,
           "Aufforderung und Bestätigung erscheinen im Terminal (Englisch)")
    ok, _ = pam("winky-test-geste", items=tty, env={"LANG": "de_DE.UTF-8"})
    pruefe(ok and "Kamera zeigen" in pam.ausgabe and "\u2713 bestätigt" in pam.ausgabe,
           "mit deutscher Systemsprache auf Deutsch")
    a.modus = "geste-kein"
    ok, _ = pam("winky-test-geste", items=tty)
    pruefe(not ok and "not confirmed" in pam.ausgabe, "ohne ✌: nicht bestätigt, weiter mit Passwort")
    pruefe("Enter without a password" in pam.ausgabe,
           "verpasstes ✌: Hinweis, dass Enter ohne Passwort es noch einmal versucht")
    a.modus = "geste-gesperrt"
    ok, _ = pam("winky-test-geste", items=tty)
    pruefe(not ok and "temporarily locked" in pam.ausgabe and "to the camera" not in pam.ausgabe,
           "gesperrt: klarer Hinweis statt Aufforderung")
    a.modus = "geste-ablehnen"
    ok, dauer = pam("winky-test-geste", items=tty)
    pruefe(not ok and "to the camera" not in pam.ausgabe and dauer < 1,
           "lehnt der Dienst ab, erscheint keine Aufforderung und es geht sofort weiter")
    a.modus = "geste-haengt"
    ok, dauer = pam("winky-test-geste", items=tty)
    pruefe(not ok and dauer < 3.0 + 0.5, f"hängt der Dienst, ist nach dem Zeitlimit Schluss ({dauer:.2f} s)")
    a.modus = "geste-treffer"
    vorher = len(a.anfragen)
    ok, _ = pam("winky-test-geste")
    pruefe(not ok and len(a.anfragen) == vorher, "ohne Terminal (PAM_TTY) kein Gestenweg")
    ok, _ = pam("winky-test-geste", items=("tty=:0",))
    pruefe(not ok and len(a.anfragen) == vorher, "Terminal außerhalb von /dev wird ignoriert")
    ok, _ = pam("winky-test-geste", items=tty + ("rhost=10.0.0.2",))
    pruefe(not ok and len(a.anfragen) == vorher, "entfernter Rechner (PAM_RHOST) wird ignoriert")
    os.chmod(schalter, 0o666)
    ok, _ = pam("winky-test-geste", items=tty)
    pruefe(not ok and len(a.anfragen) == vorher, "beschreibbarer Schalter zählt nicht")
    os.unlink(schalter)
    os.symlink("/etc/hostname", schalter)
    ok, _ = pam("winky-test-geste", items=tty)
    pruefe(not ok and len(a.anfragen) == vorher, "Schalter als Verknüpfung zählt nicht")
    os.unlink(schalter)
    with open(schalter, "w") as f:
        f.write("an\n")
    os.chmod(schalter, 0o644)
    open("/etc/winky/disabled", "w").close()
    ok, _ = pam("winky-test-geste", items=tty)
    pruefe(not ok and len(a.anfragen) == vorher, "Notschalter gilt auch für sudo")
    os.unlink("/etc/winky/disabled")
    # Ein Dienst, der nur in services steht (nicht in geste), bleibt beim Sperrbildschirm-Weg
    dienst("gdm-password", [geste.replace("services=winky-test-geste,gdm-password",
                                          "services=gdm-password,winky-test-geste"),
                            "auth requisite pam_deny.so"])
    ok, _ = pam("gdm-password", items=tty)
    pruefe(not ok and len(a.anfragen) == vorher, "gdm ohne Wiederanmeldung bleibt ohne Gesicht")
    dienst("winky-test-geste", [geste.replace("geste_timeout_ms=3000", "geste_timeout_ms=99000"),
                                "auth requisite pam_deny.so"])
    ok, _ = pam("winky-test-geste", items=tty)
    pruefe(not ok and len(a.anfragen) == vorher, "ungültiges geste_timeout_ms schaltet das Modul ab")
    os.unlink(schalter)

    # Administrator-Dialog (polkit-1): nur mit Schalter, kein Terminal nötig, ✌-Aufforderung im Dialog
    dienst("winky-test-dialog", [
        f"auth [success=done default=ignore] {modul} services=winky-test-dialog "
        f"geste=winky-test-dialog timeout_ms=1500 geste_timeout_ms=3000",
        "auth requisite pam_deny.so"])
    dialog_schalter = "/etc/winky/dialoge-ein"
    a.modus = "geste-treffer"
    vorher = len(a.anfragen)
    ok, _ = pam("winky-test-dialog")
    pruefe(not ok and len(a.anfragen) == vorher, "Administrator-Dialog ohne Schalter: keine Verbindung")
    with open(dialog_schalter, "w") as f:
        f.write("an\n")
    os.chmod(dialog_schalter, 0o644)
    ok, _ = pam("winky-test-dialog")
    pruefe(ok and a.anfragen[-1] == (9, 1000) and "to approve" in pam.ausgabe
           and "\u2713 approved" in pam.ausgabe, "Dialog: Gesicht und ✌ geben frei, Aufforderung im Dialog")
    a.modus = "geste-kein"
    ok, _ = pam("winky-test-dialog")
    pruefe(not ok and "not confirmed" in pam.ausgabe, "Dialog ohne ✌: weiter mit Passwort")
    open("/etc/winky/disabled", "w").close()
    vorher = len(a.anfragen)
    ok, _ = pam("winky-test-dialog")
    pruefe(not ok and len(a.anfragen) == vorher, "Pause gilt auch für Dialoge")
    os.unlink("/etc/winky/disabled")
    os.unlink(dialog_schalter)

    # Entsperren nur mit ✌: Sperrbildschirm und Erstanmeldung fragen den Gestenweg
    entsperren = "/etc/winky/entsperren-geste"
    dienst("gdm-nurgesicht", [
        f"auth [success=done default=ignore] {modul} services=gdm-nurgesicht timeout_ms=1500 "
        f"geste_timeout_ms=3000",
        "auth requisite pam_deny.so"])
    with open(entsperren, "w") as f:
        f.write("an\n")
    os.chmod(entsperren, 0o644)
    a.modus = "geste-treffer"
    ok, _ = pam("gdm-nurgesicht", env=reauth)
    pruefe(ok and a.anfragen[-1] == (12, 1000) and "to unlock" in pam.ausgabe,
           "nur mit ✌: Sperrbildschirm fragt Gesicht und ✌, Aufforderung erscheint")
    a.modus = "geste-kein"
    ok, _ = pam("gdm-nurgesicht", env=reauth)
    pruefe(not ok and "not confirmed" in pam.ausgabe, "nur mit ✌: ohne ✌ weiter mit Passwort")
    a.modus = "treffer"   # der Dienst würde beim reinen Gesichtsweg zusagen
    ok, _ = pam("gdm-nurgesicht", env=reauth)
    pruefe(not ok and a.anfragen[-1] == (12, 1000),
           "nur mit ✌: das Modul fragt nie den reinen Gesichtsweg")
    with open("/etc/winky/anmeldung-ein", "w") as f:
        f.write("an\n")
    os.chmod("/etc/winky/anmeldung-ein", 0o644)
    dienst("gdm-password", [
        f"auth [success=done default=ignore] {modul} services=gdm-password timeout_ms=1500 "
        f"geste_timeout_ms=3000",
        "auth required pam_deny.so"])
    a.modus = "geste-treffer"
    ok, _ = pam("gdm-password")
    pruefe(ok and a.anfragen[-1] == (13, 1000) and "to log in" in pam.ausgabe,
           "nur mit ✌: Erstanmeldung fragt Gesicht und ✌")
    os.unlink("/etc/winky/anmeldung-ein")
    os.chmod(entsperren, 0o666)
    a.modus = "treffer"
    ok, _ = pam("gdm-nurgesicht", env=reauth)
    pruefe(ok and a.anfragen[-1] == (1, 1000), "für alle beschreibbarer ✌-Schalter wird ignoriert")
    os.unlink(entsperren)
    dienst("gdm-password", [
        f"auth [success=done default=ignore] {modul} services=gdm-password timeout_ms=1500",
        "auth required pam_permit.so"])

    # Fehlendes Modul: Passwort funktioniert weiter
    dienst("gdm-ohne-modul", [
        "auth [success=done default=ignore] /nicht/vorhanden/pam_winky.so services=gdm-ohne-modul",
        "auth required pam_permit.so"])
    ok, _ = pam("gdm-ohne-modul", env=reauth)
    pruefe(ok, "fehlende Moduldatei blockiert die Passwortanmeldung nicht")

    print(f"\n{len(FEHLER)} Fehler")
    return 1 if FEHLER else 0


if __name__ == "__main__":
    sys.exit(main())
