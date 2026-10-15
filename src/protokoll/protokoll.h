/* Protokoll PAM-Modul / Verwaltungshelfer <-> Prüfdienst über WINKY_SOCKET (SOCK_SEQPACKET, 0600).
 * Der Aufrufer schickt genau eine winky_anfrage. Antwort: genau eine winky_antwort, bei den
 * Strom-Operationen EINLERNEN, TESTEN, GESTE_TESTEN, KAMERAS stattdessen Nachrichten mit Typbyte:
 *   'S' + JSON-Text                              Zwischenstand
 *   'B' + u16 breite + u16 hoehe + Graustufen    Vorschaubild (nur Anzeige)
 *   'V' + u32 anzahl + u32 dim + char modell[64] + float[anzahl*dim]   Vektoren (nur EINLERNEN)
 *   'E' + winky_antwort                          Ende
 * SUDO: zweite Nachricht 'C' + Terminal + '\0' + Befehlszeile + '\0' (bis WINKY_BEFEHL_MAX Bytes);
 * läuft die Kamera, schickt der Dienst das Einzelbyte 'W', erst dann fordert PAM zum ✌ auf
 * (ebenso bei DIALOG, AUTH_GESTE und ANMELDUNG_GESTE).
 * Zahlen in Maschinen-Byteordnung (beide Seiten auf demselben Rechner).
 */
#ifndef WINKY_PROTOKOLL_H
#define WINKY_PROTOKOLL_H

#include <stdint.h>

#define WINKY_SOCKET "/run/winky.sock"
#define WINKY_POLKIT_SOCKET "/run/winky-polkit.sock" /* root:polkitd 0660, nur KEEPASSXC */
#define WINKY_MAGIC 0x314b4e57u /* "WNK1" */
/* root 0600; Antwort 'K' + Passwort oder 'N', nur direkt nach erkannter Erstanmeldung */
#define WINKY_SCHLUESSEL_SOCKET "/run/winky-schluessel.sock"
#define WINKY_SCHLUESSEL_MAX 1024

enum winky_op {
  WINKY_OP_AUTH = 1,      /* Entsperren prüfen (PAM-Modul) */
  WINKY_OP_RESET = 2,     /* Zähler zurücksetzen (nach Passwort-Erfolg) */
  WINKY_OP_EINLERNEN = 3, /* Merkmalsvektoren aufnehmen (Verwaltungshelfer) */
  WINKY_OP_TESTEN = 4,    /* Erkennung probeweise, ohne Sperrzähler */
  WINKY_OP_KAMERAS = 5,   /* IR-Kameras suchen: 'S' mit JSON-Liste, dann 'E' */
  WINKY_OP_KEEPASSXC = 6, /* KeePassXC entsperren (über Polkit) */
  WINKY_OP_SUDO = 7,      /* sudo bestätigen: Gesicht und ✌ (PAM-Modul) */
  WINKY_OP_GESTE_TESTEN = 8, /* Gesicht und ✌ probeweise (Verwaltungshelfer) */
  WINKY_OP_DIALOG = 9,       /* Administrator-Dialog (PAM-Dienst polkit-1): Gesicht und ✌ */
  WINKY_OP_ANMELDUNG = 10,   /* erste Anmeldung nach dem Start (GDM-Anmeldemaske) */
  WINKY_OP_SCHLUESSEL = 11,  /* Schlüsselbund-Passwort holen (WINKY_SCHLUESSEL_SOCKET) */
  WINKY_OP_AUTH_GESTE = 12,  /* Sperrbildschirm nur mit Gesicht und ✌ (Schalter entsperren-geste) */
  WINKY_OP_ANMELDUNG_GESTE = 13 /* erste Anmeldung nur mit Gesicht und ✌ */
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
