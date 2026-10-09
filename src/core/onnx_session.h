// Dünne Hülle um eine ONNX-Runtime-Sitzung: gemeinsame Ort::Env, einstellbare Thread-Zahl,
// Abfrage der Ein- und Ausgabeformen.
#pragma once

#include <onnxruntime_cxx_api.h>

#include <memory>
#include <string>
#include <vector>

namespace winky {

class OnnxModel {
 public:
  OnnxModel(Ort::Env& env, const std::string& model_path, int threads);

  std::vector<Ort::Value> run(std::vector<float>& input, const std::vector<int64_t>& shape);
  // Mehrere Eingaben in der Reihenfolge des Modells
  std::vector<Ort::Value> run(const std::vector<std::vector<float>*>& inputs,
                              const std::vector<std::vector<int64_t>>& shapes);

  size_t inputCount() const { return input_names_.size(); }
  const std::string& inputName(size_t index) const { return input_names_.at(index); }

  std::vector<int64_t> inputShape(size_t index = 0) const;
  std::vector<int64_t> outputShape(size_t index = 0) const;

 private:
  std::unique_ptr<Ort::Session> session_;
  Ort::MemoryInfo memory_info_;
  std::vector<std::string> input_names_;
  std::vector<std::string> output_names_;
  std::vector<const char*> input_ptrs_;
  std::vector<const char*> output_ptrs_;
};

}  // namespace winky
