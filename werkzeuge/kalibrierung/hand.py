"""Seite „Handzeichen ✌“: Messung des Victory-Zeichens als Bestätigung für sudo und KeePassXC.

Mit Rückmeldung wie im Einsatz („✓ Erkannt“ im Bild); dazu Dunkel, Abstand und Schritte ohne
Zeichen (Tippen, Alltag), die keinen Fehlalarm auslösen dürfen. Regeln in auswerten_hand.py.
"""

from gi.repository import GLib

import auswerten_hand
from messseite import MessSeite, schritt
from vorschau import komma

TIPPTEXT = ("Der Sperrbildschirm erkennt mich in weniger als einer Sekunde, und für sudo genügt "
            "später vielleicht ein kurzes Zeichen in die Kamera.")

ALLTAG = ["Kratz dich an der Nase", "Stütz das Kinn auf die Hand",
          "Trink einen Schluck (oder tu so)", "Nimm dein Handy und schau drauf",
          "Wink in die Kamera wie im Videocall", "Reib dir die Augen",
          "Fahr dir durch die Haare", "Zeig mit dem Finger auf den Bildschirm",
          "Zähl mit den Fingern bis fünf"]

SIGNAL = "Victory ✌"
ZEITEN = [3, 11, 19, 27]   # vier Aufforderungen, je bis zu 6 s, 2 s Pause
ERKANNT = "✓ Erkannt"


def bestaetigen(id, titel, gruppe, anleitung, **kw):
    return schritt(id, titel, gruppe, anleitung, dauer=34, signal=SIGNAL, signal_zeiten=ZEITEN,
                   signal_dauer=auswerten_hand.RUECKMELDUNG_MS / 1000, **kw)


SO_GEHTS = ("Wenn „Victory ✌“ erscheint: mit der Hand, die du lieber nimmst, das V in die Kamera "
            "zeigen, Handfläche zur Kamera, und halten, bis „✓ Erkannt“ erscheint. Dann Hand "
            "wieder runter.")

SCHRITTE = [
    bestaetigen("bestaetigen", "Bestätigen wie später", "Handzeichen", [
        "Klick auf „Starten“ und leg die Hände auf die Tastatur. Die Messung dauert 34 Sekunden.",
        SO_GEHTS,
        "Kommt nach 6 Sekunden kein „✓ Erkannt“, verschwindet der Hinweis. Einfach beim "
        "nächsten weitermachen."]),
    schritt("tippen", "Tippen", "Ohne Handzeichen", [
        "Klick auf „Starten“ und tipp den Satz unten in das Feld ab, in deinem normalen Tempo.",
        "Wenn du fertig bist, tipp einfach weiter, was dir einfällt. Gespeichert wird davon "
        "nichts."],
        dauer=30, tipptext=TIPPTEXT),
    schritt("alltag", "Alltag am Rechner", "Ohne Handzeichen", [
        "Klick auf „Starten“. Im Bild erscheinen nacheinander neun kleine Aufgaben, je "
        "5 Sekunden.",
        "Mach einfach mit, so natürlich wie möglich."],
        dauer=45, aufgaben=ALLTAG),
    bestaetigen("dunkel", "Im Dunkeln", "Bedingungen", [
        "Mach das Raumlicht aus, der Bildschirm bleibt an.",
        "Klick auf „Starten“. Du hast 8 Sekunden, um dich wieder hinzusetzen.",
        SO_GEHTS], countdown=8),
    bestaetigen("weit", "Mit Abstand", "Bedingungen", [
        "Rück etwa eine Armlänge vom Bildschirm weg (gut 70 cm).",
        "Klick auf „Starten“.",
        SO_GEHTS]),
]


class HandSeite(MessSeite):
    ORDNER = "hand"
    SCHRITTE = SCHRITTE
    BEFEHL = "hand"
    AUSWERTEN = auswerten_hand

    folge = 0

    def live_text(self, st):
        if not st.get("hand"):
            gesicht = "Gesicht erkannt" if st.get("gesicht") else "kein Gesicht im Bild"
            return f"Keine Hand im Bild · {gesicht}", st.get("gesicht", False)
        return f"Hand erkannt · {st.get('geste')} ({komma(st.get('sicherheit') or 0, 2)})", True

    def status_merken(self, st):
        """Dieselbe Regel wie die Auswertung: Victory wahrscheinlichste Klasse ab 0,5, Hand
        sicher, K Bilder in Folge. Zeigt „✓ Erkannt“, solange eine Aufforderung steht."""
        ja = (st.get("hand") and (st.get("presence") or 0) >= auswerten_hand.PRESENCE_MIN
              and st.get("geste") == "Victory" and (st.get("victory") or 0) >= auswerten_hand.P_MIN)
        self.folge = self.folge + 1 if ja else 0
        if self.folge >= auswerten_hand.K and self.vorschau.label.get_label() == SIGNAL \
                and self.vorschau.label.get_visible():
            self.vorschau.hinweis(ERKANNT)
            GLib.timeout_add(1000, self._erkannt_weg)

    def _erkannt_weg(self):
        if self.vorschau.label.get_label() == ERKANNT:
            self.vorschau.label.set_visible(False)
        return False
