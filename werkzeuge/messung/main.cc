// Messwerkzeug für die Machbarkeitsmessung (Machbarkeit der IR-Gesichtserkennung).
//
// Läuft als normaler Benutzer. Speichert keine Bilder: nur Kennzahlen als CSV
// und beim Einlernen die Merkmalsvektoren (Datei mit Rechten 0600).
//
//   winky-messung selbsttest
//   winky-messung kamera    [--bilder N]
//   winky-messung vorschau  [--vorlagen DATEI] [--dauer S]
//   winky-messung einlernen --vorlagen DATEI [--dauer S]
//   winky-messung messen    --vorlagen DATEI --name NAME [--dauer S] [--csv DATEI]
//   winky-messung hand      --name NAME [--dauer S] [--csv DATEI]
//
// "hand" misst Handzeichen (MediaPipe Gesture Recognizer, ausgewertet wird Victory ✌). Die
// CSV enthält außerdem Rohwerte aus den ersten Messrunden (Daumen-Regel, Abstand
// Zeigefinger-Nase). Nur Zahlen, keine Bilder; die Zeit steht als Unix-Millisekunden in
// jeder Zeile, damit die Oberfläche ihre Aufforderungen dazulegen kann.
//
// Gemeinsame Optionen: --geraet PFAD, --modelle ORDNER, --threads N,
// --vorschau (Protokoll für die Oberfläche auf stdout), --vorlagen-id ID.
//
// Vorschau-Protokoll (stdout, nur mit --vorschau):
//   STATUS {json}\n
//   BILD <breite> <hoehe> <bytes>\n<RGB-Daten>
// Menschenlesbare Ausgaben gehen dann nach stderr. Das Kamerabild wird nur an
// die Oberfläche weitergereicht und nirgends gespeichert.

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <memory>
#include <numeric>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "face_align.h"
#include "face_detection.h"
#include "face_embedding.h"
#include "hand_gesture.h"
#include "face_quality.h"
#include "v4l2_ir.h"

namespace {

using Clock = std::chrono::steady_clock;

std::atomic<bool> g_stop{false};
FILE* g_text = stdout;  // menschenlesbare Ausgabe; mit --vorschau stderr

void onSignal(int) { g_stop = true; }

double msSince(Clock::time_point t0) {
  return std::chrono::duration<double, std::milli>(Clock::now() - t0).count();
}

struct Options {
  std::string command;
  std::string device = "/dev/video-ir";  // so heißt die Kamera im Mess-Container
  std::string models = "vendor";
  std::string templates;
  std::string templates_id;
  std::string name;
  std::string csv;
  double duration = 10.0;
  int threads = 4;
  int frames = 60;
  int width = 640;
  int height = 360;
  bool preview = false;
};

[[noreturn]] void usage() {
  std::fprintf(stderr,
               "Aufruf:\n"
               "  winky-messung selbsttest\n"
               "  winky-messung kamera    [--bilder N]\n"
               "  winky-messung vorschau  [--vorlagen DATEI] [--dauer S]\n"
               "  winky-messung einlernen --vorlagen DATEI [--dauer S]\n"
               "  winky-messung messen    --vorlagen DATEI --name NAME [--dauer S] [--csv DATEI]\n"
               "  winky-messung hand      --name NAME [--dauer S] [--csv DATEI]\n"
               "Optionen: --geraet PFAD  --modelle ORDNER  --threads N  --vorschau  --vorlagen-id ID\n");
  std::exit(2);
}

Options parse(int argc, char** argv) {
  if (argc < 2) usage();
  Options o;
  o.command = argv[1];
  for (int i = 2; i < argc; ++i) {
    const std::string a = argv[i];
    auto value = [&]() -> std::string {
      if (i + 1 >= argc) usage();
      return argv[++i];
    };
    if (a == "--geraet") o.device = value();
    else if (a == "--modelle") o.models = value();
    else if (a == "--vorlagen") o.templates = value();
    else if (a == "--vorlagen-id") o.templates_id = value();
    else if (a == "--name") o.name = value();
    else if (a == "--csv") o.csv = value();
    else if (a == "--dauer") o.duration = std::stod(value());
    else if (a == "--threads") o.threads = std::stoi(value());
    else if (a == "--bilder") o.frames = std::stoi(value());
    else if (a == "--vorschau") o.preview = true;
    else usage();
  }
  return o;
}

// Nur Buchstaben, Ziffern, '-' und '_' (Namen landen in CSV und JSON)
std::string safeText(const std::string& s) {
  std::string out;
  for (char c : s) {
    if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' ||
        c == '_')
      out += c;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Vorlagendatei (nur für die Messung): "WINKYM", Version, Dimension, Anzahl, Floats
// ---------------------------------------------------------------------------

struct Templates {
  int dim = 0;
  std::vector<float> data;  // count * dim
  size_t count() const { return dim ? data.size() / dim : 0; }
  const float* row(size_t i) const { return &data[i * dim]; }
};

void writeTemplates(const std::string& path, const Templates& t) {
  const std::string tmp = path + ".neu";
  const int fd = ::open(tmp.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, 0600);
  if (fd < 0) throw std::runtime_error("Vorlagen schreiben: " + std::string(std::strerror(errno)));
  uint32_t head[4];
  std::memcpy(&head[0], "WINKYM", 4);
  head[1] = 1;
  head[2] = static_cast<uint32_t>(t.dim);
  head[3] = static_cast<uint32_t>(t.count());
  bool ok = ::write(fd, head, sizeof(head)) == static_cast<ssize_t>(sizeof(head));
  const size_t bytes = t.data.size() * sizeof(float);
  ok = ok && ::write(fd, t.data.data(), bytes) == static_cast<ssize_t>(bytes);
  ok = ok && ::fsync(fd) == 0;
  ::close(fd);
  if (!ok || ::rename(tmp.c_str(), path.c_str()) != 0) {
    ::unlink(tmp.c_str());
    throw std::runtime_error("Vorlagen schreiben fehlgeschlagen");
  }
}

Templates readTemplates(const std::string& path) {
  Templates t;
  FILE* f = std::fopen(path.c_str(), "rb");
  if (!f) throw std::runtime_error("Vorlagen nicht lesbar: " + path);
  uint32_t head[4];
  if (std::fread(head, sizeof(head), 1, f) != 1 || std::memcmp(&head[0], "WINKYM", 4) != 0 ||
      head[1] != 1 || head[2] == 0 || head[2] > 4096 || head[3] == 0 || head[3] > 1000) {
    std::fclose(f);
    throw std::runtime_error("Vorlagendatei ungültig");
  }
  t.dim = static_cast<int>(head[2]);
  t.data.resize(static_cast<size_t>(head[2]) * head[3]);
  const size_t n = std::fread(t.data.data(), sizeof(float), t.data.size(), f);
  std::fclose(f);
  if (n != t.data.size()) throw std::runtime_error("Vorlagendatei abgeschnitten");
  return t;
}

// ---------------------------------------------------------------------------
// Modelle (laden parallel zum Kamerastart, wie später im Prüfdienst).
// Hauptmodell SFace; ein weiteres Modell zum Vergleich wird geladen, falls
// vendor/vergleich.onnx existiert (112 x 112 Eingabe, nicht im Paket).
// ---------------------------------------------------------------------------

struct Models {
  std::unique_ptr<winky::FaceDetector> detector;
  std::unique_ptr<winky::FaceEmbedder> embedder;
  std::unique_ptr<winky::FaceEmbedder> embedder2;
  std::unique_ptr<winky::HandGestureRecognizer> hand;  // nur für "hand" und "selbsttest"
  double load_ms = 0;
  std::string error;
};

const char* kZweitmodell = "/vergleich.onnx";

std::string zweitVorlagen(const std::string& path) { return path + ".mbf"; }

void loadModels(Ort::Env* env, const Options* o, Models* m) {
  const auto t0 = Clock::now();
  try {
    m->detector = std::make_unique<winky::FaceDetector>(*env, o->models + "/face_detection_yunet_2023mar.onnx",
                                                      o->threads, /*conf=*/0.5f);
    m->embedder = std::make_unique<winky::FaceEmbedder>(
        *env, o->models + "/face_recognition_sface_2021dec.onnx", o->threads);
    const std::string second = o->models + kZweitmodell;
    if (::access(second.c_str(), R_OK) == 0) {
      m->embedder2 = std::make_unique<winky::FaceEmbedder>(*env, second, o->threads);
    }
    const std::string palm = o->models + "/hand_detector.onnx";
    if ((o->command == "hand" || o->command == "selbsttest") && ::access(palm.c_str(), R_OK) == 0) {
      // Schwelle der Handflächensuche wie MediaPipe (0,5); der beste Wert steht trotzdem in der CSV
      m->hand = std::make_unique<winky::HandGestureRecognizer>(*env, o->models, o->threads, 0.5f);
    }
  } catch (const std::exception& e) {
    m->error = e.what();
  }
  m->load_ms = msSince(t0);
}

// Ergebnis der Analyse eines beleuchteten Bildes
struct LitResult {
  int n_faces = 0;
  winky::FaceBox face;
  winky::FaceQuality quality;
  float dark_mean = -1;  // Gesichtsbereich im vorherigen (dunklen) Bild
  std::vector<float> embedding;
  std::vector<float> embedding2;
  double det_ms = 0;
  double emb_ms = 0;
};

LitResult analyse(Models& m, const winky::IrFrame& frame, const winky::IrFrame* prev_dark,
                  const winky::QualityLimits& lim, bool embed = true) {
  LitResult r;
  auto t = Clock::now();
  const auto faces = m.detector->detect(frame.image);
  r.det_ms = msSince(t);
  r.n_faces = static_cast<int>(faces.size());
  if (faces.empty()) return r;
  r.face = faces.front();
  r.quality = winky::assessFace(frame.image, r.face, lim);
  if (prev_dark) r.dark_mean = winky::regionMean(prev_dark->image, r.face);
  if (r.quality.usable && embed) {
    t = Clock::now();
    const winky::GrayImage aligned = winky::alignFace(frame.image, r.face.kps);
    r.embedding = m.embedder->embed(aligned);
    r.emb_ms = msSince(t);
    if (m.embedder2 && !r.embedding.empty()) r.embedding2 = m.embedder2->embed(aligned);
  }
  return r;
}

// Mittel der 3 besten und bester Wert gegen alle Vorlagen
std::pair<float, float> score(const std::vector<float>& emb, const Templates& tpl) {
  std::vector<float> sims(tpl.count());
  for (size_t i = 0; i < tpl.count(); ++i) sims[i] = winky::cosine(emb, tpl.row(i));
  std::sort(sims.begin(), sims.end(), std::greater<float>());
  const size_t k = std::min<size_t>(3, sims.size());
  const float top =
      std::accumulate(sims.begin(), sims.begin() + static_cast<std::ptrdiff_t>(k), 0.0f) / k;
  return {top, sims.front()};
}

// ---------------------------------------------------------------------------
// Vorschau für die Oberfläche: halbe Auflösung, Gesichtsrahmen eingezeichnet
// ---------------------------------------------------------------------------

class Preview {
 public:
  explicit Preview(bool on) : on_(on) {}
  bool on() const { return on_; }

  void status(const std::string& json) {
    if (!on_) return;
    std::fprintf(stdout, "STATUS %s\n", json.c_str());
    std::fflush(stdout);
  }

  void frame(const winky::GrayImage& img, const LitResult* r,
             const std::vector<std::pair<float, float>>& punkte = {},
             const std::vector<std::pair<float, float>>& hand = {}) {
    if (!on_ || img.empty()) return;
    const int w = img.width / 2, h = img.height / 2;
    rgb_.assign(static_cast<size_t>(w) * h * 3, 0);
    for (int y = 0; y < h; ++y) {
      for (int x = 0; x < w; ++x) {
        const int v = (img.at(2 * y, 2 * x) + img.at(2 * y, 2 * x + 1) + img.at(2 * y + 1, 2 * x) +
                       img.at(2 * y + 1, 2 * x + 1) + 2) / 4;
        uint8_t* p = &rgb_[(static_cast<size_t>(y) * w + x) * 3];
        p[0] = p[1] = p[2] = static_cast<uint8_t>(v);
      }
    }
    if (r && r->n_faces > 0) {
      const bool ok = r->quality.usable;
      const uint8_t col[3] = {static_cast<uint8_t>(ok ? 60 : 245),
                              static_cast<uint8_t>(ok ? 220 : 170), static_cast<uint8_t>(ok ? 90 : 30)};
      rect(w, h, static_cast<int>(r->face.x1 / 2), static_cast<int>(r->face.y1 / 2),
           static_cast<int>(r->face.x2 / 2), static_cast<int>(r->face.y2 / 2), col);
      if (r->face.has_kps) {
        const uint8_t dot[3] = {80, 200, 255};
        for (int k = 0; k < 5; ++k) {
          const int cx = static_cast<int>(r->face.kps[k * 2] / 2);
          const int cy = static_cast<int>(r->face.kps[k * 2 + 1] / 2);
          for (int dy = -1; dy <= 1; ++dy)
            for (int dx = -1; dx <= 1; ++dx) put(w, h, cx + dx, cy + dy, dot);
        }
      }
    }
    const uint8_t lid[3] = {255, 120, 220};
    for (const auto& pt : punkte) {
      const int cx = static_cast<int>(pt.first / 2), cy = static_cast<int>(pt.second / 2);
      put(w, h, cx, cy, lid);
      put(w, h, cx + 1, cy, lid);
    }
    const uint8_t gelb[3] = {255, 210, 40};
    for (const auto& pt : hand) {
      const int cx = static_cast<int>(pt.first / 2), cy = static_cast<int>(pt.second / 2);
      for (int dy = -1; dy <= 1; ++dy)
        for (int dx = -1; dx <= 1; ++dx) put(w, h, cx + dx, cy + dy, gelb);
    }
    std::fprintf(stdout, "BILD %d %d %zu\n", w, h, rgb_.size());
    std::fwrite(rgb_.data(), 1, rgb_.size(), stdout);
    std::fflush(stdout);
  }

 private:
  void put(int w, int h, int x, int y, const uint8_t c[3]) {
    if (x < 0 || y < 0 || x >= w || y >= h) return;
    uint8_t* p = &rgb_[(static_cast<size_t>(y) * w + x) * 3];
    p[0] = c[0];
    p[1] = c[1];
    p[2] = c[2];
  }
  void rect(int w, int h, int x1, int y1, int x2, int y2, const uint8_t c[3]) {
    for (int t = 0; t < 2; ++t) {
      for (int x = x1; x <= x2; ++x) {
        put(w, h, x, y1 + t, c);
        put(w, h, x, y2 - t, c);
      }
      for (int y = y1; y <= y2; ++y) {
        put(w, h, x1 + t, y, c);
        put(w, h, x2 - t, y, c);
      }
    }
  }
  bool on_;
  std::vector<uint8_t> rgb_;
};

std::string jsonNum(double v, int digits = 3) {
  if (!std::isfinite(v)) return "null";
  char buf[32];
  std::snprintf(buf, sizeof(buf), "%.*f", digits, v);
  return buf;
}

// Kamera und Modelle parallel starten (wie später der Prüfdienst)
struct Session {
  Ort::Env env{ORT_LOGGING_LEVEL_ERROR, "winky-messung"};
  Models models;
  std::unique_ptr<winky::V4l2IrCamera> cam;
  double cam_ms = 0;
};

bool openSession(const Options& o, Session& s, Clock::time_point t0) {
  std::thread loader(loadModels, &s.env, &o, &s.models);
  s.cam = std::make_unique<winky::V4l2IrCamera>(o.device);
  std::string err;
  const bool cam_ok = s.cam->start(o.width, o.height, err);
  s.cam_ms = msSince(t0);
  loader.join();
  if (!cam_ok) {
    std::fprintf(stderr, "Kamerafehler: %s\n", err.c_str());
    return false;
  }
  if (!s.models.error.empty()) {
    std::fprintf(stderr, "Modellfehler: %s\n", s.models.error.c_str());
    return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// Befehl: selbsttest (ohne Kamera: Modelle laden und einmal durchrechnen)
// ---------------------------------------------------------------------------

int cmdSelbsttest(const Options& o) {
  Ort::Env env(ORT_LOGGING_LEVEL_ERROR, "winky-messung");
  Models m;
  loadModels(&env, &o, &m);
  if (!m.error.empty()) {
    std::fprintf(stderr, "Modellfehler: %s\n", m.error.c_str());
    return 1;
  }
  const std::string zweit = m.embedder2 ? std::to_string(m.embedder2->dim()) : "fehlt";
  std::printf("Modelle geladen in %.0f ms (Detektor-Eingabe %d px, SFace %d Werte, Vergleich %s)\n",
              m.load_ms, m.detector->inputSize(), m.embedder->dim(), zweit.c_str());
  winky::GrayImage img(o.width, o.height);
  for (int y = 0; y < img.height; ++y)
    for (int x = 0; x < img.width; ++x) img.at(y, x) = static_cast<uint8_t>((x * 7 + y * 3) & 0xff);
  auto t = Clock::now();
  const auto faces = m.detector->detect(img);
  std::printf("Detektor auf Testmuster: %zu Gesichter in %.1f ms\n", faces.size(), msSince(t));
  winky::GrayImage face(winky::kAlignedFaceSize, winky::kAlignedFaceSize);
  t = Clock::now();
  const auto e1 = m.embedder->embed(face);
  std::printf("SFace: %zu Werte in %.1f ms\n", e1.size(), msSince(t));
  if (m.embedder2) {
    t = Clock::now();
    const auto e2 = m.embedder2->embed(face);
    std::printf("Vergleichsmodell: %zu Werte in %.1f ms\n", e2.size(), msSince(t));
  }
  if (m.hand) {
    const auto hr = m.hand->analyse(img, false);
    std::printf("Handmodell: geladen, auf Testmuster %s (Handfläche %.2f) in %.1f ms\n",
                hr.found ? "Hand gefunden" : "keine Hand", hr.palm_score, hr.palm_ms);
  } else {
    std::printf("Handmodell: fehlt\n");
  }
  return e1.empty() ? 1 : 0;
}

// ---------------------------------------------------------------------------
// Befehl: kamera
// ---------------------------------------------------------------------------

int cmdKamera(const Options& o) {
  const auto t0 = Clock::now();
  winky::V4l2IrCamera cam(o.device);
  std::string err;
  if (!cam.start(o.width, o.height, err)) {
    std::fprintf(stderr, "Fehler: %s\n", err.c_str());
    return 1;
  }
  std::printf("Kamera gestartet nach %.0f ms (%dx%d)\n", msSince(t0), cam.width(), cam.height());
  winky::StrobeTracker strobe;
  winky::IrFrame f;
  for (int i = 0; i < o.frames && !g_stop; ++i) {
    if (!cam.read(f, 2000, err)) {
      std::fprintf(stderr, "Fehler: %s\n", err.c_str());
      return 1;
    }
    const auto s = strobe.push(f.mean);
    std::printf("%3d  t=%6.0f ms  seq=%u  hell=%5.1f  %s%s\n", i, msSince(t0), f.sequence, f.mean,
                s.lit ? "beleuchtet" : "dunkel", s.strobing ? "" : "  (kein Blinken)");
  }
  std::printf("Verworfene Bilder: %u\n", cam.droppedFrames());
  return 0;
}

// ---------------------------------------------------------------------------
// Befehl: vorschau (Kamerabild mit Gesichtsrahmen, optional mit Wert)
// ---------------------------------------------------------------------------

int cmdVorschau(const Options& o) {
  const auto t0 = Clock::now();
  Templates tpl;
  if (!o.templates.empty() && ::access(o.templates.c_str(), R_OK) == 0) tpl = readTemplates(o.templates);
  Session s;
  if (!openSession(o, s, t0)) return 1;
  const bool scoring = tpl.count() > 0 && s.models.embedder->dim() == tpl.dim;
  Preview pv(o.preview);
  winky::QualityLimits lim;
  winky::StrobeTracker strobe;
  winky::IrFrame frame;
  std::string err;
  while (!g_stop && msSince(t0) < o.duration * 1000.0) {
    if (!s.cam->read(frame, 2000, err)) {
      std::fprintf(stderr, "Kamerafehler: %s\n", err.c_str());
      return 1;
    }
    if (!strobe.push(frame.mean).lit) continue;
    const LitResult r = analyse(s.models, frame, nullptr, lim, scoring);
    std::string wert = "null";
    if (!r.embedding.empty()) wert = jsonNum(score(r.embedding, tpl).first);
    pv.frame(frame.image, &r);
    pv.status(std::string("{\"modus\":\"vorschau\",\"gesicht\":") + (r.n_faces ? "true" : "false") +
              ",\"grund\":\"" + (r.n_faces ? r.quality.reason : "kein_gesicht") +
              "\",\"hell\":" + jsonNum(frame.mean, 1) + ",\"wert\":" + wert + "}");
  }
  return 0;
}

// ---------------------------------------------------------------------------
// Befehl: einlernen
// ---------------------------------------------------------------------------

int cmdEinlernen(const Options& o) {
  if (o.templates.empty()) usage();
  const auto t0 = Clock::now();
  Session s;
  if (!openSession(o, s, t0)) return 1;
  Models& m = s.models;
  Preview pv(o.preview);

  struct Sample {
    std::vector<float> emb;
    std::vector<float> emb2;
  };
  std::vector<Sample> samples;
  winky::QualityLimits lim;
  winky::StrobeTracker strobe;
  winky::IrFrame frame, prev;
  bool prev_dark = false;
  int lit = 0, with_face = 0;
  std::vector<std::string> reasons;
  std::string err;

  std::fprintf(g_text, "Einlernen läuft %.0f s. Kopf langsam leicht nach links, rechts, oben, unten.\n",
               o.duration);
  const auto t_start = Clock::now();
  while (msSince(t_start) < o.duration * 1000.0) {
    if (g_stop) {
      std::fprintf(stderr, "Abgebrochen, nichts gespeichert.\n");
      return 3;
    }
    if (!s.cam->read(frame, 2000, err)) {
      std::fprintf(stderr, "\nKamerafehler: %s\n", err.c_str());
      return 1;
    }
    const auto st = strobe.push(frame.mean);
    if (!st.lit) {
      prev = frame;
      prev_dark = true;
      continue;
    }
    ++lit;
    const LitResult r = analyse(m, frame, prev_dark ? &prev : nullptr, lim);
    prev_dark = false;
    if (r.n_faces > 0) ++with_face;
    if (!r.embedding.empty()) {
      samples.push_back({r.embedding, r.embedding2});
      if (!pv.on()) std::fputc('+', g_text);
    } else {
      if (!pv.on()) std::fputc(r.n_faces ? 'q' : '.', g_text);
      if (r.n_faces) reasons.emplace_back(r.quality.reason);
    }
    std::fflush(g_text);
    pv.frame(frame.image, &r);
    pv.status(std::string("{\"modus\":\"einlernen\",\"t\":") + jsonNum(msSince(t_start) / 1000.0, 1) +
              ",\"dauer\":" + jsonNum(o.duration, 0) + ",\"beleuchtet\":" + std::to_string(lit) +
              ",\"gesicht\":" + std::to_string(with_face) +
              ",\"brauchbar\":" + std::to_string(samples.size()) + ",\"grund\":\"" +
              (r.n_faces ? r.quality.reason : "kein_gesicht") + "\"}");
  }
  s.cam->stop();
  std::fprintf(g_text, "\nBeleuchtete Bilder: %d, mit Gesicht: %d, brauchbar: %zu\n", lit, with_face,
               samples.size());
  if (!reasons.empty()) {
    std::sort(reasons.begin(), reasons.end());
    std::fprintf(g_text, "Verworfen wegen:");
    for (size_t i = 0; i < reasons.size();) {
      size_t j = i;
      while (j < reasons.size() && reasons[j] == reasons[i]) ++j;
      std::fprintf(g_text, " %s=%zu", reasons[i].c_str(), j - i);
      i = j;
    }
    std::fprintf(g_text, "\n");
  }
  if (samples.size() < 8) {
    std::fprintf(stderr, "Zu wenige brauchbare Bilder (mindestens 8). Bitte wiederholen.\n");
    return 1;
  }

  // Ausreißer entfernen: Ähnlichkeit zum Mittelwert, Median - 3 * MAD
  const int dim = static_cast<int>(samples.front().emb.size());
  std::vector<float> mean(dim, 0.0f);
  for (const auto& sm : samples)
    for (int k = 0; k < dim; ++k) mean[k] += sm.emb[k];
  double norm = 0;
  for (float v : mean) norm += static_cast<double>(v) * v;
  norm = std::sqrt(norm);
  for (float& v : mean) v = static_cast<float>(v / norm);
  std::vector<float> sims;
  for (const auto& sm : samples) sims.push_back(winky::cosine(sm.emb, mean.data()));
  std::vector<float> sorted = sims;
  std::sort(sorted.begin(), sorted.end());
  const float median = sorted[sorted.size() / 2];
  std::vector<float> dev;
  for (float v : sims) dev.push_back(std::fabs(v - median));
  std::sort(dev.begin(), dev.end());
  const float mad = std::max(dev[dev.size() / 2], 0.02f);
  std::vector<Sample> kept;
  for (size_t i = 0; i < samples.size(); ++i) {
    if (sims[i] >= median - 3.0f * mad) kept.push_back(samples[i]);
  }

  // Höchstens 30 Vorlagen, gleichmäßig über die Zeit verteilt
  const size_t want = std::min<size_t>(30, kept.size());
  Templates t, t2;
  t.dim = dim;
  const bool second =
      std::all_of(kept.begin(), kept.end(), [](const Sample& x) { return !x.emb2.empty(); });
  if (second) t2.dim = static_cast<int>(kept.front().emb2.size());
  for (size_t i = 0; i < want; ++i) {
    const size_t idx = (want == 1) ? 0 : i * (kept.size() - 1) / (want - 1);
    t.data.insert(t.data.end(), kept[idx].emb.begin(), kept[idx].emb.end());
    if (second) t2.data.insert(t2.data.end(), kept[idx].emb2.begin(), kept[idx].emb2.end());
  }
  writeTemplates(o.templates, t);
  if (second) writeTemplates(zweitVorlagen(o.templates), t2);

  double sum = 0;
  float lo = 1.0f;
  size_t pairs = 0;
  for (size_t i = 0; i < t.count(); ++i) {
    std::vector<float> a(t.row(i), t.row(i) + dim);
    for (size_t j = i + 1; j < t.count(); ++j) {
      const float c = winky::cosine(a, t.row(j));
      sum += c;
      lo = std::min(lo, c);
      ++pairs;
    }
  }
  std::fprintf(g_text, "Gespeichert: %zu Vorlagen, Ausreißer entfernt: %zu%s\n", t.count(),
               samples.size() - kept.size(), second ? " (dazu Vergleichsmodell)" : "");
  std::fprintf(g_text, "Ähnlichkeit der Vorlagen untereinander: Mittel %.3f, Minimum %.3f\n",
               pairs ? sum / pairs : 0.0, lo);
  return 0;
}

// ---------------------------------------------------------------------------
// Befehl: messen
// ---------------------------------------------------------------------------

int cmdMessen(const Options& o) {
  if (o.templates.empty() || o.name.empty()) usage();
  const std::string name = safeText(o.name);
  const auto t0 = Clock::now();  // entspricht dem Start der Prüfung am Sperrbildschirm
  const Templates tpl = readTemplates(o.templates);
  Session s;
  if (!openSession(o, s, t0)) return 1;
  Models& m = s.models;
  if (m.embedder->dim() != tpl.dim) {
    std::fprintf(stderr, "Vorlagen passen nicht zum Modell\n");
    return 1;
  }
  Templates tpl2;
  const std::string tpl2_path = zweitVorlagen(o.templates);
  if (m.embedder2 && ::access(tpl2_path.c_str(), R_OK) == 0) {
    tpl2 = readTemplates(tpl2_path);
    if (tpl2.dim != m.embedder2->dim()) tpl2 = Templates{};
  }
  const bool have2 = tpl2.count() > 0;

  FILE* csv = nullptr;
  if (!o.csv.empty()) {
    const int fd = ::open(o.csv.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, 0600);
    csv = fd >= 0 ? fdopen(fd, "w") : nullptr;
    if (!csv) {
      std::fprintf(stderr, "CSV nicht schreibbar: %s\n", o.csv.c_str());
      return 1;
    }
    char date[32];
    const std::time_t now = std::time(nullptr);
    std::strftime(date, sizeof(date), "%Y-%m-%d %H:%M:%S", std::localtime(&now));
    std::fprintf(csv, "# name=%s\n# zeit=%s\n# vorlagen=%zu\n# vorlagen2=%zu\n# vorlagen_id=%s\n",
                 name.c_str(), date, tpl.count(), tpl2.count(), safeText(o.templates_id).c_str());
    std::fprintf(csv, "# threads=%d\n# kamera_start_ms=%.1f\n# modelle_laden_ms=%.1f\n", o.threads,
                 s.cam_ms, m.load_ms);
    std::fprintf(csv,
                 "name,bild,t_ms,seq,hell,beleuchtet,blinkt,gesichter,det_conf,x1,y1,x2,y2,"
                 "breite,punkte_min,neigung,drehung,augenabstand,gesicht_hell,gesicht_sat,"
                 "gesicht_dunkel,brauchbar,grund,det_ms,emb_ms,wert_top3,wert_max,"
                 "wert2_top3,wert2_max\n");
  }

  Preview pv(o.preview);
  winky::QualityLimits lim;
  winky::StrobeTracker strobe;
  winky::IrFrame frame, prev;
  bool prev_dark = false;
  int n = 0, lit = 0, faces = 0, usable = 0;
  std::vector<float> scores, scores2;
  double first_frame_ms = -1, first_usable_ms = -1;
  std::string err;

  std::fprintf(g_text, "Messung \"%s\" läuft %.0f s ...\n", name.c_str(), o.duration);
  for (;;) {
    if (g_stop) {
      if (csv) std::fclose(csv);
      std::fprintf(stderr, "Abgebrochen.\n");
      return 3;
    }
    if (first_frame_ms >= 0 && msSince(t0) - first_frame_ms >= o.duration * 1000.0) break;
    if (!s.cam->read(frame, 2000, err)) {
      std::fprintf(stderr, "\nKamerafehler: %s\n", err.c_str());
      if (csv) std::fclose(csv);
      return 1;
    }
    const double t_ms = msSince(t0);
    if (first_frame_ms < 0) first_frame_ms = t_ms;
    const auto st = strobe.push(frame.mean);
    ++n;
    if (csv)
      std::fprintf(csv, "%s,%d,%.1f,%u,%.1f,%d,%d,", name.c_str(), n, t_ms, frame.sequence,
                   frame.mean, st.lit ? 1 : 0, st.strobing ? 1 : 0);
    if (!st.lit) {
      if (csv) std::fprintf(csv, ",,,,,,,,,,,,,,,,,,,,,\n");  // 22 leere Felder
      prev = frame;
      prev_dark = true;
      continue;
    }
    ++lit;
    const LitResult r = analyse(m, frame, prev_dark ? &prev : nullptr, lim);
    prev_dark = false;
    std::pair<float, float> w1{-2, -2}, w2{-2, -2};
    if (!r.embedding.empty()) {
      w1 = score(r.embedding, tpl);
      scores.push_back(w1.first);
      ++usable;
      if (first_usable_ms < 0) first_usable_ms = t_ms;
      if (have2 && !r.embedding2.empty()) {
        w2 = score(r.embedding2, tpl2);
        scores2.push_back(w2.first);
      }
    }
    if (r.n_faces) ++faces;
    if (csv) {
      if (r.n_faces == 0) {
        std::fprintf(csv, "0,,,,,,,,,,,,,,0,kein_gesicht,%.1f,,,,,\n", r.det_ms);
      } else {
        const auto& q = r.quality;
        std::fprintf(csv,
                     "%d,%.3f,%.0f,%.0f,%.0f,%.0f,%.1f,%.3f,%.1f,%.3f,%.1f,%.1f,%.4f,%.1f,%d,%s,"
                     "%.1f,%.1f,",
                     r.n_faces, q.conf, r.face.x1, r.face.y1, r.face.x2, r.face.y2, q.width,
                     q.kps_min, q.roll_deg, q.yaw_ratio, q.eye_dist, q.mean, q.saturated,
                     r.dark_mean, q.usable ? 1 : 0, q.reason, r.det_ms, r.emb_ms);
        if (w1.first > -2) std::fprintf(csv, "%.4f,%.4f,", w1.first, w1.second);
        else std::fprintf(csv, ",,");
        if (w2.first > -2) std::fprintf(csv, "%.4f,%.4f\n", w2.first, w2.second);
        else std::fprintf(csv, ",\n");
      }
    }
    const double t_rel = (t_ms - first_frame_ms) / 1000.0;
    if (pv.on()) {
      pv.frame(frame.image, &r);
      pv.status(std::string("{\"modus\":\"messen\",\"t\":") + jsonNum(t_rel, 1) +
                ",\"dauer\":" + jsonNum(o.duration, 0) + ",\"bilder\":" + std::to_string(n) +
                ",\"beleuchtet\":" + std::to_string(lit) + ",\"gesicht\":" + std::to_string(faces) +
                ",\"brauchbar\":" + std::to_string(usable) + ",\"grund\":\"" +
                (r.n_faces ? r.quality.reason : "kein_gesicht") + "\",\"wert\":" +
                (w1.first > -2 ? jsonNum(w1.first) : "null") + ",\"wert2\":" +
                (w2.first > -2 ? jsonNum(w2.first) : "null") + "}");
    } else {
      char wert[64] = "  -  ";
      if (w1.first > -2) {
        if (have2 && w2.first > -2)
          std::snprintf(wert, sizeof(wert), "%.3f / %.3f", w1.first, w2.first);
        else
          std::snprintf(wert, sizeof(wert), "%.3f", w1.first);
      }
      std::printf("\r  %4.1f s  Bilder %3d  beleuchtet %3d  Gesicht %3d  brauchbar %3d  Wert %s     ",
                  t_rel, n, lit, faces, usable, wert);
      std::fflush(stdout);
    }
  }
  s.cam->stop();
  if (csv && std::fclose(csv) != 0) {
    std::fprintf(stderr, "CSV konnte nicht vollständig geschrieben werden\n");
    return 1;
  }

  std::fprintf(g_text, "\nKamera bereit nach %.0f ms, Modelle nach %.0f ms, erstes Bild nach %.0f ms\n",
               s.cam_ms, m.load_ms, first_frame_ms);
  if (first_usable_ms >= 0)
    std::fprintf(g_text, "Erstes brauchbares Gesicht nach %.0f ms\n", first_usable_ms);
  auto summary = [](const char* label, std::vector<float> v) {
    if (v.empty()) return;
    std::sort(v.begin(), v.end());
    std::fprintf(g_text, "%s: Minimum %.3f, Median %.3f, Maximum %.3f\n", label, v.front(),
                 v[v.size() / 2], v.back());
  };
  if (scores.empty()) std::fprintf(g_text, "Kein brauchbares Gesicht erkannt.\n");
  summary("Werte SFace", scores);
  summary("Werte Vergleichsmodell", scores2);
  return 0;
}

// ---------------------------------------------------------------------------
// Befehl: hand (Machbarkeit eines Handzeichens)
// ---------------------------------------------------------------------------

const char* kGestenNamen[winky::kGestureCount] = {"keine", "Faust", "offene Hand", "Zeigefinger hoch",
                                                "Daumen runter", "Daumen hoch", "Victory",
                                                "I love you"};

// Einfache Regel aus den Handpunkten (Bild, y nach unten): Daumen zeigt nach oben und
// ragt über alle anderen Punkte, die vier Finger sind eingerollt.
struct DaumenRegel {
  bool hoch = false;
  float winkel = 0;      // Daumenrichtung gegen senkrecht nach oben, Grad
  float oben = 0;        // Daumenspitze über dem höchsten anderen Punkt, in Handgrößen
  float lang = 0;        // Daumenlänge in Handgrößen
  float streck[4] = {};  // Zeige-, Mittel-, Ring-, kleiner Finger: Spitze/Ansatz vom Handgelenk
};

DaumenRegel daumenRegel(const std::array<float, winky::kHandPoints * 2>& p) {
  auto d = [&](int i, int j) { return std::hypot(p[i * 2] - p[j * 2], p[i * 2 + 1] - p[j * 2 + 1]); };
  DaumenRegel r;
  const float hs = std::max(1.0f, d(0, 9));
  r.winkel = static_cast<float>(std::atan2(std::fabs(p[4 * 2] - p[2 * 2]), p[2 * 2 + 1] - p[4 * 2 + 1]) *
                                180.0 / M_PI);
  float hoechster = 1e9f;
  for (int i = 0; i < winky::kHandPoints; ++i)
    if (i < 2 || i > 4) hoechster = std::min(hoechster, p[i * 2 + 1]);
  r.oben = (hoechster - p[4 * 2 + 1]) / hs;
  r.lang = d(2, 4) / hs;
  const int spitze[4] = {8, 12, 16, 20}, ansatz[4] = {5, 9, 13, 17};
  bool eingerollt = true;
  for (int f = 0; f < 4; ++f) {
    r.streck[f] = d(0, spitze[f]) / std::max(1.0f, d(0, ansatz[f]));
    eingerollt = eingerollt && r.streck[f] < 1.45f;
  }
  r.hoch = r.winkel < 45.0f && r.oben > 0.15f && r.lang > 0.5f && eingerollt;
  return r;
}

int cmdHand(const Options& o) {
  if (o.name.empty()) usage();
  const std::string name = safeText(o.name);
  const auto t0 = Clock::now();
  Session s;
  if (!openSession(o, s, t0)) return 1;
  Models& m = s.models;
  if (!m.hand) {
    std::fprintf(stderr, "Handmodell fehlt (hand_detector.onnx in %s)\n", o.models.c_str());
    return 1;
  }
  FILE* csv = nullptr;
  if (!o.csv.empty()) {
    const int fd = ::open(o.csv.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, 0600);
    csv = fd >= 0 ? fdopen(fd, "w") : nullptr;
    if (!csv) {
      std::fprintf(stderr, "CSV nicht schreibbar: %s\n", o.csv.c_str());
      return 1;
    }
    char date[32];
    const std::time_t now = std::time(nullptr);
    std::strftime(date, sizeof(date), "%Y-%m-%d %H:%M:%S", std::localtime(&now));
    std::fprintf(csv, "# name=%s\n# zeit=%s\n# art=hand\n# threads=%d\n", name.c_str(), date, o.threads);
    std::fprintf(csv,
                 "name,bild,unix_ms,t_ms,seq,hell,beleuchtet,gesichter,augenabstand,hand,palm,"
                 "presence,verfolgt,rechts,p_keine,p_faust,p_offen,p_zeigen,p_runter,p_hoch,p_victory,p_love,"
                 "regel_hoch,daumen_winkel,daumen_oben,daumen_lang,streck_zeige,streck_mittel,"
                 "streck_ring,streck_klein,finger_nase,det_ms,palm_ms,hand_ms,geste_ms\n");
  }

  Preview pv(o.preview);
  winky::StrobeTracker strobe;
  winky::IrFrame frame;
  int n = 0, lit = 0, haende = 0;
  double first_frame_ms = -1;
  // Letzte bekannte Nase: Die Hand verdeckt beim Antippen oft das Gesicht
  float nase_x = 0, nase_y = 0, augen = 0;
  double nase_ms = -1e9;
  std::string err;
  std::fprintf(g_text, "Handmessung \"%s\" läuft %.0f s ...\n", name.c_str(), o.duration);
  for (;;) {
    if (g_stop) {
      if (csv) std::fclose(csv);
      std::fprintf(stderr, "Abgebrochen.\n");
      return 3;
    }
    if (first_frame_ms >= 0 && msSince(t0) - first_frame_ms >= o.duration * 1000.0) break;
    if (!s.cam->read(frame, 2000, err)) {
      std::fprintf(stderr, "\nKamerafehler: %s\n", err.c_str());
      if (csv) std::fclose(csv);
      return 1;
    }
    const double t_ms = msSince(t0);
    const long long unix_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                                  std::chrono::system_clock::now().time_since_epoch()).count();
    if (first_frame_ms < 0) first_frame_ms = t_ms;
    const auto st = strobe.push(frame.mean);
    ++n;
    if (!st.lit) continue;
    ++lit;
    auto t = Clock::now();
    const auto gefunden = m.detector->detect(frame.image);
    const double det_ms = msSince(t);
    LitResult r;
    r.n_faces = static_cast<int>(gefunden.size());
    if (!gefunden.empty()) {
      r.face = gefunden.front();
      nase_x = r.face.kps[4];
      nase_y = r.face.kps[5];
      augen = std::hypot(r.face.kps[2] - r.face.kps[0], r.face.kps[3] - r.face.kps[1]);
      nase_ms = t_ms;
    }
    const bool nase_bekannt = t_ms - nase_ms < 1000.0 && augen > 1.0f;
    const winky::HandResult h = m.hand->analyse(frame.image);
    std::vector<std::pair<float, float>> handpunkte;
    DaumenRegel regel;
    float finger_nase = -1;
    int top = 0;
    if (h.found) {
      ++haende;
      regel = daumenRegel(h.pts);
      for (int i = 0; i < winky::kHandPoints; ++i) handpunkte.emplace_back(h.pts[i * 2], h.pts[i * 2 + 1]);
      if (nase_bekannt) finger_nase = std::hypot(h.pts[8 * 2] - nase_x, h.pts[8 * 2 + 1] - nase_y) / augen;
      for (int i = 1; i < winky::kGestureCount; ++i)
        if (h.gesture[i] > h.gesture[top]) top = i;
    }
    if (csv) {
      std::fprintf(csv, "%s,%d,%lld,%.1f,%u,%.1f,1,%d,", name.c_str(), n, unix_ms, t_ms, frame.sequence,
                   frame.mean, r.n_faces);
      if (nase_bekannt) std::fprintf(csv, "%.1f,", augen);
      else std::fprintf(csv, ",");
      if (h.found) {
        std::fprintf(csv, "1,%.3f,%.3f,%d,%.3f,", h.palm_score, h.presence, h.tracked ? 1 : 0,
                     h.right_hand);
        for (float g : h.gesture) std::fprintf(csv, "%.4f,", g);
        std::fprintf(csv, "%d,%.1f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,", regel.hoch ? 1 : 0, regel.winkel,
                     regel.oben, regel.lang, regel.streck[0], regel.streck[1], regel.streck[2],
                     regel.streck[3]);
        if (finger_nase >= 0) std::fprintf(csv, "%.3f,", finger_nase);
        else std::fprintf(csv, ",");
      } else {
        std::fprintf(csv, "0,%.3f,,,,,,,,,,,,,,,,,,,,,", h.palm_score);
      }
      std::fprintf(csv, "%.1f,%.1f,%.1f,%.1f\n", det_ms, h.palm_ms, h.landmarks_ms, h.gesture_ms);
    }
    if (pv.on()) {
      pv.frame(frame.image, &r, {}, handpunkte);
      std::string geste = "null";
      if (h.found) geste = std::string("\"") + kGestenNamen[top] + "\"";
      pv.status(std::string("{\"modus\":\"hand\",\"t\":") +
                jsonNum((t_ms - first_frame_ms) / 1000.0, 1) + ",\"dauer\":" + jsonNum(o.duration, 0) +
                ",\"gesicht\":" + (r.n_faces ? "true" : "false") +
                ",\"hand\":" + (h.found ? "true" : "false") + ",\"geste\":" + geste +
                ",\"sicherheit\":" + (h.found ? jsonNum(h.gesture[top], 2) : "null") +
                ",\"daumen_hoch\":" + (h.found ? jsonNum(h.gesture[winky::kThumbUp], 2) : "null") +
                ",\"victory\":" + (h.found ? jsonNum(h.gesture[winky::kVictory], 2) : "null") +
                ",\"presence\":" + (h.found ? jsonNum(h.presence, 2) : "null") +
                ",\"regel_hoch\":" + (regel.hoch ? "true" : "false") +
                ",\"finger_nase\":" + (finger_nase >= 0 ? jsonNum(finger_nase, 2) : "null") + "}");
    } else {
      std::printf("\r  %4.1f s  beleuchtet %3d  Hand %3d  Geste %-16s %.2f  Regel %d  Finger-Nase %.2f   ",
                  (t_ms - first_frame_ms) / 1000.0, lit, haende, h.found ? kGestenNamen[top] : "-",
                  h.found ? h.gesture[top] : 0.0f, regel.hoch ? 1 : 0, finger_nase);
      std::fflush(stdout);
    }
  }
  s.cam->stop();
  if (csv && std::fclose(csv) != 0) {
    std::fprintf(stderr, "CSV konnte nicht vollständig geschrieben werden\n");
    return 1;
  }
  std::fprintf(g_text, "\nBilder %d, beleuchtet %d, mit Hand %d\n", n, lit, haende);
  return 0;
}

// Prüfbefehl ohne Kamera: Handzeichen in einem Graustufenbild (PGM, P5), zum Abgleich
// mit MediaPipe selbst. Aufruf: winky-messung handbild --name DATEI.pgm
int cmdHandbild(const Options& o) {
  FILE* f = std::fopen(o.name.c_str(), "rb");
  if (!f) {
    std::fprintf(stderr, "Bild nicht lesbar: %s\n", o.name.c_str());
    return 1;
  }
  char magic[3] = {};
  int w = 0, h = 0, maxv = 0;
  if (std::fscanf(f, "%2s %d %d %d", magic, &w, &h, &maxv) != 4 || std::string(magic) != "P5" ||
      w <= 0 || h <= 0 || w > 8192 || h > 8192 || maxv != 255) {
    std::fclose(f);
    std::fprintf(stderr, "kein 8-Bit-PGM\n");
    return 1;
  }
  std::fgetc(f);
  winky::GrayImage img(w, h);
  const size_t gelesen = std::fread(img.data.data(), 1, img.data.size(), f);
  std::fclose(f);
  if (gelesen != img.data.size()) return 1;
  Ort::Env env(ORT_LOGGING_LEVEL_ERROR, "winky-messung");
  Models m;
  Options o2 = o;
  o2.command = "hand";
  loadModels(&env, &o2, &m);
  if (!m.hand) {
    std::fprintf(stderr, "Handmodell fehlt: %s\n", m.error.c_str());
    return 1;
  }
  const auto r = m.hand->analyse(img, false);
  std::printf("{\"gefunden\":%s,\"palm\":%.4f,\"presence\":%.4f,\"rechts\":%.4f,\"gesten\":[",
              r.found ? "true" : "false", r.palm_score, r.presence, r.right_hand);
  for (int i = 0; i < winky::kGestureCount; ++i) std::printf("%s%.4f", i ? "," : "", r.gesture[i]);
  std::printf("],\"punkte\":[");
  for (int i = 0; i < winky::kHandPoints * 2; ++i) std::printf("%s%.2f", i ? "," : "", r.pts[i]);
  std::printf("],\"regel_hoch\":%s}\n", r.found && daumenRegel(r.pts).hoch ? "true" : "false");
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  const Options o = parse(argc, argv);
  if (o.preview) g_text = stderr;
  struct sigaction sa {};
  sa.sa_handler = onSignal;
  sigemptyset(&sa.sa_mask);
  sigaction(SIGTERM, &sa, nullptr);
  sigaction(SIGINT, &sa, nullptr);
  std::signal(SIGPIPE, SIG_IGN);
  try {
    if (o.command == "selbsttest") return cmdSelbsttest(o);
    if (o.command == "kamera") return cmdKamera(o);
    if (o.command == "vorschau") return cmdVorschau(o);
    if (o.command == "einlernen") return cmdEinlernen(o);
    if (o.command == "messen") return cmdMessen(o);
    if (o.command == "hand") return cmdHand(o);
    if (o.command == "handbild") return cmdHandbild(o);
  } catch (const std::exception& e) {
    std::fprintf(stderr, "Fehler: %s\n", e.what());
    return 1;
  }
  usage();
}
