#include "vorlagen.h"

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstring>
#include <functional>

namespace winky {

namespace {

bool sicher(int fd, bool verzeichnis, std::string& fehler, const char* was) {
  struct stat st {};
  if (fstat(fd, &st) != 0) {
    fehler = std::string(was) + ": fstat fehlgeschlagen";
    return false;
  }
  if (verzeichnis ? !S_ISDIR(st.st_mode) : !S_ISREG(st.st_mode)) {
    fehler = std::string(was) + ": falscher Dateityp";
    return false;
  }
  if (st.st_uid != 0 || (st.st_mode & (S_IWGRP | S_IWOTH))) {
    fehler = std::string(was) + ": unsicherer Besitzer oder Rechte";
    return false;
  }
  return true;
}

struct Fd {
  int fd = -1;
  ~Fd() {
    if (fd >= 0) ::close(fd);
  }
};

}  // namespace

bool pruefeVorlagen(const std::vector<uint8_t>& roh, Vorlagen& v, std::string& fehler) {
  if (roh.size() < kVorlagenKopf) {
    fehler = "Vorlagen: zu kurz";
    return false;
  }
  uint32_t version, dim, anzahl;
  std::memcpy(&version, &roh[4], 4);
  std::memcpy(&dim, &roh[8], 4);
  std::memcpy(&anzahl, &roh[12], 4);
  if (std::memcmp(roh.data(), "WNKV", 4) != 0 || version != 1) {
    fehler = "Vorlagen: unbekanntes Format";
    return false;
  }
  if (dim != kVorlagenDim || anzahl == 0 || anzahl > kVorlagenMax) {
    fehler = "Vorlagen: ungültige Größe";
    return false;
  }
  if (std::memcmp(&roh[16], kErkennungsModellSha, 64) != 0) {
    fehler = "Vorlagen gehören zu einem anderen Erkennungsmodell, bitte neu einlernen";
    return false;
  }
  if (roh.size() != kVorlagenKopf + static_cast<size_t>(dim) * anzahl * sizeof(float)) {
    fehler = "Vorlagen: Länge passt nicht";
    return false;
  }
  Vorlagen neu;
  neu.dim = dim;
  std::memcpy(&neu.erstellt, &roh[80], 8);
  neu.daten.resize(static_cast<size_t>(dim) * anzahl);
  std::memcpy(neu.daten.data(), &roh[kVorlagenKopf], neu.daten.size() * sizeof(float));
  for (size_t i = 0; i < anzahl; ++i) {
    double n = 0;
    for (size_t k = 0; k < dim; ++k) {
      const float x = neu.daten[i * dim + k];
      if (!std::isfinite(x)) {
        fehler = "Vorlagen: ungültige Zahl";
        return false;
      }
      n += static_cast<double>(x) * x;
    }
    if (std::fabs(std::sqrt(n) - 1.0) > 1e-3) {
      fehler = "Vorlagen: Vektor nicht normiert";
      return false;
    }
  }
  v = std::move(neu);
  return true;
}

bool ladeVorlagen(const std::string& basis, uid_t uid, Vorlagen& v, std::string& fehler) {
  Fd b, u, f;
  b.fd = ::open(basis.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (b.fd < 0 || !sicher(b.fd, true, fehler, "Vorlagenordner")) {
    if (b.fd < 0) fehler = "Vorlagenordner fehlt";
    return false;
  }
  const std::string name = std::to_string(uid);
  u.fd = ::openat(b.fd, name.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (u.fd < 0) {
    fehler = "keine Vorlagen für diesen Benutzer";
    return false;
  }
  if (!sicher(u.fd, true, fehler, "Benutzerordner")) return false;
  f.fd = ::openat(u.fd, "vorlagen.bin", O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  if (f.fd < 0) {
    fehler = "keine Vorlagen für diesen Benutzer";
    return false;
  }
  if (!sicher(f.fd, false, fehler, "Vorlagendatei")) return false;
  struct stat st {};
  fstat(f.fd, &st);
  const size_t max = kVorlagenKopf + kVorlagenDim * kVorlagenMax * sizeof(float);
  if (st.st_size <= 0 || static_cast<size_t>(st.st_size) > max) {
    fehler = "Vorlagendatei hat unplausible Größe";
    return false;
  }
  std::vector<uint8_t> roh(static_cast<size_t>(st.st_size));
  size_t gelesen = 0;
  while (gelesen < roh.size()) {
    const ssize_t n = ::read(f.fd, roh.data() + gelesen, roh.size() - gelesen);
    if (n <= 0) {
      if (n < 0 && errno == EINTR) continue;
      fehler = "Vorlagendatei unvollständig";
      return false;
    }
    gelesen += static_cast<size_t>(n);
  }
  return pruefeVorlagen(roh, v, fehler);
}

float bewerte(const std::vector<float>& merkmal, const Vorlagen& v) {
  if (merkmal.size() != v.dim || v.anzahl() == 0) return -1.0f;
  std::vector<float> werte(v.anzahl());
  for (size_t i = 0; i < v.anzahl(); ++i) {
    double s = 0;
    const float* z = v.zeile(i);
    for (size_t k = 0; k < v.dim; ++k) s += static_cast<double>(merkmal[k]) * z[k];
    werte[i] = static_cast<float>(s);
  }
  std::sort(werte.begin(), werte.end(), std::greater<float>());
  const size_t k = std::min<size_t>(3, werte.size());
  float summe = 0;
  for (size_t i = 0; i < k; ++i) summe += werte[i];
  return summe / static_cast<float>(k);
}

}  // namespace winky
