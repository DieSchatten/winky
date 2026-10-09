#include "face_detection.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace winky {

namespace {

constexpr int kSchritte[] = {8, 16, 32};

float ueberlappung(const FaceBox& a, const FaceBox& b) {
  const float b_ = std::max(0.0f, std::min(a.x2, b.x2) - std::max(a.x1, b.x1));
  const float h_ = std::max(0.0f, std::min(a.y2, b.y2) - std::max(a.y1, b.y1));
  const float schnitt = b_ * h_;
  const float vereinigt = a.area() + b.area() - schnitt;
  return vereinigt > 0 ? schnitt / vereinigt : 0.0f;
}

float begrenzt(float v) { return std::isfinite(v) ? std::clamp(v, 0.0f, 1.0f) : 0.0f; }

}  // namespace

FaceDetector::FaceDetector(Ort::Env& env, const std::string& model_path, int threads, float conf,
                           float iou_thres)
    : model_(env, model_path, threads), conf_(conf), iou_(iou_thres) {
  const auto form = model_.inputShape();
  if (form.size() != 4 || form[1] != 3 || form[2] <= 0 || form[2] != form[3] ||
      form[2] % 32 != 0) {
    throw std::runtime_error("Gesichtssuche: Eingabe muss 1 x 3 x N x N sein (N durch 32 teilbar)");
  }
  seite_ = static_cast<int>(form[2]);
}

std::vector<FaceBox> FaceDetector::detect(const GrayImage& img) {
  const Einpassung e = einpassen(img, seite_, buffer_);
  const std::vector<int64_t> form = {1, 3, seite_, seite_};
  auto aus = model_.run(buffer_, form);
  if (aus.size() != 12) throw std::runtime_error("Gesichtssuche: 12 Ausgaben erwartet");

  // Ausgaben in Modellreihenfolge: cls_8/16/32, obj_8/16/32, bbox_8/16/32, kps_8/16/32
  std::vector<FaceBox> kandidaten;
  for (int s = 0; s < 3; ++s) {
    const int schritt = kSchritte[s];
    const int spalten = seite_ / schritt;
    const int felder = spalten * spalten;
    const float* cls = aus[s].GetTensorData<float>();
    const float* obj = aus[3 + s].GetTensorData<float>();
    const float* box = aus[6 + s].GetTensorData<float>();
    const float* kps = aus[9 + s].GetTensorData<float>();
    if (aus[6 + s].GetTensorTypeAndShapeInfo().GetElementCount() !=
        static_cast<size_t>(felder) * 4) {
      throw std::runtime_error("Gesichtssuche: Ausgabe passt nicht zur Eingabegröße");
    }
    for (int i = 0; i < felder; ++i) {
      const float wert = std::sqrt(begrenzt(cls[i]) * begrenzt(obj[i]));
      if (!(wert >= conf_)) continue;
      const int zeile = i / spalten, spalte = i % spalten;
      const float* r = box + 4 * i;
      const float mx = (spalte + r[0]) * schritt, my = (zeile + r[1]) * schritt;
      const float b = std::exp(r[2]) * schritt, h = std::exp(r[3]) * schritt;
      if (!std::isfinite(mx + my + b + h)) continue;
      FaceBox f;
      f.x1 = mx - b / 2, f.x2 = mx + b / 2, f.y1 = my - h / 2, f.y2 = my + h / 2;
      f.conf = wert;
      f.has_kps = true;
      const float* p = kps + 10 * i;
      for (int k = 0; k < 5; ++k) {
        f.kps[2 * k] = (spalte + p[2 * k]) * schritt;
        f.kps[2 * k + 1] = (zeile + p[2 * k + 1]) * schritt;
        f.kps_conf[k] = wert;
      }
      kandidaten.push_back(f);
    }
  }

  // Doppelte Treffer desselben Gesichts: der stärkste bleibt
  std::sort(kandidaten.begin(), kandidaten.end(),
            [](const FaceBox& a, const FaceBox& b) { return a.conf > b.conf; });
  std::vector<FaceBox> behalten;
  for (const auto& k : kandidaten) {
    bool doppelt = false;
    for (const auto& b : behalten) doppelt = doppelt || ueberlappung(k, b) > iou_;
    if (!doppelt) behalten.push_back(k);
    if (behalten.size() >= 10) break;
  }

  // Zurück in Kamerakoordinaten
  const float zurueck = 1.0f / e.faktor;
  std::vector<FaceBox> ergebnis;
  for (auto f : behalten) {
    f.x1 = std::clamp(f.x1 * zurueck, 0.0f, static_cast<float>(img.width));
    f.x2 = std::clamp(f.x2 * zurueck, 0.0f, static_cast<float>(img.width));
    f.y1 = std::clamp(f.y1 * zurueck, 0.0f, static_cast<float>(img.height));
    f.y2 = std::clamp(f.y2 * zurueck, 0.0f, static_cast<float>(img.height));
    for (float& v : f.kps) v *= zurueck;
    if (f.width() > 1.0f && f.height() > 1.0f) ergebnis.push_back(f);
  }
  std::sort(ergebnis.begin(), ergebnis.end(),
            [](const FaceBox& a, const FaceBox& b) { return a.area() > b.area(); });
  return ergebnis;
}

}  // namespace winky
