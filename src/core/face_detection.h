// Gesichtssuche mit YuNet 2023mar (OpenCV Zoo, MIT) samt 5 Punkten. Eingabe 640 x 640, Bild oben
// links; Ausgabe je Schrittweite 8/16/32 ein Raster mit Klassen- und Objektwert, Rahmen (Versatz
// und log. Größe, in Schrittweiten) und 5 Punkten.
#pragma once

#include <array>
#include <string>
#include <vector>

#include "image.h"
#include "onnx_session.h"

namespace winky {

struct FaceBox {
  float x1 = 0, y1 = 0, x2 = 0, y2 = 0;
  float conf = 0;
  std::array<float, 10> kps{};      // 5 x (x, y) in Bildkoordinaten
  std::array<float, 5> kps_conf{};  // Sicherheit je Punkt (YuNet: Wert des Gesichts)
  bool has_kps = false;

  float width() const { return x2 - x1; }
  float height() const { return y2 - y1; }
  float area() const { return width() * height(); }
};

class FaceDetector {
 public:
  // conf: kleinster Gesichtswert, iou: Überlappung, ab der sich zwei Rahmen verdrängen
  FaceDetector(Ort::Env& env, const std::string& model_path, int threads, float conf = 0.5f,
               float iou = 0.3f);

  // Gefundene Gesichter, größtes zuerst.
  std::vector<FaceBox> detect(const GrayImage& img);

  int inputSize() const { return seite_; }

 private:
  OnnxModel model_;
  int seite_ = 640;
  float conf_;
  float iou_;
  std::vector<float> buffer_;
};

}  // namespace winky
