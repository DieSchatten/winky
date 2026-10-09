// IR-Kamera direkt über V4L2 (Graustufen, mmap). Ohne libcamera: weniger Code im Anmeldepfad,
// schnellerer Start, die Farbkamera bleibt für andere Programme unberührt.
#pragma once

#include <cstddef>
#include <cstdint>
#include <deque>
#include <string>
#include <vector>

#include "image.h"

namespace winky {

struct IrFrame {
  GrayImage image;
  uint32_t sequence = 0;
  int64_t timestamp_us = 0;  // Kamerazeit (monoton)
  float mean = 0;
};

class V4l2IrCamera {
 public:
  explicit V4l2IrCamera(std::string device_path);
  ~V4l2IrCamera();
  V4l2IrCamera(const V4l2IrCamera&) = delete;
  V4l2IrCamera& operator=(const V4l2IrCamera&) = delete;

  // Öffnet das Gerät, setzt GREY width x height und startet den Datenstrom.
  bool start(int width, int height, std::string& error);
  // Wartet höchstens timeout_ms auf das nächste fehlerfreie Bild.
  bool read(IrFrame& frame, int timeout_ms, std::string& error);
  void stop();

  int width() const { return width_; }
  int height() const { return height_; }
  uint32_t droppedFrames() const { return dropped_; }

 private:
  struct Buffer {
    void* start = nullptr;
    size_t length = 0;
  };
  std::string path_;
  int fd_ = -1;
  int width_ = 0;
  int height_ = 0;
  int stride_ = 0;
  bool streaming_ = false;
  uint32_t dropped_ = 0;
  std::vector<Buffer> buffers_;
};

// Erkennt, ob ein Bild beleuchtet ist; der IR-Strahler blinkt bildweise (Helligkeit etwa 74 / 0).
class StrobeTracker {
 public:
  struct Result {
    bool lit = false;
    bool strobing = false;  // deutlicher Hell-Dunkel-Wechsel im Fenster
  };
  Result push(float mean);

 private:
  std::deque<float> window_;
};

}  // namespace winky
