#include "sitzung.h"

#include <systemd/sd-login.h>

#include <cstdlib>
#include <cstring>

namespace winky {

bool hatLokaleGrafischeSitzung(uid_t uid, std::string& grund) {
  char** sitzungen = nullptr;
  const int n = sd_uid_get_sessions(uid, /*require_active=*/1, &sitzungen);
  if (n <= 0) {
    grund = "keine aktive Sitzung";
    return false;
  }
  bool ok = false;
  for (int i = 0; i < n; ++i) {
    const char* s = sitzungen[i];
    char* seat = nullptr;
    char* typ = nullptr;
    char* klasse = nullptr;
    const bool lokal = sd_session_is_remote(s) == 0;
    const bool auf_seat0 = sd_session_get_seat(s, &seat) >= 0 && seat && std::strcmp(seat, "seat0") == 0;
    const bool grafisch = sd_session_get_type(s, &typ) >= 0 && typ &&
                          (std::strcmp(typ, "wayland") == 0 || std::strcmp(typ, "x11") == 0);
    const bool benutzer = sd_session_get_class(s, &klasse) >= 0 && klasse &&
                          std::strcmp(klasse, "user") == 0;
    if (lokal && auf_seat0 && grafisch && benutzer) ok = true;
    std::free(seat);
    std::free(typ);
    std::free(klasse);
    std::free(sitzungen[i]);
  }
  std::free(sitzungen);
  if (!ok) grund = "keine lokale grafische Sitzung an seat0";
  return ok;
}

bool anmeldemaskeAktiv(std::string& grund) {
  char* sitzung = nullptr;
  if (sd_seat_get_active("seat0", &sitzung, nullptr) < 0 || !sitzung) {
    grund = "keine aktive Sitzung an seat0";
    return false;
  }
  char* klasse = nullptr;
  const bool ok = sd_session_is_remote(sitzung) == 0 && sd_session_get_class(sitzung, &klasse) >= 0 &&
                  klasse && std::strcmp(klasse, "greeter") == 0;
  std::free(klasse);
  std::free(sitzung);
  if (!ok) grund = "keine Anmeldemaske an seat0";
  return ok;
}

bool terminalEntfernt(const std::string& terminal) {
  std::string tty = terminal;
  if (tty.rfind("/dev/", 0) == 0) tty = tty.substr(5);
  char** sitzungen = nullptr;
  const int n = sd_get_sessions(&sitzungen);
  if (n < 0) return true;  // logind nicht erreichbar: im Zweifel ablehnen
  bool entfernt = false;
  for (int i = 0; i < n; ++i) {
    char* s_tty = nullptr;
    if (sd_session_get_tty(sitzungen[i], &s_tty) >= 0 && s_tty && tty == s_tty &&
        sd_session_is_remote(sitzungen[i]) != 0)
      entfernt = true;
    std::free(s_tty);
    std::free(sitzungen[i]);
  }
  std::free(sitzungen);
  return entfernt;
}

}  // namespace winky
