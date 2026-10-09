// Merkmalsvektor eines ausgerichteten Gesichts mit SFace (OpenCV Zoo, Apache-2.0,
// Fassung 2021dec): 112 x 112, drei Kanäle mit Rohwerten 0..255, 128 Werte.
#pragma once

#include <string>
#include <vector>

#include "image.h"
#include "onnx_session.h"

namespace winky {

class FaceEmbedder {
 public:
  FaceEmbedder(Ort::Env& env, const std::string& model_path, int threads);

  // Auf Länge 1 gebrachter Merkmalsvektor; leer bei Fehler.
  std::vector<float> embed(const GrayImage& aligned);

  int dim() const { return dim_; }

 private:
  OnnxModel model_;
  int dim_ = 0;
  std::vector<float> buffer_;
};

// Skalarprodukt zweier Vektoren der Länge 1 = Kosinus-Ähnlichkeit.
float cosine(const std::vector<float>& a, const float* b);

}  // namespace winky
