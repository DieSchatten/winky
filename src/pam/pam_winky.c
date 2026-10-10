/* pam_winky: Gesichtsentsperrung für GNOME-Sperrbildschirm (GDM-Wiederanmeldung) und sudo (mit ✌).
 * Bewusst klein (nur libc/libpam, kein fork, nichts aus dem Home); geprüft wird im Prüfdienst.
 * Jede unerfüllte Vorbedingung und jeder Fehler ergibt PAM_IGNORE, dann fragt pam_unix (Passwort).
 * Argumente: services=a,b timeout_ms=500..5000 geste=<Dienste, auch in services>
 * geste_timeout_ms=3000..60000; Unbekanntes schaltet das Modul ab. Testdienste für pamtester:
 * winky-test (ohne GDM-Prüfung), winky-test-geste (ohne Terminalprüfung), winky-test-dialog
 * (wie polkit-1). */
#define PAM_SM_AUTH
#define _GNU_SOURCE

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pwd.h>
#include <security/pam_ext.h>
#include <security/pam_modules.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <syslog.h>
#include <time.h>
#include <unistd.h>

#include "protokoll.h"

#define SICHTBAR __attribute__((visibility("default")))
#define DATEN_GESICHT "winky_gesicht"
#define NOTSCHALTER "/etc/winky/disabled"
#define TESTDIENST "winky-test"
#define TESTDIENST_GESTE "winky-test-geste"
#define SUDO_SCHALTER "/etc/winky/sudo-ein"
#define ANMELDUNG_SCHALTER "/etc/winky/anmeldung-ein"
#define DIALOG_SCHALTER "/etc/winky/dialoge-ein"
#define TESTDIENST_DIALOG "winky-test-dialog"

struct argumente {
  char dienste[256];
  char geste[128];
  int timeout_ms;
  int geste_timeout_ms;
};

static int lese_argumente(int argc, const char **argv, struct argumente *a) {
  a->dienste[0] = '\0';
  a->geste[0] = '\0';
  a->timeout_ms = 3000;
  a->geste_timeout_ms = 10000;
  for (int i = 0; i < argc; ++i) {
    const char *arg = argv[i];
    if (strncmp(arg, "services=", 9) == 0) {
      const size_t n = strlen(arg + 9);
      if (n == 0 || n >= sizeof(a->dienste)) return 0;
      memcpy(a->dienste, arg + 9, n + 1);
    } else if (strncmp(arg, "geste=", 6) == 0) {
      const size_t n = strlen(arg + 6);
      if (n == 0 || n >= sizeof(a->geste)) return 0;
      memcpy(a->geste, arg + 6, n + 1);
    } else if (strncmp(arg, "timeout_ms=", 11) == 0) {
      char *ende = NULL;
      const long v = strtol(arg + 11, &ende, 10);
      if (!ende || *ende != '\0' || v < 500 || v > 5000) return 0;
      a->timeout_ms = (int)v;
    } else if (strncmp(arg, "geste_timeout_ms=", 17) == 0) {
      char *ende = NULL;
      const long v = strtol(arg + 17, &ende, 10);
      if (!ende || *ende != '\0' || v < 3000 || v > 60000) return 0;
      a->geste_timeout_ms = (int)v;
    } else {
      return 0; /* unbekanntes Argument: lieber gar nichts tun */
    }
  }
  return a->dienste[0] != '\0';
}

static int in_liste(const char *liste, const char *dienst) {
  const size_t n = strlen(dienst);
  const char *p = liste;
  while (*p) {
    const char *komma = strchr(p, ',');
    const size_t len = komma ? (size_t)(komma - p) : strlen(p);
    if (len == n && strncmp(p, dienst, n) == 0) return 1;
    if (!komma) break;
    p = komma + 1;
  }
  return 0;
}

static int dienst_erlaubt(const struct argumente *a, const char *dienst) {
  return in_liste(a->dienste, dienst);
}

static int deckel_zu(void) {
  DIR *d = opendir("/proc/acpi/button/lid");
  if (!d) return 0;
  int zu = 0;
  struct dirent *e;
  while (!zu && (e = readdir(d)) != NULL) {
    if (e->d_name[0] == '.') continue;
    char pfad[300];
    snprintf(pfad, sizeof(pfad), "/proc/acpi/button/lid/%s/state", e->d_name);
    FILE *f = fopen(pfad, "re");
    if (!f) continue;
    char zeile[64] = {0};
    if (fgets(zeile, sizeof(zeile), f) && strstr(zeile, "closed")) zu = 1;
    fclose(f);
  }
  closedir(d);
  return zu;
}

static long ms_seit(const struct timespec *start) {
  struct timespec jetzt;
  clock_gettime(CLOCK_MONOTONIC, &jetzt);
  return (jetzt.tv_sec - start->tv_sec) * 1000L + (jetzt.tv_nsec - start->tv_nsec) / 1000000L;
}

/* Fragt den Prüfdienst: 0 und *status, sonst -1. zusatz geht als zweite Nachricht; auf 'W'
 * (Kamera läuft) zeigt PAM einmal hinweis und setzt *wartete. */
static int frage(uint32_t op, uid_t uid, int timeout_ms, const char *zusatz, size_t zusatz_len,
                 pam_handle_t *pamh, const char *hinweis, int *wartete, uint32_t *status) {
  struct timespec start;
  clock_gettime(CLOCK_MONOTONIC, &start);
  const int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
  if (fd < 0) return -1;
  struct sockaddr_un sa;
  memset(&sa, 0, sizeof(sa));
  sa.sun_family = AF_UNIX;
  strncpy(sa.sun_path, WINKY_SOCKET, sizeof(sa.sun_path) - 1);
  if (connect(fd, (struct sockaddr *)&sa, sizeof(sa)) != 0) {
    close(fd);
    return -1;
  }
  /* Gegenstelle muss root sein (Socket wird von systemd angelegt) */
  struct ucred cred;
  socklen_t len = sizeof(cred);
  if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &cred, &len) != 0 || cred.uid != 0) {
    close(fd);
    return -1;
  }
  struct winky_anfrage q = {WINKY_MAGIC, op, (uint32_t)uid, 0};
  if (send(fd, &q, sizeof(q), MSG_NOSIGNAL) != (ssize_t)sizeof(q) ||
      (zusatz && send(fd, zusatz, zusatz_len, MSG_NOSIGNAL) != (ssize_t)zusatz_len)) {
    close(fd);
    return -1;
  }
  for (;;) {
    const long rest = timeout_ms - ms_seit(&start);
    if (rest <= 0) break;
    struct pollfd p = {fd, POLLIN, 0};
    const int r = poll(&p, 1, (int)rest);
    if (r < 0 && errno == EINTR) continue;
    if (r <= 0) break;
    struct winky_antwort a;
    const ssize_t n = recv(fd, &a, sizeof(a), MSG_DONTWAIT);
    if (n < 0 && (errno == EAGAIN || errno == EINTR)) continue;
    if (n == 1 && ((const char *)&a)[0] == 'W' && pamh && hinweis) {
      if (wartete && !*wartete) pam_info(pamh, "%s", hinweis);
      if (wartete) *wartete = 1;
      continue;
    }
    close(fd);
    if (n != (ssize_t)sizeof(a) || a.magic != WINKY_MAGIC) return -1;
    *status = a.status;
    return 0;
  }
  close(fd);
  return -1;
}

static int frage_dienst(uint32_t op, uid_t uid, int timeout_ms, uint32_t *status) {
  return frage(op, uid, timeout_ms, NULL, 0, NULL, NULL, NULL, status);
}

/* Schlüsselbund: nach erkannter Erstanmeldung das im TPM versiegelte Passwort beim
 * Schlüsselbund-Dienst holen und als PAM_AUTHTOK für pam_gnome_keyring bereitstellen. */
static void schluessel_holen(pam_handle_t *pamh, uid_t uid) {
  char pfad[80];
  snprintf(pfad, sizeof(pfad), "/var/lib/winky/%u/schluesselbund.cred", (unsigned)uid);
  struct stat st;
  if (lstat(pfad, &st) != 0 || !S_ISREG(st.st_mode) || st.st_uid != 0) return;
  struct timespec start;
  clock_gettime(CLOCK_MONOTONIC, &start);
  const int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
  if (fd < 0) return;
  struct sockaddr_un sa;
  memset(&sa, 0, sizeof(sa));
  sa.sun_family = AF_UNIX;
  strncpy(sa.sun_path, WINKY_SCHLUESSEL_SOCKET, sizeof(sa.sun_path) - 1);
  struct ucred cred;
  socklen_t len = sizeof(cred);
  struct winky_anfrage q = {WINKY_MAGIC, WINKY_OP_SCHLUESSEL, (uint32_t)uid, 0};
  if (connect(fd, (struct sockaddr *)&sa, sizeof(sa)) != 0 ||
      getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &cred, &len) != 0 || cred.uid != 0 ||
      send(fd, &q, sizeof(q), MSG_NOSIGNAL) != (ssize_t)sizeof(q)) {
    close(fd);
    return;
  }
  char puf[WINKY_SCHLUESSEL_MAX + 2];
  for (;;) {
    const long rest = 6000 - ms_seit(&start); /* TPM und Prüfung brauchen etwas */
    if (rest <= 0) break;
    struct pollfd p = {fd, POLLIN, 0};
    const int r = poll(&p, 1, (int)rest);
    if (r < 0 && errno == EINTR) continue;
    if (r <= 0) break;
    const ssize_t n = recv(fd, puf, sizeof(puf) - 1, MSG_DONTWAIT);
    if (n < 0 && (errno == EAGAIN || errno == EINTR)) continue;
    if (n > 1 && n <= WINKY_SCHLUESSEL_MAX && puf[0] == 'K') {
      puf[n] = '\0';
      if (pam_set_item(pamh, PAM_AUTHTOK, puf + 1) == PAM_SUCCESS)
        pam_syslog(pamh, LOG_INFO, "Schlüsselbund-Passwort bereitgestellt");
    }
    break;
  }
  explicit_bzero(puf, sizeof(puf));
  close(fd);
}

/* Befehlszeile dieses Prozesses (sudo ...), Nullbytes als Leerzeichen, gekürzt */
static void befehlszeile(char *out, size_t max) {
  out[0] = '\0';
  const int fd = open("/proc/self/cmdline", O_RDONLY | O_CLOEXEC);
  if (fd < 0) return;
  const ssize_t n = read(fd, out, max - 1);
  close(fd);
  if (n <= 0) {
    out[0] = '\0';
    return;
  }
  for (ssize_t i = 0; i < n; ++i) {
    if (out[i] == '\0') out[i] = ' ';
    else if ((unsigned char)out[i] < 0x20) out[i] = '?';
  }
  out[n] = '\0';
  size_t l = strlen(out);
  while (l > 0 && out[l - 1] == ' ') out[--l] = '\0';
}

/* Sprache der Terminalmeldungen aus der Umgebung des Aufrufers: Deutsch oder Englisch */
static int deutsch(void) {
  static const char *const namen[] = {"LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"};
  for (size_t i = 0; i < sizeof(namen) / sizeof(namen[0]); i++) {
    const char *w = getenv(namen[i]);
    if (w && *w) return strncmp(w, "de", 2) == 0;
  }
  return 0;
}

static int schalter_an(const char *pfad) {
  struct stat st;
  return lstat(pfad, &st) == 0 && S_ISREG(st.st_mode) && st.st_uid == 0 &&
         !(st.st_mode & (S_IWGRP | S_IWOTH));
}

/* Gemeinsame Vorprüfung für authenticate und setcred: liefert timeout_ms (sonst -1) und *uid. */
static int vorpruefung(pam_handle_t *pamh, int argc, const char **argv, uid_t *uid,
                       int *testdienst, struct argumente *aus) {
  struct argumente a;
  if (!lese_argumente(argc, argv, &a)) return -1;
  if (aus) *aus = a;
  const void *dienst = NULL;
  if (pam_get_item(pamh, PAM_SERVICE, &dienst) != PAM_SUCCESS || !dienst) return -1;
  if (!dienst_erlaubt(&a, (const char *)dienst)) return -1;
  *testdienst = strcmp((const char *)dienst, TESTDIENST) == 0;
  const void *benutzer = NULL;
  if (pam_get_item(pamh, PAM_USER, &benutzer) != PAM_SUCCESS || !benutzer ||
      !*(const char *)benutzer)
    return -1;
  const void *rhost = NULL;
  if (pam_get_item(pamh, PAM_RHOST, &rhost) == PAM_SUCCESS && rhost && *(const char *)rhost)
    return -1;
  struct passwd pw, *pwp = NULL;
  char puffer[4096];
  if (getpwnam_r((const char *)benutzer, &pw, puffer, sizeof(puffer), &pwp) != 0 || !pwp)
    return -1;
  if (pw.pw_uid == 0) return -1;
  *uid = pw.pw_uid;
  return a.timeout_ms;
}

/* Administrator-Dialog (polkit-1): läuft nur, wenn wirklich ein Passwortdialog erscheint. Was
 * freigegeben wird, zeigt der Dialog selbst; Winky schreibt die Aufforderung zum ✌ hinein. */
static int dialog_weg(pam_handle_t *pamh, uid_t uid, const struct argumente *a) {
  if (!schalter_an(DIALOG_SCHALTER)) return PAM_IGNORE;
  struct stat st;
  if (lstat(NOTSCHALTER, &st) == 0) return PAM_IGNORE;
  if (deckel_zu()) return PAM_IGNORE;
  uint32_t status = WINKY_FEHLER;
  int wartete = 0;
  if (frage(WINKY_OP_DIALOG, uid, a->geste_timeout_ms, NULL, 0, pamh,
            deutsch() ? "Winky: zum Freigeben \u270c in die Kamera zeigen (sonst Passwort) \u2026"
                      : "Winky: show \u270c to the camera to approve (or type your password) \u2026",
            &wartete, &status) == 0 && status == WINKY_TREFFER) {
    pam_info(pamh, deutsch() ? "Winky: \u2713 freigegeben" : "Winky: \u2713 approved");
    pam_set_data(pamh, DATEN_GESICHT, (void *)1, NULL);
    pam_syslog(pamh, LOG_INFO, "Administrator-Dialog per Gesicht und Handzeichen freigegeben");
    return PAM_SUCCESS;
  }
  if (wartete) pam_info(pamh, deutsch() ? "Winky: nicht bestätigt" : "Winky: not confirmed");
  return PAM_IGNORE;
}

SICHTBAR int pam_sm_authenticate(pam_handle_t *pamh, int flags, int argc, const char **argv) {
  (void)flags;
  uid_t uid;
  int testdienst = 0;
  struct argumente a;
  const int timeout_ms = vorpruefung(pamh, argc, argv, &uid, &testdienst, &a);
  if (timeout_ms < 0) return PAM_IGNORE;
  const void *dienst = NULL;
  pam_get_item(pamh, PAM_SERVICE, &dienst);
  if (dienst && in_liste(a.geste, (const char *)dienst)) {
    if (strcmp((const char *)dienst, "polkit-1") == 0 ||
        strcmp((const char *)dienst, TESTDIENST_DIALOG) == 0)
      return dialog_weg(pamh, uid, &a);
    /* Gestenweg (sudo): nur am echten Terminal, nicht bei sudo -S oder Skripten */
    if (!schalter_an(SUDO_SCHALTER)) return PAM_IGNORE;
    const int test = strcmp((const char *)dienst, TESTDIENST_GESTE) == 0;
    if (!test && !isatty(STDIN_FILENO)) return PAM_IGNORE;
    const void *tty = NULL;
    if (pam_get_item(pamh, PAM_TTY, &tty) != PAM_SUCCESS || !tty ||
        strncmp((const char *)tty, "/dev/", 5) != 0 || strlen((const char *)tty) > 60)
      return PAM_IGNORE;
    struct stat st;
    if (lstat(NOTSCHALTER, &st) == 0) return PAM_IGNORE;
    if (deckel_zu()) return PAM_IGNORE;
    char nachricht[WINKY_BEFEHL_MAX];
    nachricht[0] = 'C';
    const size_t tl = strlen((const char *)tty);
    memcpy(nachricht + 1, tty, tl + 1);
    befehlszeile(nachricht + 2 + tl, sizeof(nachricht) - 2 - tl);
    const size_t len = 2 + tl + strlen(nachricht + 2 + tl) + 1;
    uint32_t status = WINKY_FEHLER;
    int wartete = 0;
    if (frage(WINKY_OP_SUDO, uid, a.geste_timeout_ms, nachricht, len, pamh,
              deutsch() ? "Winky: zum Bestätigen \u270c in die Kamera zeigen (sonst Passwort) \u2026"
                        : "Winky: show \u270c to the camera to confirm (or type your password) \u2026",
              &wartete, &status) == 0 && status == WINKY_TREFFER) {
      pam_info(pamh, deutsch() ? "Winky: \u2713 bestätigt" : "Winky: \u2713 confirmed");
      pam_set_data(pamh, DATEN_GESICHT, (void *)1, NULL);
      pam_syslog(pamh, LOG_INFO, "sudo per Gesicht und Handzeichen bestätigt");
      return PAM_SUCCESS;
    }
    if (wartete) pam_info(pamh, deutsch() ? "Winky: nicht bestätigt" : "Winky: not confirmed");
    return PAM_IGNORE;
  }
  /* Sperrbildschirm (GDM-Wiederanmeldung); die erste Anmeldung nur mit eigenem Schalter */
  uint32_t op = WINKY_OP_AUTH;
  if (!testdienst) {
    const char *reauth = getenv("GDM_SESSION_FOR_REAUTH");
    if (!reauth || strcmp(reauth, "1") != 0) {
      if (!dienst || strcmp((const char *)dienst, "gdm-password") != 0 ||
          !schalter_an(ANMELDUNG_SCHALTER))
        return PAM_IGNORE;
      op = WINKY_OP_ANMELDUNG;
    }
  }
  struct stat st;
  if (lstat(NOTSCHALTER, &st) == 0) return PAM_IGNORE;
  if (deckel_zu()) return PAM_IGNORE;

  /* An der Anmeldemaske sagen, was passiert (am Sperrbildschirm nicht: GNOME verzögert dort
   * jede Meldung, und das Entsperren soll sofort gehen) */
  const int maske = op == WINKY_OP_ANMELDUNG;
  if (maske)
    pam_info(pamh, deutsch() ? "Winky: Schau in die Kamera \u2026 (sonst gleich Passwort)"
                             : "Winky: look at the camera \u2026 (or the password in a moment)");
  uint32_t status = WINKY_FEHLER;
  if (frage_dienst(op, uid, timeout_ms, &status) == 0 && status == WINKY_TREFFER) {
    if (maske) {
      pam_info(pamh, deutsch() ? "Winky: \u2713 erkannt, Anmeldung l\u00e4uft \u2026"
                               : "Winky: \u2713 recognized, logging in \u2026");
      schluessel_holen(pamh, uid);
    }
    pam_set_data(pamh, DATEN_GESICHT, (void *)1, NULL);
    pam_syslog(pamh, LOG_INFO, "per Gesicht entsperrt");
    return PAM_SUCCESS;
  }
  if (maske)
    pam_info(pamh, deutsch() ? "Winky: nicht erkannt, bitte Passwort eingeben"
                             : "Winky: not recognized, please enter your password");
  return PAM_IGNORE;
}

/* Nach erfolgreicher Passwortanmeldung die Zähler im Prüfdienst zurücksetzen */
SICHTBAR int pam_sm_setcred(pam_handle_t *pamh, int flags, int argc, const char **argv) {
  (void)flags;
  uid_t uid;
  int testdienst = 0;
  if (vorpruefung(pamh, argc, argv, &uid, &testdienst, NULL) < 0) return PAM_IGNORE;
  const void *gesicht = NULL;
  if (pam_get_data(pamh, DATEN_GESICHT, &gesicht) == PAM_SUCCESS) return PAM_IGNORE;
  uint32_t status;
  frage_dienst(WINKY_OP_RESET, uid, 300, &status);
  return PAM_IGNORE;
}
