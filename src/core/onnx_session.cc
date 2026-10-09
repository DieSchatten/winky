#include "onnx_session.h"

namespace winky {

OnnxModel::OnnxModel(Ort::Env& env, const std::string& model_path, int threads)
    : memory_info_(Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault)) {
  Ort::SessionOptions opts;
  opts.SetIntraOpNumThreads(threads > 0 ? threads : 1);
  opts.SetInterOpNumThreads(1);
  opts.SetExecutionMode(ExecutionMode::ORT_SEQUENTIAL);
  opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);

  session_ = std::make_unique<Ort::Session>(env, model_path.c_str(), opts);

  Ort::AllocatorWithDefaultOptions allocator;
  for (size_t i = 0; i < session_->GetInputCount(); ++i) {
    input_names_.emplace_back(session_->GetInputNameAllocated(i, allocator).get());
  }
  for (size_t i = 0; i < session_->GetOutputCount(); ++i) {
    output_names_.emplace_back(session_->GetOutputNameAllocated(i, allocator).get());
  }
  for (const auto& s : input_names_) input_ptrs_.push_back(s.c_str());
  for (const auto& s : output_names_) output_ptrs_.push_back(s.c_str());
}

std::vector<Ort::Value> OnnxModel::run(std::vector<float>& input,
                                       const std::vector<int64_t>& shape) {
  Ort::Value tensor = Ort::Value::CreateTensor<float>(memory_info_, input.data(), input.size(),
                                                      shape.data(), shape.size());
  return session_->Run(Ort::RunOptions{nullptr}, input_ptrs_.data(), &tensor, 1,
                       output_ptrs_.data(), output_ptrs_.size());
}

std::vector<Ort::Value> OnnxModel::run(const std::vector<std::vector<float>*>& inputs,
                                       const std::vector<std::vector<int64_t>>& shapes) {
  std::vector<Ort::Value> tensors;
  for (size_t i = 0; i < inputs.size(); ++i) {
    tensors.push_back(Ort::Value::CreateTensor<float>(memory_info_, inputs[i]->data(),
                                                      inputs[i]->size(), shapes[i].data(),
                                                      shapes[i].size()));
  }
  return session_->Run(Ort::RunOptions{nullptr}, input_ptrs_.data(), tensors.data(),
                       tensors.size(), output_ptrs_.data(), output_ptrs_.size());
}

std::vector<int64_t> OnnxModel::inputShape(size_t index) const {
  return session_->GetInputTypeInfo(index).GetTensorTypeAndShapeInfo().GetShape();
}

std::vector<int64_t> OnnxModel::outputShape(size_t index) const {
  return session_->GetOutputTypeInfo(index).GetTensorTypeAndShapeInfo().GetShape();
}

}  // namespace winky
