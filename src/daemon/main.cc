// winky-matcher: Prüfdienst für die Gesichtsentsperrung.
//
// systemd startet je Verbindung auf /run/winky.sock eine Instanz
// (winky@.service, StandardInput=socket). Der Dienst läuft als _winky in
// einer Sandbox ohne Netz, ohne Home und nur mit Zugriff auf Videogeräte.
// Er liest nur root-eigene Dateien und schreibt nur den Fehlversuchszähler.
//
// Optionen (nur über die Unit-Datei, also root-kontrolliert):
//   --konfig PFAD  --vorlagen-basis PFAD  --sperre-basis PFAD  --modelle ORDNER
//   --polkit   Zugang über /run/winky-polkit.sock: Aufrufer root oder polkitd,
//              nur die Operation KEEPASSXC
//   --anfrage-basis PFAD  Ordner für Hinweisdateien offener sudo-Anfragen
//
// SUDO (sudo bestätigen) braucht zusätzlich: Schalter sudo = ja in der Konfiguration
// und /etc/winky/sudo-ein (root), einen erfolgreichen ✌-Test des Benutzers
// (/var/lib/winky/<uid>/geste-ok), ein Terminal ohne entfernte Sitzung. Erkannt ist es
// erst bei Gesicht UND Handzeichen ✌ neben demselben Gesicht.

#include <dirent.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <pwd.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdarg>
#include <cstdio>
#include <climits>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <thread>
#include <vector>

#include "entscheidung.h"
#include "face_align.h"
#include "face_detection.h"
#include "face_embedding.h"
#include "face_quality.h"
#include "anfrage.h"
#include "hand_gesture.h"
#include "konfig.h"
#include "protokoll.h"
#include "sitzung.h"
#include "sperre.h"
#include "v4l2_ir.h"
#include "vorlagen.h"

namespace {

using Clock = std::chrono::steady_clock;

double msSeit(Clock::time_point t0) {
  return std::chrono::duration<double, std::milli>(Clock::now() - t0).count();
}

// Ausgabe ins Journal mit Priorität (sd-daemon-Präfix)
void log(int prio, const char* fmt, ...) {
  std::fprintf(stderr, "<%d>", prio);
  va_list ap;
  va_start(ap, fmt);
  std::vfprintf(stderr, fmt, ap);
  va_end(ap);
  std::fputc('\n', stderr);
  std::fflush(stderr);
}

struct Optionen {
  std::string konfig = winky::kKonfigPfad;
  std::string vorlagen = winky::kVorlagenBasis;
  std::string sperre = winky::kSperreBasis;
  std::string modelle = "/usr/share/winky/models";
  std::string anfrage = winky::kAnfrageBasis;
  std::string sudo_schalter = "/etc/winky/sudo-ein";
  bool polkit = false;
};

const char* statusText(uint32_t s) {
  switch (s) {
    case WINKY_TREFFER: return "treffer";
    case WINKY_KEIN_TREFFER: return "kein_treffer";
    case WINKY_KEIN_GESICHT: return "kein_gesicht";
    case WINKY_NICHT_EINGERICHTET: return "nicht_eingerichtet";
    case WINKY_GESPERRT: return "gesperrt";
    case WINKY_ABGELEHNT: return "abgelehnt";
    case WINKY_OK: return "ok";
    default: return "fehler";
  }
}

// Vorschau höchstens WINKY_VORSCHAU_MAX_BREITE breit (ganzzahlig verkleinert)
int vorschauFaktor(int breite) {
  return std::max(1, (breite + WINKY_VORSCHAU_MAX_BREITE - 1) / WINKY_VORSCHAU_MAX_BREITE);
}

std::string jsonText(const std::string& s) {
  std::string o = "\"";
  for (unsigned char c : s) {
    if (c == '"' || c == '\\') {
      o += '\\';
      o += static_cast<char>(c);
    } else if (c >= 0x20) {
      o += static_cast<char>(c);
    }
  }
  return o + "\"";
}

// --------------------------------------------------------------------------
// Verbindung zum Aufrufer (fd 0, SOCK_SEQPACKET)
// --------------------------------------------------------------------------

class Verbindung {
 public:
  explicit Verbindung(int fd) : fd_(fd) {}

  bool senden(const void* daten, size_t laenge) {
    return ::send(fd_, daten, laenge, MSG_NOSIGNAL) == static_cast<ssize_t>(laenge);
  }

  bool antwort(uint32_t status, float wert, double dauer_ms, bool strom) {
    winky_antwort a{WINKY_MAGIC, status, wert, static_cast<uint32_t>(std::max(0.0, dauer_ms))};
    if (!strom) return senden(&a, sizeof(a));
    std::vector<uint8_t> b(1 + sizeof(a));
    b[0] = 'E';
    std::memcpy(&b[1], &a, sizeof(a));
    return senden(b.data(), b.size());
  }

  bool status(const std::string& json) {
    std::string b = "S" + json;
    return senden(b.data(), b.size());
  }

  bool bild(const winky::GrayImage& img) {
    if (img.empty()) return true;
    const int f = vorschauFaktor(img.width);
    const int w = img.width / f, h = img.height / f;
    std::vector<uint8_t> b(5 + static_cast<size_t>(w) * h);
    b[0] = 'B';
    const uint16_t ww = static_cast<uint16_t>(w), hh = static_cast<uint16_t>(h);
    std::memcpy(&b[1], &ww, 2);
    std::memcpy(&b[3], &hh, 2);
    for (int y = 0; y < h; ++y) {
      for (int x = 0; x < w; ++x) {
        int summe = 0;
        for (int dy = 0; dy < f; ++dy)
          for (int dx = 0; dx < f; ++dx) summe += img.at(y * f + dy, x * f + dx);
        b[5 + static_cast<size_t>(y) * w + x] = static_cast<uint8_t>(summe / (f * f));
      }
    }
    return senden(b.data(), b.size());
  }

  // Der Aufrufer hat aufgelegt (Abbruch in der Oberfläche)
  bool getrennt() {
    pollfd p{fd_, POLLIN, 0};
    if (::poll(&p, 1, 0) <= 0) return false;
    if (p.revents & (POLLHUP | POLLERR)) return true;
    char c;
    return ::recv(fd_, &c, 1, MSG_DONTWAIT | MSG_PEEK) == 0;
  }

 private:
  int fd_;
};

// --------------------------------------------------------------------------
// Kamera und Modelle
// --------------------------------------------------------------------------

struct Laufzeit {
  Ort::Env env{ORT_LOGGING_LEVEL_ERROR, "winky"};
  std::unique_ptr<winky::FaceDetector> detektor;
  std::unique_ptr<winky::FaceEmbedder> erkennung;
  std::unique_ptr<winky::V4l2IrCamera> kamera;
  std::unique_ptr<winky::HandGestureRecognizer> hand;  // nur für SUDO und GESTE_TESTEN
  std::string fehler;
};

bool starte(const Optionen& o, const winky::Konfig& k, Laufzeit& l, bool mit_hand = false) {
  std::string modell_fehler;
  std::thread lader([&] {
    try {
      if (mit_hand)
        l.hand = std::make_unique<winky::HandGestureRecognizer>(l.env, o.modelle, k.threads, 0.5f);
      l.detektor = std::make_unique<winky::FaceDetector>(l.env, o.modelle + "/face_detection_yunet_2023mar.onnx",
                                                       k.threads, 0.5f);
      l.erkennung = std::make_unique<winky::FaceEmbedder>(
          l.env, o.modelle + "/face_recognition_sface_2021dec.onnx", k.threads);
      if (l.erkennung->dim() != static_cast<int>(winky::kVorlagenDim))
        modell_fehler = "Erkennungsmodell hat falsche Dimension";
    } catch (const std::exception& e) {
      modell_fehler = e.what();
    }
  });
  if (k.kamera.empty()) {
    lader.join();
    l.fehler = "Noch keine Kamera eingerichtet";
    return false;
  }
  l.kamera = std::make_unique<winky::V4l2IrCamera>(k.kamera);
  std::string kamera_fehler;
  const bool ok = l.kamera->start(640, 360, kamera_fehler);
  lader.join();
  if (!ok) {
    l.fehler = "Kamera: " + kamera_fehler;
    return false;
  }
  if (!modell_fehler.empty()) {
    l.fehler = "Modelle: " + modell_fehler;
    return false;
  }
  return true;
}

struct Bildanalyse {
  bool gesicht = false;
  int gesichter = 0;
  winky::FaceBox box;
  winky::FaceQuality qualitaet;
  std::vector<float> merkmal;
};

Bildanalyse analysiere(Laufzeit& l, const winky::GrayImage& img) {
  Bildanalyse a;
  static const winky::QualityLimits grenzen;
  const auto gesichter = l.detektor->detect(img);
  a.gesichter = static_cast<int>(gesichter.size());
  if (gesichter.empty()) return a;
  a.gesicht = true;
  a.box = gesichter.front();
  a.qualitaet = winky::assessFace(img, a.box, grenzen);
  if (a.qualitaet.usable) a.merkmal = l.erkennung->embed(winky::alignFace(img, a.box.kps));
  return a;
}

std::string zahl(double v, int stellen = 3) {
  char b[32];
  std::snprintf(b, sizeof(b), "%.*f", stellen, v);
  return b;
}

std::string statusJson(const char* modus, double t, int dauer, const Bildanalyse& a, float wert,
                       int gesammelt, int bildbreite) {
  const float f = static_cast<float>(vorschauFaktor(bildbreite));
  std::string s = std::string("{\"modus\":\"") + modus + "\",\"t\":" + zahl(t / 1000.0, 1) +
                  ",\"dauer\":" + std::to_string(dauer) + ",\"gesicht\":" +
                  (a.gesicht ? "true" : "false") + ",\"grund\":\"" +
                  (a.gesicht ? a.qualitaet.reason : "kein_gesicht") + "\"";
  if (wert > -1) s += ",\"wert\":" + zahl(wert);
  if (gesammelt >= 0) s += ",\"gesammelt\":" + std::to_string(gesammelt);
  if (a.gesicht) {
    s += ",\"rahmen\":[" + zahl(a.box.x1 / f, 0) + "," + zahl(a.box.y1 / f, 0) + "," +
         zahl(a.box.x2 / f, 0) + "," + zahl(a.box.y2 / f, 0) + "]";
  }
  return s + "}";
}

// --------------------------------------------------------------------------
// Prüfung (AUTH und TESTEN)
// --------------------------------------------------------------------------

struct Pruefergebnis {
  uint32_t status = WINKY_FEHLER;
  float wert = -1;
  bool gesicht_gesehen = false;
  bool gesicht_erkannt = false;  // nur Geste: Gesicht passte, Zeichen fehlte womöglich
  bool abgebrochen = false;
};

Pruefergebnis pruefe(Laufzeit& l, const winky::Vorlagen& v, const winky::Regeln& r,
                     Clock::time_point t0, Verbindung* strom, int dauer_s) {
  Pruefergebnis erg;
  winky::Entscheidung e(r);
  winky::StrobeTracker blink;
  winky::IrFrame bild, vorher;
  bool vorher_dunkel = false;
  std::string fehler;
  winky::Ergebnis stand = winky::Ergebnis::Offen;
  while (stand == winky::Ergebnis::Offen) {
    if (strom && strom->getrennt()) {
      erg.abgebrochen = true;
      return erg;
    }
    const double rest = r.gesamt_ms - msSeit(t0);
    if (rest <= 0) {
      stand = e.zeit(msSeit(t0));
      break;
    }
    if (!l.kamera->read(bild, static_cast<int>(std::min(rest, 500.0)) + 1, fehler)) {
      stand = e.zeit(msSeit(t0));
      if (stand == winky::Ergebnis::Offen && fehler.find("Zeitüberschreitung") == std::string::npos) {
        log(4, "Kamera meldet: %s", fehler.c_str());
        erg.status = WINKY_FEHLER;
        return erg;
      }
      continue;
    }
    if (!blink.push(bild.mean).lit) {
      vorher = bild;
      vorher_dunkel = true;
      stand = e.zeit(msSeit(t0));
      continue;
    }
    const Bildanalyse a = analysiere(l, bild.image);
    winky::Beobachtung b;
    b.t_ms = msSeit(t0);
    b.gesicht = a.gesicht;
    b.brauchbar = !a.merkmal.empty();
    if (a.gesicht) {
      b.rahmen = {a.box.x1, a.box.y1, a.box.x2, a.box.y2};
      b.hell_gesicht = winky::regionMean(bild.image, a.box);
      b.dunkel_gesicht = vorher_dunkel ? winky::regionMean(vorher.image, a.box) : -1.0f;
    }
    if (b.brauchbar) b.wert = winky::bewerte(a.merkmal, v);
    vorher_dunkel = false;
    stand = e.neu(b);
    if (strom) {  // erst der Stand (mit Rahmen), dann das Bild dazu
      strom->status(statusJson("testen", b.t_ms, dauer_s, a, b.wert, -1, bild.image.width));
      strom->bild(bild.image);
    }
  }
  erg.wert = e.besterWert();
  erg.gesicht_gesehen = e.gesichtGesehen();
  erg.status = stand == winky::Ergebnis::Treffer       ? WINKY_TREFFER
               : stand == winky::Ergebnis::KeinTreffer ? WINKY_KEIN_TREFFER
                                                     : WINKY_KEIN_GESICHT;
  return erg;
}

// --------------------------------------------------------------------------
// Prüfung mit Handzeichen (SUDO und GESTE_TESTEN)
// --------------------------------------------------------------------------

const char* kGesten[winky::kGestureCount] = {"keine", "Faust", "offene Hand", "Zeigefinger hoch",
                                           "Daumen runter", "Daumen hoch", "Victory", "I love you"};

Pruefergebnis pruefeGeste(Laufzeit& l, const winky::Vorlagen& v, const winky::Regeln& r,
                          Clock::time_point t0, Verbindung* strom, int dauer_s,
                          const std::function<bool()>& abbrechen) {
  Pruefergebnis erg;
  winky::GestenEntscheidung e(r, winky::GestenRegeln{});
  winky::StrobeTracker blink;
  winky::IrFrame bild, vorher;
  bool vorher_dunkel = false;
  std::string fehler;
  winky::Ergebnis stand = winky::Ergebnis::Offen;
  while (stand == winky::Ergebnis::Offen) {
    if ((strom && strom->getrennt()) || abbrechen()) {
      erg.abgebrochen = true;
      return erg;
    }
    const double rest = r.gesamt_ms - msSeit(t0);
    if (rest <= 0) {
      stand = e.zeit(msSeit(t0));
      break;
    }
    if (!l.kamera->read(bild, static_cast<int>(std::min(rest, 500.0)) + 1, fehler)) {
      stand = e.zeit(msSeit(t0));
      if (stand == winky::Ergebnis::Offen && fehler.find("Zeitüberschreitung") == std::string::npos) {
        log(4, "Kamera meldet: %s", fehler.c_str());
        erg.status = WINKY_FEHLER;
        return erg;
      }
      continue;
    }
    if (!blink.push(bild.mean).lit) {
      vorher = bild;
      vorher_dunkel = true;
      stand = e.zeit(msSeit(t0));
      continue;
    }
    const Bildanalyse a = analysiere(l, bild.image);
    winky::Beobachtung b;
    b.t_ms = msSeit(t0);
    b.gesicht = a.gesicht;
    b.brauchbar = !a.merkmal.empty();
    if (a.gesicht) {
      b.rahmen = {a.box.x1, a.box.y1, a.box.x2, a.box.y2};
      b.hell_gesicht = winky::regionMean(bild.image, a.box);
      b.dunkel_gesicht = vorher_dunkel ? winky::regionMean(vorher.image, a.box) : -1.0f;
    }
    if (b.brauchbar) b.wert = winky::bewerte(a.merkmal, v);
    vorher_dunkel = false;
    // Handzeichen: wie in der Messung (auswerten_hand.py) ✌ als wahrscheinlichste Geste
    // ab 0,5 bei sicher erkannter Hand
    const winky::HandResult h = l.hand->analyse(bild.image);
    int top = 0;
    for (int i = 1; i < winky::kGestureCount; ++i)
      if (h.gesture[i] > h.gesture[top]) top = i;
    winky::HandBeobachtung hb;
    hb.zeichen = h.found && h.presence >= 0.5f && top == winky::kVictory && h.gesture[top] >= 0.5f;
    if (h.found) {
      for (int i = 0; i < winky::kHandPoints; ++i) {
        hb.x += h.pts[i * 2] / winky::kHandPoints;
        hb.y += h.pts[i * 2 + 1] / winky::kHandPoints;
      }
    }
    stand = e.neu(b, a.gesichter, hb);
    if (strom) {
      std::string st = statusJson("geste", b.t_ms, dauer_s, a, b.wert, -1, bild.image.width);
      st.pop_back();
      st += std::string(",\"hand\":") + (h.found ? "true" : "false") +
            ",\"geste\":" + (h.found ? jsonText(kGesten[top]) : "null") +
            ",\"zeichen\":" + (hb.zeichen ? "true" : "false") +
            ",\"gesichter\":" + std::to_string(a.gesichter) +
            ",\"gesicht_erkannt\":" + (e.gesichtErkannt() ? "true" : "false") + "}";
      strom->status(st);
      strom->bild(bild.image);
    }
  }
  erg.wert = e.besterWert();
  erg.gesicht_gesehen = e.gesichtGesehen();
  erg.gesicht_erkannt = e.gesichtErkannt();
  erg.status = stand == winky::Ergebnis::Treffer       ? WINKY_TREFFER
               : stand == winky::Ergebnis::KeinTreffer ? WINKY_KEIN_TREFFER
                                                     : WINKY_KEIN_GESICHT;
  return erg;
}

// Datei root-eigen und regulär (keine Verknüpfung)? Für Schalter und Freigaben.
bool rootDatei(const std::string& pfad) {
  struct stat st {};
  return ::lstat(pfad.c_str(), &st) == 0 && S_ISREG(st.st_mode) && st.st_uid == 0 &&
         !(st.st_mode & (S_IWGRP | S_IWOTH));
}

// ✌-Test bestanden: /var/lib/winky/<uid>/geste-ok, root-eigen (vom Verwaltungshelfer)
bool gesteFreigegeben(const std::string& basis, uid_t uid) {
  const int dir = ::open((basis + "/" + std::to_string(uid)).c_str(),
                         O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (dir < 0) return false;
  struct stat st {};
  const bool ok = ::fstatat(dir, "geste-ok", &st, AT_SYMLINK_NOFOLLOW) == 0 &&
                  S_ISREG(st.st_mode) && st.st_uid == 0;
  ::close(dir);
  return ok;
}

// --------------------------------------------------------------------------
// Einlernen
// --------------------------------------------------------------------------

int einlernen(Laufzeit& l, Verbindung& c, int dauer_s, Clock::time_point t0) {
  struct Probe {
    std::vector<float> m;
  };
  std::vector<Probe> proben;
  winky::StrobeTracker blink;
  winky::IrFrame bild;
  std::string fehler;
  const auto start = Clock::now();
  while (msSeit(start) < dauer_s * 1000.0) {
    if (c.getrennt()) return -1;
    if (!l.kamera->read(bild, 2000, fehler)) {
      log(4, "Kamera meldet beim Einlernen: %s", fehler.c_str());
      c.antwort(WINKY_FEHLER, -1, msSeit(t0), true);
      return 1;
    }
    if (!blink.push(bild.mean).lit) continue;
    const Bildanalyse a = analysiere(l, bild.image);
    if (!a.merkmal.empty()) proben.push_back({a.merkmal});
    c.status(statusJson("einlernen", msSeit(start), dauer_s, a, -1,
                        static_cast<int>(proben.size()), bild.image.width));
    c.bild(bild.image);
  }
  if (proben.size() < 8) {
    c.antwort(WINKY_KEIN_GESICHT, -1, msSeit(t0), true);
    return 1;
  }
  // Ausreißer entfernen (Ähnlichkeit zum Mittel unter Median - 3 * MAD)
  const size_t dim = proben.front().m.size();
  std::vector<float> mittel(dim, 0.0f);
  for (const auto& p : proben)
    for (size_t k = 0; k < dim; ++k) mittel[k] += p.m[k];
  double n = 0;
  for (float x : mittel) n += static_cast<double>(x) * x;
  n = std::sqrt(n);
  for (float& x : mittel) x = static_cast<float>(x / n);
  std::vector<float> sims;
  for (const auto& p : proben) sims.push_back(winky::cosine(p.m, mittel.data()));
  std::vector<float> sortiert = sims;
  std::sort(sortiert.begin(), sortiert.end());
  const float median = sortiert[sortiert.size() / 2];
  std::vector<float> abw;
  for (float s : sims) abw.push_back(std::fabs(s - median));
  std::sort(abw.begin(), abw.end());
  const float mad = std::max(abw[abw.size() / 2], 0.02f);
  std::vector<const Probe*> behalten;
  for (size_t i = 0; i < proben.size(); ++i)
    if (sims[i] >= median - 3.0f * mad) behalten.push_back(&proben[i]);

  const uint32_t anzahl = static_cast<uint32_t>(std::min<size_t>(30, behalten.size()));
  const uint32_t d = static_cast<uint32_t>(dim);
  std::vector<uint8_t> b(1 + 8 + 64 + static_cast<size_t>(anzahl) * dim * sizeof(float));
  b[0] = 'V';
  std::memcpy(&b[1], &anzahl, 4);
  std::memcpy(&b[5], &d, 4);
  std::memcpy(&b[9], winky::kErkennungsModellSha, 64);
  size_t pos = 73;
  for (uint32_t i = 0; i < anzahl; ++i) {
    const size_t idx = anzahl == 1 ? 0 : i * (behalten.size() - 1) / (anzahl - 1);
    std::memcpy(&b[pos], behalten[idx]->m.data(), dim * sizeof(float));
    pos += dim * sizeof(float);
  }
  if (!c.senden(b.data(), b.size())) return 1;
  c.antwort(WINKY_OK, -1, msSeit(t0), true);
  log(6, "Einlernen: %zu brauchbare Bilder, %u Vorlagen übergeben", proben.size(), anzahl);
  return 0;
}

// --------------------------------------------------------------------------
// Kamerasuche: alle Videogeräte mit Graustufenformat kurz anlaufen lassen und
// prüfen, ob ein IR-Strahler leuchtet und ob er blinkt.
// --------------------------------------------------------------------------

bool hatGraustufen(const std::string& geraet, std::string& name) {
  const int fd = ::open(geraet.c_str(), O_RDWR | O_NONBLOCK | O_CLOEXEC);
  if (fd < 0) return false;
  v4l2_capability cap{};
  bool ok = ::ioctl(fd, VIDIOC_QUERYCAP, &cap) == 0;
  const uint32_t caps = (cap.capabilities & V4L2_CAP_DEVICE_CAPS) ? cap.device_caps : cap.capabilities;
  ok = ok && (caps & V4L2_CAP_VIDEO_CAPTURE) && (caps & V4L2_CAP_STREAMING);
  bool grau = false;
  if (ok) {
    name = reinterpret_cast<const char*>(cap.card);
    v4l2_fmtdesc d{};
    d.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    for (d.index = 0; d.index < 32 && ::ioctl(fd, VIDIOC_ENUM_FMT, &d) == 0; ++d.index)
      if (d.pixelformat == V4L2_PIX_FMT_GREY) grau = true;
  }
  ::close(fd);
  return grau;
}

// /dev/videoN -> stabiler Pfad unter /dev/v4l/by-path (ohne "usbv2"-Doppel)
std::map<std::string, std::string> stabilePfade() {
  std::map<std::string, std::string> m;
  DIR* d = ::opendir("/dev/v4l/by-path");
  if (!d) return m;
  while (dirent* e = ::readdir(d)) {
    if (e->d_name[0] == '.') continue;
    const std::string pfad = std::string("/dev/v4l/by-path/") + e->d_name;
    char ziel[PATH_MAX];
    if (!::realpath(pfad.c_str(), ziel)) continue;
    auto it = m.find(ziel);
    if (it == m.end() || (it->second.find("usbv2") != std::string::npos &&
                          pfad.find("usbv2") == std::string::npos))
      m[ziel] = pfad;
  }
  ::closedir(d);
  return m;
}

std::string kameraSuche() {
  const auto stabil = stabilePfade();
  std::string json = "[";
  for (int i = 0; i < 64; ++i) {
    const std::string geraet = "/dev/video" + std::to_string(i);
    if (::access(geraet.c_str(), F_OK) != 0) continue;
    std::string name;
    if (!hatGraustufen(geraet, name)) continue;
    const auto it = stabil.find(geraet);
    const std::string pfad = it != stabil.end() ? it->second : geraet;
    winky::V4l2IrCamera cam(geraet);
    std::string fehler;
    std::string eintrag = "{\"geraet\":" + jsonText(geraet) + ",\"pfad\":" + jsonText(pfad) +
                          ",\"name\":" + jsonText(name);
    if (!cam.start(640, 360, fehler)) {
      eintrag += ",\"fehler\":" + jsonText(fehler) + "}";
    } else {
      winky::StrobeTracker blink;
      winky::IrFrame bild;
      double hell = 0, dunkel = 0;
      int n_hell = 0, n_dunkel = 0;
      bool blinkt = false;
      for (int j = 0; j < 16 && cam.read(bild, 1500, fehler); ++j) {
        const auto r = blink.push(bild.mean);
        if (j < 2) continue;  // Einschwingen
        blinkt = blinkt || r.strobing;
        if (r.lit) {
          hell += bild.mean;
          ++n_hell;
        } else {
          dunkel += bild.mean;
          ++n_dunkel;
        }
      }
      eintrag += ",\"breite\":" + std::to_string(cam.width()) + ",\"hoehe\":" +
                 std::to_string(cam.height()) + ",\"blinkt\":" +
                 (blinkt && n_dunkel > 0 ? "true" : "false") + ",\"hell\":" +
                 zahl(n_hell ? hell / n_hell : 0, 1) + ",\"dunkel\":" +
                 zahl(n_dunkel ? dunkel / n_dunkel : 0, 1) + "}";
      cam.stop();
    }
    if (json.size() > 1) json += ",";
    json += eintrag;
  }
  return json + "]";
}

}  // namespace

int main(int argc, char** argv) {
  const auto t0 = Clock::now();
  std::signal(SIGPIPE, SIG_IGN);
  Optionen o;
  for (int i = 1; i < argc; ++i) {
    if (std::string(argv[i]) == "--polkit") {
      o.polkit = true;
      continue;
    }
    if (i + 1 >= argc) {
      log(3, "Option %s ohne Wert", argv[i]);
      return 2;
    }
    const std::string a = argv[i++];
    if (a == "--konfig") o.konfig = argv[i];
    else if (a == "--vorlagen-basis") o.vorlagen = argv[i];
    else if (a == "--sperre-basis") o.sperre = argv[i];
    else if (a == "--modelle") o.modelle = argv[i];
    else if (a == "--anfrage-basis") o.anfrage = argv[i];
    else if (a == "--sudo-schalter") o.sudo_schalter = argv[i];
    else {
      log(3, "Unbekannte Option %s", a.c_str());
      return 2;
    }
  }

  // Verbindung kommt als fd 0 (StandardInput=socket)
  struct stat st {};
  if (fstat(0, &st) != 0 || !S_ISSOCK(st.st_mode)) {
    log(3, "fd 0 ist kein Socket, Start nur über winky.socket");
    return 2;
  }
  Verbindung c(0);
  ucred cred{};
  socklen_t len = sizeof(cred);
  // Hauptzugang: nur root. Polkit-Zugang: root oder der Systembenutzer polkitd.
  uid_t polkitd = static_cast<uid_t>(-1);
  if (o.polkit) {
    passwd ppw{}, *pp = nullptr;
    char pbuf[1024];
    if (getpwnam_r("polkitd", &ppw, pbuf, sizeof(pbuf), &pp) == 0 && pp) polkitd = ppw.pw_uid;
  }
  if (getsockopt(0, SOL_SOCKET, SO_PEERCRED, &cred, &len) != 0 ||
      (cred.uid != 0 && !(o.polkit && cred.uid == polkitd))) {
    log(4, "Anfrage von uid %d abgelehnt", static_cast<int>(cred.uid));
    c.antwort(WINKY_ABGELEHNT, -1, msSeit(t0), false);
    return 1;
  }

  winky_anfrage q{};
  pollfd p{0, POLLIN, 0};
  if (::poll(&p, 1, 1000) <= 0 || ::recv(0, &q, sizeof(q), 0) != sizeof(q) || q.magic != WINKY_MAGIC) {
    log(4, "Ungültige oder fehlende Anfrage");
    return 1;
  }
  const bool strom = q.op == WINKY_OP_EINLERNEN || q.op == WINKY_OP_TESTEN || q.op == WINKY_OP_KAMERAS ||
                     q.op == WINKY_OP_GESTE_TESTEN;
  passwd pw{}, *pwp = nullptr;
  char puffer[4096];
  if (q.uid == 0 || getpwuid_r(q.uid, &pw, puffer, sizeof(puffer), &pwp) != 0 || !pwp) {
    log(4, "Anfrage für unbekannten oder root-Benutzer abgelehnt");
    c.antwort(WINKY_ABGELEHNT, -1, msSeit(t0), strom);
    return 1;
  }
  const uid_t uid = q.uid;
  if (o.polkit && q.op != WINKY_OP_KEEPASSXC) {
    log(4, "Über den Polkit-Zugang ist nur KEEPASSXC erlaubt");
    c.antwort(WINKY_ABGELEHNT, -1, msSeit(t0), strom);
    return 1;
  }

  if (q.op == WINKY_OP_KAMERAS) {
    const std::string liste = kameraSuche();
    c.status("{\"kameras\":" + liste + "}");
    c.antwort(WINKY_OK, -1, msSeit(t0), true);
    log(6, "Kamerasuche: %s", liste.c_str());
    return 0;
  }

  if (q.op == WINKY_OP_RESET) {
    winky::schreibeFehlversuche(o.sperre, uid, 0);
    winky::schreibeSudoOffen(o.sperre, uid, 0, std::time(nullptr));
    c.antwort(WINKY_OK, -1, msSeit(t0), false);
    return 0;
  }

  winky::Konfig k;
  std::string fehler;
  if (!winky::ladeKonfig(o.konfig, k, fehler)) {
    log(3, "%s", fehler.c_str());
    c.antwort(WINKY_FEHLER, -1, msSeit(t0), strom);
    return 1;
  }

  if (q.op == WINKY_OP_KEEPASSXC && k.keepassxc && k.keepassxc_geste) {
    // KeePassXC nur mit Gesicht und ✌: dieselben Regeln wie sudo (Freigabe per ✌-Test,
    // Desktop-Meldung, gleichzeitige Anfragen brechen ab, Begrenzung). Polkit beendet das
    // Prüfprogramm nach 10 s, das Zeitfenster (sudo_ms) bleibt darunter.
    const std::string befehl = "KeePassXC entsperren";
    const long beginn = static_cast<long>(std::time(nullptr));
    auto ende = [&](uint32_t status, float wert, const char* grund, const char* stand) {
      c.antwort(status, wert, msSeit(t0), false);
      if (stand) winky::schreibeAnfrage(o.anfrage, uid, stand, befehl, "", beginn, "keepassxc");
      log(status == WINKY_TREFFER ? 5 : 6,
          "Ergebnis uid=%u status=%s wert=%s dauer_ms=%.0f zweck=keepassxc geste=1%s%s", uid,
          statusText(status), zahl(wert).c_str(), msSeit(t0), grund ? " grund=" : "",
          grund ? grund : "");
      return status == WINKY_TREFFER ? 0 : 1;
    };
    if (k.schwelle <= 0 || k.kamera.empty())
      return ende(WINKY_NICHT_EINGERICHTET, -1, "nicht_eingerichtet", nullptr);
    if (k.sitzungspruefung) {
      std::string grund;
      if (!winky::hatLokaleGrafischeSitzung(uid, grund)) return ende(WINKY_ABGELEHNT, -1, "sitzung", nullptr);
    }
    if (winky::leseFehlversuche(o.sperre, uid) >= k.sperre_nach)
      return ende(WINKY_GESPERRT, -1, "zu_viele_fehlversuche", nullptr);
    if (winky::leseSudoOffen(o.sperre, uid, beginn) >= winky::kSudoGrenze)
      return ende(WINKY_GESPERRT, -1, "begrenzt", "begrenzt");
    if (!gesteFreigegeben(o.vorlagen, uid))
      return ende(WINKY_NICHT_EINGERICHTET, -1, "geste_nicht_getestet", nullptr);
    winky::Vorlagen v;
    if (!winky::ladeVorlagen(o.vorlagen, uid, v, fehler)) {
      log(6, "%s", fehler.c_str());
      return ende(WINKY_NICHT_EINGERICHTET, -1, "vorlagen", nullptr);
    }
    const int sperre = winky::sudoSperren(o.sperre, uid);
    if (sperre < 0) {
      winky::erhoeheSudoOffen(o.sperre, uid, beginn);
      return ende(WINKY_ABGELEHNT, -1, "gleichzeitig", "abgebrochen");
    }
    winky::schreibeAnfrage(o.anfrage, uid, "wartet", befehl, "", beginn, "keepassxc");
    Laufzeit l;
    if (!starte(o, k, l, true)) {
      log(4, "%s", l.fehler.c_str());
      winky::sudoEntsperren(o.sperre, uid, sperre);
      return ende(WINKY_FEHLER, -1, "start", "nicht_bestaetigt");
    }
    const winky::Regeln r{k.schwelle, k.mindest_treffer, static_cast<double>(k.sudo_ms),
                          static_cast<double>(k.sudo_ms), k.blink_abstand, k.blinkpruefung};
    const Pruefergebnis erg = pruefeGeste(l, v, r, t0, nullptr, 0, [&] {
      return winky::sudoAbbruchGesetzt(o.sperre, uid);
    });
    l.kamera->stop();
    winky::sudoEntsperren(o.sperre, uid, sperre);
    const long jetzt = static_cast<long>(std::time(nullptr));
    if (erg.abgebrochen) {
      winky::erhoeheSudoOffen(o.sperre, uid, jetzt);
      return ende(WINKY_ABGELEHNT, -1, "gleichzeitig", "abgebrochen");
    }
    if (erg.status == WINKY_TREFFER) {
      winky::schreibeSudoOffen(o.sperre, uid, 0, jetzt);
      winky::schreibeFehlversuche(o.sperre, uid, 0);
      return ende(WINKY_TREFFER, erg.wert, nullptr, "bestaetigt");
    }
    winky::erhoeheSudoOffen(o.sperre, uid, jetzt);
    if (erg.status == WINKY_KEIN_TREFFER && !erg.gesicht_erkannt)
      winky::schreibeFehlversuche(o.sperre, uid, winky::leseFehlversuche(o.sperre, uid) + 1);
    return ende(erg.status, erg.wert, erg.gesicht_erkannt ? "kein_zeichen" : nullptr,
                "nicht_bestaetigt");
  }

  if (q.op == WINKY_OP_AUTH || q.op == WINKY_OP_KEEPASSXC) {
    const char* zweck = q.op == WINKY_OP_KEEPASSXC ? "keepassxc" : "sperrbildschirm";
    auto ende = [&](uint32_t status, float wert, const char* grund) {
      c.antwort(status, wert, msSeit(t0), false);
      log(status == WINKY_TREFFER ? 5 : 6,
          "Ergebnis uid=%u status=%s wert=%s dauer_ms=%.0f zweck=%s%s%s", uid, statusText(status),
          zahl(wert).c_str(), msSeit(t0), zweck, grund ? " grund=" : "", grund ? grund : "");
      return status == WINKY_TREFFER ? 0 : 1;
    };
    if (q.op == WINKY_OP_KEEPASSXC && !k.keepassxc) return ende(WINKY_ABGELEHNT, -1, "keepassxc_aus");
    if (k.schwelle <= 0) return ende(WINKY_NICHT_EINGERICHTET, -1, "schwelle_fehlt");
    if (k.kamera.empty()) return ende(WINKY_NICHT_EINGERICHTET, -1, "keine_kamera");
    if (k.sitzungspruefung) {
      std::string grund;
      if (!winky::hatLokaleGrafischeSitzung(uid, grund)) return ende(WINKY_ABGELEHNT, -1, "sitzung");
    }
    if (winky::leseFehlversuche(o.sperre, uid) >= k.sperre_nach)
      return ende(WINKY_GESPERRT, -1, "zu_viele_fehlversuche");
    winky::Vorlagen v;
    if (!winky::ladeVorlagen(o.vorlagen, uid, v, fehler)) {
      log(6, "%s", fehler.c_str());
      return ende(WINKY_NICHT_EINGERICHTET, -1, "vorlagen");
    }
    Laufzeit l;
    if (!starte(o, k, l)) {
      log(4, "%s", l.fehler.c_str());
      return ende(WINKY_FEHLER, -1, "start");
    }
    const winky::Regeln r{k.schwelle, k.mindest_treffer, static_cast<double>(k.ohne_gesicht_ms),
                        static_cast<double>(k.gesamt_ms), k.blink_abstand, k.blinkpruefung};
    const Pruefergebnis erg = pruefe(l, v, r, t0, nullptr, 0);
    l.kamera->stop();
    if (erg.status == WINKY_TREFFER) {
      winky::schreibeFehlversuche(o.sperre, uid, 0);
    } else if (erg.status == WINKY_KEIN_TREFFER) {
      winky::schreibeFehlversuche(o.sperre, uid, winky::leseFehlversuche(o.sperre, uid) + 1);
    }
    return ende(erg.status, erg.wert, nullptr);
  }

  if (q.op == WINKY_OP_SUDO) {
    // Zweite Nachricht: 'C' + Terminal + NUL + Befehl + NUL
    std::string terminal, befehl;
    char puf[WINKY_BEFEHL_MAX + 1];
    pollfd pc{0, POLLIN, 0};
    if (::poll(&pc, 1, 500) > 0) {
      const ssize_t n = ::recv(0, puf, sizeof(puf), 0);
      if (n > 1 && puf[0] == 'C' && n <= WINKY_BEFEHL_MAX) {
        const std::string roh(puf + 1, static_cast<size_t>(n - 1));
        const size_t nul = roh.find('\0');
        terminal = winky::saeubern(roh.substr(0, nul), 64);
        if (nul != std::string::npos) befehl = winky::saeubern(roh.substr(nul + 1), 240);
      }
    }
    if (befehl.empty()) befehl = "sudo";
    const long beginn = static_cast<long>(std::time(nullptr));
    auto ende = [&](uint32_t status, float wert, const char* grund, const char* stand) {
      c.antwort(status, wert, msSeit(t0), false);
      if (stand) winky::schreibeAnfrage(o.anfrage, uid, stand, befehl, terminal, beginn);
      log(status == WINKY_TREFFER ? 5 : 6,
          "Ergebnis uid=%u status=%s wert=%s dauer_ms=%.0f zweck=sudo%s%s befehl=%s", uid,
          statusText(status), zahl(wert).c_str(), msSeit(t0), grund ? " grund=" : "",
          grund ? grund : "", jsonText(befehl).c_str());
      return status == WINKY_TREFFER ? 0 : 1;
    };
    if (!k.sudo || !rootDatei(o.sudo_schalter)) return ende(WINKY_ABGELEHNT, -1, "sudo_aus", nullptr);
    if (k.schwelle <= 0 || k.kamera.empty())
      return ende(WINKY_NICHT_EINGERICHTET, -1, "nicht_eingerichtet", nullptr);
    if (terminal.rfind("/dev/", 0) != 0 || winky::terminalEntfernt(terminal))
      return ende(WINKY_ABGELEHNT, -1, "terminal", nullptr);
    if (k.sitzungspruefung) {
      std::string grund;
      if (!winky::hatLokaleGrafischeSitzung(uid, grund)) return ende(WINKY_ABGELEHNT, -1, "sitzung", nullptr);
    }
    if (winky::leseFehlversuche(o.sperre, uid) >= k.sperre_nach)
      return ende(WINKY_GESPERRT, -1, "zu_viele_fehlversuche", nullptr);
    const int offen = winky::leseSudoOffen(o.sperre, uid, beginn);
    if (offen >= winky::kSudoGrenze) return ende(WINKY_GESPERRT, -1, "sudo_begrenzt", "begrenzt");
    if (!gesteFreigegeben(o.vorlagen, uid))
      return ende(WINKY_NICHT_EINGERICHTET, -1, "geste_nicht_getestet", nullptr);
    winky::Vorlagen v;
    if (!winky::ladeVorlagen(o.vorlagen, uid, v, fehler)) {
      log(6, "%s", fehler.c_str());
      return ende(WINKY_NICHT_EINGERICHTET, -1, "vorlagen", nullptr);
    }
    const int sperre = winky::sudoSperren(o.sperre, uid);
    if (sperre < 0) {
      winky::erhoeheSudoOffen(o.sperre, uid, beginn);  // zählt mit: ein Warnsignal
      return ende(WINKY_ABGELEHNT, -1, "gleichzeitig", "abgebrochen");
    }
    winky::schreibeAnfrage(o.anfrage, uid, "wartet", befehl, terminal, beginn);
    Laufzeit l;
    if (!starte(o, k, l, true)) {
      log(4, "%s", l.fehler.c_str());
      winky::sudoEntsperren(o.sperre, uid, sperre);
      return ende(WINKY_FEHLER, -1, "start", "nicht_bestaetigt");
    }
    // Gesicht wie beim Entsperren, aber das ganze Zeitfenster lang (man schaut evtl. erst
    // auf das Terminal und dann in die Kamera)
    const winky::Regeln r{k.schwelle, k.mindest_treffer, static_cast<double>(k.sudo_ms),
                        static_cast<double>(k.sudo_ms), k.blink_abstand, k.blinkpruefung};
    c.senden("W", 1);  // Kamera läuft: das PAM-Modul zeigt jetzt die Aufforderung
    const Pruefergebnis erg = pruefeGeste(l, v, r, t0, nullptr, 0, [&] {
      return winky::sudoAbbruchGesetzt(o.sperre, uid);
    });
    l.kamera->stop();
    winky::sudoEntsperren(o.sperre, uid, sperre);
    const long jetzt = static_cast<long>(std::time(nullptr));
    if (erg.abgebrochen) {
      winky::erhoeheSudoOffen(o.sperre, uid, jetzt);
      return ende(WINKY_ABGELEHNT, -1, "gleichzeitig", "abgebrochen");
    }
    if (erg.status == WINKY_TREFFER) {
      winky::schreibeSudoOffen(o.sperre, uid, 0, jetzt);
      winky::schreibeFehlversuche(o.sperre, uid, 0);
      return ende(WINKY_TREFFER, erg.wert, nullptr, "bestaetigt");
    }
    winky::erhoeheSudoOffen(o.sperre, uid, jetzt);
    // Ein fremdes Gesicht zählt wie beim Entsperren als Fehlversuch, fehlendes Zeichen nicht
    if (erg.status == WINKY_KEIN_TREFFER && !erg.gesicht_erkannt)
      winky::schreibeFehlversuche(o.sperre, uid, winky::leseFehlversuche(o.sperre, uid) + 1);
    return ende(erg.status, erg.wert, erg.gesicht_erkannt ? "kein_zeichen" : nullptr,
                "nicht_bestaetigt");
  }

  if (q.op == WINKY_OP_GESTE_TESTEN) {
    const int dauer_s = static_cast<int>(std::clamp<uint32_t>(q.dauer_s, 3, 30));
    winky::Vorlagen v;
    if (!winky::ladeVorlagen(o.vorlagen, uid, v, fehler)) {
      c.status("{\"fehler\":\"Noch kein Gesicht eingelernt\"}");
      c.antwort(WINKY_NICHT_EINGERICHTET, -1, msSeit(t0), true);
      return 1;
    }
    Laufzeit l;
    if (!starte(o, k, l, true)) {
      log(4, "%s", l.fehler.c_str());
      c.status("{\"fehler\":" + jsonText(l.fehler) + "}");
      c.antwort(WINKY_FEHLER, -1, msSeit(t0), true);
      return 1;
    }
    const float schwelle = k.schwelle > 0 ? k.schwelle : 0.65f;
    const auto start = Clock::now();
    const winky::Regeln r{schwelle, k.mindest_treffer, dauer_s * 1000.0, dauer_s * 1000.0,
                        k.blink_abstand, k.blinkpruefung};
    const Pruefergebnis erg = pruefeGeste(l, v, r, start, &c, dauer_s, [] { return false; });
    if (erg.abgebrochen) return 1;
    c.antwort(erg.status, erg.wert, msSeit(start), true);
    log(6, "Gestentest uid=%u status=%s wert=%s dauer_ms=%.0f gesicht_erkannt=%d", uid,
        statusText(erg.status), zahl(erg.wert).c_str(), msSeit(start), erg.gesicht_erkannt ? 1 : 0);
    return 0;
  }

  if (q.op == WINKY_OP_TESTEN || q.op == WINKY_OP_EINLERNEN) {
    const int dauer_s = static_cast<int>(std::clamp<uint32_t>(q.dauer_s, 3, 60));
    Laufzeit l;
    if (!starte(o, k, l)) {
      log(4, "%s", l.fehler.c_str());
      c.status("{\"fehler\":" + jsonText(l.fehler) + "}");
      c.antwort(WINKY_FEHLER, -1, msSeit(t0), true);
      return 1;
    }
    if (q.op == WINKY_OP_EINLERNEN) return einlernen(l, c, dauer_s, t0) == 0 ? 0 : 1;

    winky::Vorlagen v;
    if (!winky::ladeVorlagen(o.vorlagen, uid, v, fehler)) {
      c.status("{\"fehler\":\"Noch kein Gesicht eingelernt\"}");
      c.antwort(WINKY_NICHT_EINGERICHTET, -1, msSeit(t0), true);
      return 1;
    }
    // Probelauf: gleiche Regel wie beim Entsperren, aber mehr Zeit und ohne Sperrzähler
    const float schwelle = k.schwelle > 0 ? k.schwelle : 0.65f;
    const auto start = Clock::now();
    const winky::Regeln r{schwelle, k.mindest_treffer, dauer_s * 1000.0, dauer_s * 1000.0,
                        k.blink_abstand, k.blinkpruefung};
    const Pruefergebnis erg = pruefe(l, v, r, start, &c, dauer_s);
    if (erg.abgebrochen) return 1;
    c.antwort(erg.status, erg.wert, msSeit(start), true);
    log(6, "Test uid=%u status=%s wert=%s dauer_ms=%.0f", uid, statusText(erg.status),
        zahl(erg.wert).c_str(), msSeit(start));
    return 0;
  }

  log(4, "Unbekannte Operation %u", q.op);
  c.antwort(WINKY_ABGELEHNT, -1, msSeit(t0), false);
  return 1;
}
