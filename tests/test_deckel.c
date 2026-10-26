/* Test der Deckelprüfung im PAM-Modul: Kamera überspringen nur bei Deckel zu UND externem
 * Bildschirm. Bindet pam_winky.c ein; Deckel- und Bildschirmordner sind beim Bau auf relative
 * Pfade gelegt (DECKEL_ORDNER=lid, DRM_ORDNER=drm), der Test arbeitet in einem Wegwerf-Ordner. */
#include "../src/pam/pam_winky.c"

#include <stdlib.h>

static int fehler = 0;

static void pruefe(int bed, const char *text) {
  printf("%s  %s\n", bed ? "ok    " : "FEHLER", text);
  if (!bed) ++fehler;
}

static void datei(const char *pfad, const char *inhalt) {
  char ordner[256];
  snprintf(ordner, sizeof(ordner), "%s", pfad);
  *strrchr(ordner, '/') = '\0';
  mkdir(ordner, 0755);
  FILE *f = fopen(pfad, "w");
  fputs(inhalt, f);
  fclose(f);
}

int main(void) {
  char vorlage[] = "/tmp/winky-deckel-XXXXXX";
  if (!mkdtemp(vorlage) || chdir(vorlage) != 0) return 1;
  mkdir("drm", 0755);

  pruefe(!zugeklappt_am_bildschirm(), "ohne Deckel (Desktop-Rechner): Kamera wird versucht");
  mkdir("lid", 0755);
  datei("lid/LID0/state", "state:      open\n");
  datei("drm/card1-eDP-1/status", "connected\n");
  datei("drm/card1-DP-1/status", "disconnected\n");
  datei("drm/card1-Writeback-1/status", "connected\n");
  pruefe(!zugeklappt_am_bildschirm(), "Deckel auf: Kamera wird versucht");
  datei("lid/LID0/state", "state:      closed\n");
  pruefe(!zugeklappt_am_bildschirm(),
         "Deckel meldet zu, nur eingebauter Bildschirm: Kamera wird trotzdem versucht");
  datei("drm/card1-DP-1/status", "connected\n");
  pruefe(zugeklappt_am_bildschirm(), "Deckel zu, externer Bildschirm (DP): gleich das Passwort");
  datei("drm/card1-DP-1/status", "disconnected\n");
  datei("drm/card1-HDMI-A-1/status", "connected\n");
  pruefe(zugeklappt_am_bildschirm(), "Deckel zu, externer Bildschirm (HDMI): gleich das Passwort");
  datei("lid/LID0/state", "state:      open\n");
  pruefe(!zugeklappt_am_bildschirm(), "Deckel auf am externen Bildschirm: Kamera wird versucht");

  printf("\n%d Fehler\n", fehler);
  return fehler ? 1 : 0;
}
