#include "hand_gesture.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <numeric>
#include <stdexcept>

namespace winky {

namespace {

constexpr int kPalmInput = 192;
constexpr int kHandInput = 224;
constexpr int kPalmValues = 18;   // Rahmen (4) + 7 Punkte (x, y)
constexpr float kNormalizeZ = 0.4f;  // wie hand_landmarks_detector_graph (kLandmarksNormalizeZ)
// Punkte für den Folgeausschnitt, ohne Fingerspitzen (MediaPipe kPartialLandmarkIndices)
constexpr int kRahmenPunkte[] = {0, 1, 2, 3, 5, 6, 9, 10, 13, 14, 17, 18};

double msSince(std::chrono::steady_clock::time_point t0) {
  return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
}

float sigmoid(float x) { return 1.0f / (1.0f + std::exp(-x)); }

// Gedrehter quadratischer Ausschnitt: Bildpunkt = o + u * spalte + v * zeile
struct Ausschnitt {
  double ox, oy, ux, uy, vx, vy;
  void punkt(double u, double v, double& x, double& y) const {
    x = ox + ux * u + vx * v;
    y = oy + uy * u + vy * v;
  }
};

Ausschnitt ausschnitt(double cx, double cy, double seite, double drehung, int netz) {
  const double k = seite / netz, c = std::cos(drehung), s = std::sin(drehung);
  Ausschnitt a{0, 0, c * k, s * k, -s * k, c * k};
  a.ox = cx - (a.ux + a.vx) * netz / 2.0;
  a.oy = cy - (a.uy + a.vy) * netz / 2.0;
  return a;
}

// Schreibt den Ausschnitt als NHWC-Floats 0..1 mit drei gleichen Kanälen
void fuellen(const GrayImage& img, const Ausschnitt& a, int netz, std::vector<float>& out) {
  out.resize(static_cast<size_t>(netz) * netz * 3);
  for (int v = 0; v < netz; ++v) {
    for (int u = 0; u < netz; ++u) {
      double x, y;
      a.punkt(u + 0.5, v + 0.5, x, y);
      const float g = sampleBilinear(img, x - 0.5, y - 0.5) / 255.0f;
      float* p = &out[(static_cast<size_t>(v) * netz + u) * 3];
      p[0] = p[1] = p[2] = g;
    }
  }
}

// Auf Handgelenk (Punkt 0) und Spannweite 1 normieren (LandmarksToMatrixCalculator)
void normieren(std::vector<float>& p) {
  const float x0 = p[0], y0 = p[1], z0 = p[2];
  float min_x = 1e30f, max_x = -1e30f, min_y = 1e30f, max_y = -1e30f;
  for (int i = 0; i < kHandPoints; ++i) {
    p[i * 3] -= x0;
    p[i * 3 + 1] -= y0;
    p[i * 3 + 2] -= z0;
    min_x = std::min(min_x, p[i * 3]);
    max_x = std::max(max_x, p[i * 3]);
    min_y = std::min(min_y, p[i * 3 + 1]);
    max_y = std::max(max_y, p[i * 3 + 1]);
  }
  const float skala = std::max(max_x - min_x, max_y - min_y) + 1e-5f;
  for (float& v : p) v /= skala;
}

}  // namespace

HandGestureRecognizer::HandGestureRecognizer(Ort::Env& env, const std::string& dir, int threads,
                                             float min_palm)
    : palm_(env, dir + "/hand_detector.onnx", threads),
      landmarks_(env, dir + "/hand_landmarks_detector.onnx", threads),
      embedder_(env, dir + "/gesture_embedder.onnx", 1),
      classifier_(env, dir + "/canned_gesture_classifier.onnx", 1),
      min_palm_(min_palm) {
  const auto pin = palm_.inputShape();
  if (pin.size() != 4 || pin[1] != kPalmInput || pin[2] != kPalmInput || pin[3] != 3) {
    throw std::runtime_error("Handflächenmodell erwartet keine 192x192x3-Eingabe");
  }
  const auto lin = landmarks_.inputShape();
  if (lin.size() != 4 || lin[1] != kHandInput || lin[2] != kHandInput || lin[3] != 3) {
    throw std::runtime_error("Handpunktmodell erwartet keine 224x224x3-Eingabe");
  }
  if (embedder_.inputCount() != 3 || embedder_.inputName(0) != "hand" ||
      embedder_.inputName(1) != "handedness" || embedder_.inputName(2) != "world_hand") {
    throw std::runtime_error("unerwartete Eingaben des Gestenmodells");
  }
  // Ankerraster wie SsdAnchorsCalculator: 2 Anker je Ebene, gleiche Schrittweiten zusammengefasst
  const int strides[4] = {8, 16, 16, 16};
  for (int ebene = 0; ebene < 4;) {
    int bis = ebene, je_ort = 0;
    while (bis < 4 && strides[bis] == strides[ebene]) {
      je_ort += 2;
      ++bis;
    }
    const int n = (kPalmInput + strides[ebene] - 1) / strides[ebene];
    for (int y = 0; y < n; ++y)
      for (int x = 0; x < n; ++x)
        for (int a = 0; a < je_ort; ++a) anchors_.push_back({(x + 0.5f) / n, (y + 0.5f) / n});
    ebene = bis;
  }
  if (anchors_.size() != 2016) throw std::runtime_error("Ankerraster hat nicht 2016 Anker");
}

HandResult HandGestureRecognizer::analyse(const GrayImage& img, bool verfolgen) {
  HandResult r;
  if (img.empty()) return r;
  double mx, my, seite, drehung;
  if (verfolgen && spur_) {
    r.tracked = true;
    mx = spur_x_, my = spur_y_, seite = spur_seite_, drehung = spur_drehung_;
  } else if (!handflaeche(img, r, mx, my, seite, drehung)) {
    spur_ = false;
    return r;
  }
  punkteUndGeste(img, r, mx, my, seite, drehung);
  spur_ = verfolgen && r.found && r.presence >= 0.5f;
  if (spur_) {
    const auto& p = r.pts;
    const double x1 = ((p[5 * 2] + p[13 * 2]) / 2 + p[9 * 2]) / 2;
    const double y1 = ((p[5 * 2 + 1] + p[13 * 2 + 1]) / 2 + p[9 * 2 + 1]) / 2;
    double d = M_PI / 2 - std::atan2(-(y1 - p[1]), x1 - p[0]);
    d = d - 2 * M_PI * std::floor((d + M_PI) / (2 * M_PI));
    // Rahmen um die Punkte im gedrehten System
    const double c = std::cos(d), s2 = std::sin(d);
    double umin = 1e30, umax = -1e30, vmin = 1e30, vmax = -1e30;
    for (int i : kRahmenPunkte) {
      const double u = c * p[i * 2] + s2 * p[i * 2 + 1], v = -s2 * p[i * 2] + c * p[i * 2 + 1];
      umin = std::min(umin, u), umax = std::max(umax, u), vmin = std::min(vmin, v), vmax = std::max(vmax, v);
    }
    const double uc = (umin + umax) / 2, vc = (vmin + vmax) / 2, bw = umax - umin, bh = vmax - vmin;
    const double cx = c * uc - s2 * vc, cy = s2 * uc + c * vc;
    spur_x_ = cx + 0.1 * bh * s2;
    spur_y_ = cy - 0.1 * bh * c;
    spur_seite_ = std::max(bw, bh) * 2.0;
    spur_drehung_ = d;
  }
  return r;
}

bool HandGestureRecognizer::handflaeche(const GrayImage& img, HandResult& r, double& mx,
                                        double& my, double& seite, double& drehung) {
  const int W = img.width, H = img.height;

  // 1. Handfläche: Bild seitenverhältnistreu in 192 x 192, Rand schwarz
  auto t = std::chrono::steady_clock::now();
  const float s = std::min(static_cast<float>(kPalmInput) / W, static_cast<float>(kPalmInput) / H);
  const float pad_x = (kPalmInput - W * s) / 2.0f, pad_y = (kPalmInput - H * s) / 2.0f;
  const Ausschnitt lb{-pad_x / s, -pad_y / s, 1.0 / s, 0, 0, 1.0 / s};
  fuellen(img, lb, kPalmInput, buffer_);
  auto out = palm_.run(buffer_, {1, kPalmInput, kPalmInput, 3});
  if (out.size() < 2) return false;
  const float* reg = out[0].GetTensorData<float>();
  const float* cls = out[1].GetTensorData<float>();
  int best = 0;
  float best_score = 0;
  for (size_t i = 0; i < anchors_.size(); ++i) {
    const float sc = sigmoid(std::max(-100.0f, std::min(100.0f, cls[i])));
    if (sc > best_score) {
      best_score = sc;
      best = static_cast<int>(i);
    }
  }
  r.palm_ms = msSince(t);
  r.palm_score = best_score;
  if (best_score < min_palm_) return false;
  const float* b = &reg[best * kPalmValues];
  const Anchor& an = anchors_[best];
  auto bild_x = [&](float v) { return (v * kPalmInput - pad_x) / s; };
  auto bild_y = [&](float v) { return (v * kPalmInput - pad_y) / s; };
  const double cx = bild_x(b[0] / kPalmInput + an.x), cy = bild_y(b[1] / kPalmInput + an.y);
  const double bw = b[2] / s, bh = b[3] / s;
  const double k0x = bild_x(b[4] / kPalmInput + an.x), k0y = bild_y(b[5] / kPalmInput + an.y);
  const double k2x = bild_x(b[8] / kPalmInput + an.x), k2y = bild_y(b[9] / kPalmInput + an.y);

  // 2. Ausschnitt: Handgelenk -> Mittelfinger-Ansatz auf 90° drehen, 2,6-fach, nach oben schieben
  drehung = M_PI / 2 - std::atan2(-(k2y - k0y), k2x - k0x);
  drehung = drehung - 2 * M_PI * std::floor((drehung + M_PI) / (2 * M_PI));
  mx = cx + 0.5 * bh * std::sin(drehung);
  my = cy - 0.5 * bh * std::cos(drehung);
  seite = std::max(bw, bh) * 2.6;
  return true;
}

void HandGestureRecognizer::punkteUndGeste(const GrayImage& img, HandResult& r, double mx,
                                           double my, double seite, double drehung) {
  const Ausschnitt a = ausschnitt(mx, my, seite, drehung, kHandInput);
  auto t = std::chrono::steady_clock::now();
  fuellen(img, a, kHandInput, buffer_);
  auto lo = landmarks_.run(buffer_, {1, kHandInput, kHandInput, 3});
  r.landmarks_ms = msSince(t);
  if (lo.size() < 4) return;
  const float* lm = lo[0].GetTensorData<float>();
  r.presence = lo[1].GetTensorData<float>()[0];
  r.right_hand = lo[2].GetTensorData<float>()[0];
  const float* welt = lo[3].GetTensorData<float>();

  std::vector<float> hand(kHandPoints * 3), weltpunkte(kHandPoints * 3), haendig = {r.right_hand};
  const double k = seite / kHandInput, c = std::cos(drehung), sn = std::sin(drehung);
  for (int i = 0; i < kHandPoints; ++i) {
    double x, y;
    a.punkt(lm[i * 3], lm[i * 3 + 1], x, y);
    if (!std::isfinite(x) || !std::isfinite(y)) return;
    hand[i * 3] = static_cast<float>(x);
    hand[i * 3 + 1] = static_cast<float>(y);
    hand[i * 3 + 2] = static_cast<float>(lm[i * 3 + 2] * k / kNormalizeZ);
    r.pts[i * 2] = static_cast<float>(x);
    r.pts[i * 2 + 1] = static_cast<float>(y);
    weltpunkte[i * 3] = static_cast<float>(c * welt[i * 3] - sn * welt[i * 3 + 1]);
    weltpunkte[i * 3 + 1] = static_cast<float>(sn * welt[i * 3] + c * welt[i * 3 + 1]);
    weltpunkte[i * 3 + 2] = welt[i * 3 + 2];
  }
  r.found = true;

  // 3. Geste
  t = std::chrono::steady_clock::now();
  normieren(hand);
  normieren(weltpunkte);
  auto eo = embedder_.run({&hand, &haendig, &weltpunkte},
                          {{1, kHandPoints, 3}, {1, 1}, {1, kHandPoints, 3}});
  if (!eo.empty()) {
    const float* e = eo[0].GetTensorData<float>();
    std::vector<float> merkmal(e, e + 128);
    auto co = classifier_.run(merkmal, {1, 128});
    if (!co.empty()) {
      const float* p = co[0].GetTensorData<float>();
      const float summe = std::accumulate(p, p + kGestureCount, 0.0f);
      const bool wahrscheinlichkeiten = summe > 0.98f && summe < 1.02f &&
                                        std::all_of(p, p + kGestureCount, [](float v) { return v >= 0; });
      float mx_l = *std::max_element(p, p + kGestureCount), z = 0;
      for (int i = 0; i < kGestureCount; ++i) {
        r.gesture[i] = wahrscheinlichkeiten ? p[i] : std::exp(p[i] - mx_l);
        z += r.gesture[i];
      }
      if (!wahrscheinlichkeiten)
        for (float& v : r.gesture) v /= z;
    }
  }
  r.gesture_ms = msSince(t);
}

}  // namespace winky
