/* Protokoll zwischen PAM-Modul / Verwaltungshelfer und dem Prüfdienst.
 *
 * Unix-Socket vom Typ SOCK_SEQPACKET unter /run/winky.sock (root, 0600).
 * systemd startet je Verbindung eine Instanz von winky@.service.
 *
 * Ablauf: Der Aufrufer schickt genau eine winky_anfrage. Bei AUTH und RESET
 * antwortet der Dienst mit genau einer winky_antwort. Bei EINLERNEN und TESTEN
 * folgen Nachrichten, die mit einem Typbyte beginnen:
 *   'S' + JSON-Text        Zwischenstand
 *   'B' + u16 breite + u16 hoehe + Graustufen   Vorschaubild (nur Anzeige)
 *   'V' + u32 anzahl + u32 dim + char modell[64] + float[anzahl*dim]
 *                          eingelernte Merkmalsvektoren (nur EINLERNEN)
 *   'E' + winky_antwort      Ende
 *
 * Bei SUDO schickt das PAM-Modul direkt nach der Anfrage eine zweite Nachricht
 *   'C' + Terminal (z. B. "/dev/pts/3") + '\0' + Befehlszeile + '\0'
 * höchstens WINKY_BEFEHL_MAX Bytes. Der Dienst prüft damit, dass das Terminal zu keiner
 * entfernten Sitzung gehört, und zeigt den Befehl im Desktop-Hinweis.
 * Sobald die Kamera läuft, schickt der Dienst bei SUDO ein einzelnes Byte 'W' (wartet),
 * damit das PAM-Modul erst dann zum Handzeichen auffordert; danach die winky_antwort.
 * GESTE_TESTEN läuft als Strom wie TESTEN.
 * Alle Zahlen in Maschinen-Byteordnung (beide Seiten laufen auf demselben Rechner).
 */
#ifndef WINKY_PROTOKOLL_H
#define WINKY_PROTOKOLL_H

#include <stdint.h>

#define WINKY_SOCKET "/run/winky.sock"
#define WINKY_POLKIT_SOCKET "/run/winky-polkit.sock" /* root:polkitd 0660, nur KEEPASSXC */
#define WINKY_MAGIC 0x314b4e57u /* "WNK1" */

enum winky_op {
  WINKY_OP_AUTH = 1,      /* Entsperren prüfen (PAM-Modul) */
  WINKY_OP_RESET = 2,     /* Fehlversuche zurücksetzen (nach Passwort-Erfolg) */
  WINKY_OP_EINLERNEN = 3, /* Merkmalsvektoren aufnehmen (Verwaltungshelfer) */
  WINKY_OP_TESTEN = 4,    /* Erkennung probeweise, ohne Sperrzähler */
  WINKY_OP_KAMERAS = 5,   /* IR-Kameras suchen und prüfen: 'S' mit JSON-Liste, dann 'E' */
  WINKY_OP_KEEPASSXC = 6, /* Schnellentsperren von KeePassXC (über Polkit), sonst wie AUTH */
  WINKY_OP_SUDO = 7,      /* sudo bestätigen: Gesicht und Handzeichen ✌ (PAM-Modul) */
  WINKY_OP_GESTE_TESTEN = 8 /* Gesicht und ✌ probeweise (Verwaltungshelfer, Strom) */
};

enum winky_status {
  WINKY_TREFFER = 0,
  WINKY_KEIN_TREFFER = 1,
  WINKY_KEIN_GESICHT = 2,
  WINKY_NICHT_EINGERICHTET = 3,
  WINKY_GESPERRT = 4,
  WINKY_FEHLER = 5,
  WINKY_ABGELEHNT = 6,
  WINKY_OK = 7
};

struct winky_anfrage {
  uint32_t magic;
  uint32_t op;
  uint32_t uid;
  uint32_t dauer_s; /* nur EINLERNEN/TESTEN, sonst 0 */
};

struct winky_antwort {
  uint32_t magic;
  uint32_t status;
  float wert; /* bester Ähnlichkeitswert, -1 wenn keiner */
  uint32_t dauer_ms;
};

#define WINKY_VORSCHAU_MAX_BREITE 320
#define WINKY_BEFEHL_MAX 320

#endif
