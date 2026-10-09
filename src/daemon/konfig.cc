#include "konfig.h"

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <sstream>

namespace winky {

namespace {

std::string trim(const std::string& s) {
  const auto a = s.find_first_not_of(" \t\r");
  if (a == std::string::npos) return "";
  const auto b = s.find_last_not_of(" \t\r");
  return s.substr(a, b - a + 1);
}

bool zahl(const std::string& v, double lo, double hi, double& out) {
  if (v.empty() || v.size() > 16) return false;
  char* ende = nullptr;
  errno = 0;
  const double d = std::strtod(v.c_str(), &ende);
  if (errno != 0 || ende == v.c_str() || *ende != '\0' || !(d >= lo && d <= hi)) return false;
  out = d;
  return true;
}

}  // namespace

bool ladeKonfig(const std::string& pfad, Konfig& k, std::string& fehler) {
  const int fd = ::open(pfad.c_str(), O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  if (fd < 0) {
    fehler = "Konfiguration nicht lesbar: " + std::string(std::strerror(errno));
    return false;
  }
  struct stat st {};
  if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_uid != 0 ||
      (st.st_mode & (S_IWGRP | S_IWOTH)) || st.st_size > 65536) {
    ::close(fd);
    fehler = "Konfiguration hat unsichere Rechte oder falschen Besitzer";
    return false;
  }
  std::string inhalt(static_cast<size_t>(st.st_size), '\0');
  const ssize_t n = ::read(fd, inhalt.data(), inhalt.size());
  ::close(fd);
  if (n != st.st_size) {
    fehler = "Konfiguration unvollständig gelesen";
    return false;
  }

  Konfig neu;
  std::istringstream in(inhalt);
  std::string zeile;
  int nr = 0;
  while (std::getline(in, zeile)) {
    ++nr;
    const auto raute = zeile.find('#');
    if (raute != std::string::npos) zeile.erase(raute);
    zeile = trim(zeile);
    if (zeile.empty()) continue;
    const auto gleich = zeile.find('=');
    if (gleich == std::string::npos) {
      fehler = "Zeile " + std::to_string(nr) + ": '=' fehlt";
      return false;
    }
    const std::string key = trim(zeile.substr(0, gleich));
    const std::string val = trim(zeile.substr(gleich + 1));
    double d = 0;
    bool ok = true;
    if (key == "schwelle") {
      ok = zahl(val, 0.0, 0.99, d) && (d == 0.0 || d >= 0.40);
      neu.schwelle = static_cast<float>(d);
    } else if (key == "kamera") {
      ok = val.empty() ||
           (val.rfind("/dev/", 0) == 0 && val.size() < 256 && val.find("..") == std::string::npos);
      neu.kamera = val;
    } else if (key == "mindest_treffer") {
      ok = zahl(val, 1, 10, d);
      neu.mindest_treffer = static_cast<int>(d);
    } else if (key == "ohne_gesicht_ms") {
      ok = zahl(val, 300, 5000, d);
      neu.ohne_gesicht_ms = static_cast<int>(d);
    } else if (key == "gesamt_ms") {
      ok = zahl(val, 500, 2900, d);
      neu.gesamt_ms = static_cast<int>(d);
    } else if (key == "sperre_nach") {
      ok = zahl(val, 1, 50, d);
      neu.sperre_nach = static_cast<int>(d);
    } else if (key == "sitzungspruefung") {
      ok = val == "ja" || val == "nein";
      neu.sitzungspruefung = val != "nein";
    } else if (key == "blinkpruefung") {
      ok = val == "ja" || val == "nein";
      neu.blinkpruefung = val != "nein";
    } else if (key == "keepassxc") {
      ok = val == "ja" || val == "nein";
      neu.keepassxc = val == "ja";
    } else if (key == "keepassxc_geste") {
      ok = val == "ja" || val == "nein";
      neu.keepassxc_geste = val != "nein";
    } else if (key == "sudo") {
      ok = val == "ja" || val == "nein";
      neu.sudo = val == "ja";
    } else if (key == "sudo_ms") {
      ok = zahl(val, 3000, 9500, d);  // unter dem Zeitlimit des PAM-Moduls (10 s)
      neu.sudo_ms = static_cast<int>(d);
    } else if (key == "threads") {
      ok = zahl(val, 1, 16, d);
      neu.threads = static_cast<int>(d);
    } else if (key == "blink_abstand") {
      ok = zahl(val, 0, 200, d);
      neu.blink_abstand = static_cast<float>(d);
    } else {
      fehler = "Zeile " + std::to_string(nr) + ": unbekannter Schlüssel '" + key + "'";
      return false;
    }
    if (!ok) {
      fehler = "Zeile " + std::to_string(nr) + ": ungültiger Wert für '" + key + "'";
      return false;
    }
  }
  k = neu;
  return true;
}

}  // namespace winky
