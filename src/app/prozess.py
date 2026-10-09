"""Startet Messwerkzeug oder Verwaltungshelfer und liest ihr Zeilenprotokoll.

  STATUS {json}               Zwischenstand
  BILD <breite> <hoehe> <n>   danach n Bytes RGB (nur Anzeige)
  ERGEBNIS {json}             Abschluss (nur Verwaltungshelfer)
"""

import json
import signal
import subprocess
import threading

from gi.repository import GLib


class Prozess:
    def __init__(self, befehl, bei_bild=None, bei_status=None, bei_ende=None,
                 abbruch_ueber_eingabe=False, cwd=None):
        self.bei_bild = bei_bild
        self.bei_status = bei_status
        self.bei_ende = bei_ende
        self.abbruch_ueber_eingabe = abbruch_ueber_eingabe
        self.abgebrochen = False
        self.fehlertext = []
        self.ergebnis = None
        self._bild_wartet = False
        self.proc = subprocess.Popen(
            befehl, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if abbruch_ueber_eingabe else subprocess.DEVNULL,
            cwd=cwd, start_new_session=True)
        self._t_err = threading.Thread(target=self._lese_stderr, daemon=True)
        self._t_err.start()
        threading.Thread(target=self._lese_stdout, daemon=True).start()

    def _lese_stderr(self):
        for zeile in self.proc.stderr:
            self.fehlertext.append(zeile.decode(errors="replace").rstrip())

    def _lese_stdout(self):
        f = self.proc.stdout
        while True:
            zeile = f.readline()
            if not zeile:
                break
            if zeile.startswith(b"BILD "):
                try:
                    _, w, h, n = zeile.split()
                    w, h, n = int(w), int(h), int(n)
                except ValueError:
                    break
                daten = f.read(n)
                if len(daten) != n:
                    break
                if self.bei_bild and not self._bild_wartet:
                    self._bild_wartet = True
                    GLib.idle_add(self._bild, w, h, daten)
            elif zeile.startswith(b"STATUS "):
                try:
                    st = json.loads(zeile[7:])
                except ValueError:
                    continue
                if self.bei_status:
                    GLib.idle_add(self._weiter, self.bei_status, st)
            elif zeile.startswith(b"ERGEBNIS "):
                try:
                    self.ergebnis = json.loads(zeile[9:])
                except ValueError:
                    pass
        rc = self.proc.wait()
        self._t_err.join(timeout=2)
        if self.bei_ende:
            GLib.idle_add(self._weiter, self.bei_ende, self, rc)

    @staticmethod
    def _weiter(funktion, *args):
        funktion(*args)
        return False

    def _bild(self, w, h, daten):
        self._bild_wartet = False
        self.bei_bild(w, h, daten)
        return False

    def laeuft(self):
        return self.proc.poll() is None

    def abbrechen(self):
        """Messwerkzeug: SIGTERM. Verwaltungshelfer (root): Eingabe schließen."""
        self.abgebrochen = True
        if not self.laeuft():
            return
        if self.abbruch_ueber_eingabe:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
        else:
            self.proc.send_signal(signal.SIGTERM)

    def fehlermeldung(self, rc):
        """Lesbare Meldung für einen fehlgeschlagenen Lauf."""
        if self.ergebnis and self.ergebnis.get("fehler"):
            return self.ergebnis["fehler"]
        if rc == 126:
            return "Abgebrochen: Das Passwort wurde nicht eingegeben."
        if rc == 127:
            return "Nicht berechtigt oder Passwortabfrage nicht verfügbar."
        text = "\n".join(z for z in self.fehlertext[-6:] if z.strip())
        return text or f"Fehlgeschlagen (Rückgabewert {rc})."
