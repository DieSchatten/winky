#include "face_embedding.h"

#include <cmath>
#include <stdexcept>

#include "face_align.h"

namespace winky {

FaceEmbedder::FaceEmbedder(Ort::Env& env, const std::string& model_path, int threads)
    : model_(env, model_path, threads) {
  const auto ein = model_.inputShape();
  if (ein.size() != 4 || ein[1] != 3 || (ein[2] > 0 && ein[2] != kAlignedFaceSize) ||
      (ein[3] > 0 && ein[3] != kAlignedFaceSize)) {
    throw std::runtime_error("Erkennungsmodell erwartet keine 3 x 112 x 112-Eingabe");
  }
  const auto aus = model_.outputShape();
  if (aus.size() != 2 || aus[1] <= 0) {
    throw std::runtime_error("unerwartete Ausgabeform des Erkennungsmodells");
  }
  dim_ = static_cast<int>(aus[1]);
}

std::vector<float> FaceEmbedder::embed(const GrayImage& aligned) {
  if (aligned.width != kAlignedFaceSize || aligned.height != kAlignedFaceSize) return {};
  const size_t ebene = static_cast<size_t>(kAlignedFaceSize) * kAlignedFaceSize;
  buffer_.resize(ebene * 3);
  for (size_t i = 0; i < ebene; ++i) {
    buffer_[i] = buffer_[ebene + i] = buffer_[2 * ebene + i] = aligned.data[i];
  }
  const std::vector<int64_t> form = {1, 3, kAlignedFaceSize, kAlignedFaceSize};
  auto aus = model_.run(buffer_, form);
  if (aus.empty()) return {};
  const float* d = aus[0].GetTensorData<float>();
  std::vector<float> v(d, d + dim_);
  double laenge = 0.0;
  for (float x : v) {
    if (!std::isfinite(x)) return {};
    laenge += static_cast<double>(x) * x;
  }
  laenge = std::sqrt(laenge);
  if (!(laenge > 1e-9)) return {};
  for (float& x : v) x = static_cast<float>(x / laenge);
  return v;
}

float cosine(const std::vector<float>& a, const float* b) {
  double s = 0.0;
  for (size_t i = 0; i < a.size(); ++i) s += static_cast<double>(a[i]) * b[i];
  return static_cast<float>(s);
}

}  // namespace winky
