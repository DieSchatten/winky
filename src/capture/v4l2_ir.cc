#include "v4l2_ir.h"

#include <fcntl.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <utility>

namespace winky {

namespace {

int xioctl(int fd, unsigned long request, void* arg) {
  int r;
  do {
    r = ioctl(fd, request, arg);
  } while (r == -1 && errno == EINTR);
  return r;
}

std::string errnoText(const char* what) { return std::string(what) + ": " + std::strerror(errno); }

}  // namespace

V4l2IrCamera::V4l2IrCamera(std::string device_path) : path_(std::move(device_path)) {}

V4l2IrCamera::~V4l2IrCamera() { stop(); }

bool V4l2IrCamera::start(int width, int height, std::string& error) {
  stop();
  fd_ = ::open(path_.c_str(), O_RDWR | O_NONBLOCK | O_CLOEXEC);
  if (fd_ < 0) {
    error = errnoText("Kamera öffnen");
    return false;
  }
  struct stat st {};
  if (fstat(fd_, &st) != 0 || !S_ISCHR(st.st_mode)) {
    error = "Kamerapfad ist kein Zeichengerät";
    stop();
    return false;
  }

  v4l2_capability cap{};
  if (xioctl(fd_, VIDIOC_QUERYCAP, &cap) != 0) {
    error = errnoText("VIDIOC_QUERYCAP");
    stop();
    return false;
  }
  const uint32_t caps =
      (cap.capabilities & V4L2_CAP_DEVICE_CAPS) ? cap.device_caps : cap.capabilities;
  if (!(caps & V4L2_CAP_VIDEO_CAPTURE) || !(caps & V4L2_CAP_STREAMING)) {
    error = "Gerät kann keine Videoaufnahme per Streaming";
    stop();
    return false;
  }

  v4l2_format fmt{};
  fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  fmt.fmt.pix.width = static_cast<uint32_t>(width);
  fmt.fmt.pix.height = static_cast<uint32_t>(height);
  fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_GREY;
  fmt.fmt.pix.field = V4L2_FIELD_ANY;
  if (xioctl(fd_, VIDIOC_S_FMT, &fmt) != 0) {
    error = errnoText("VIDIOC_S_FMT");
    stop();
    return false;
  }
  if (fmt.fmt.pix.pixelformat != V4L2_PIX_FMT_GREY) {
    error = "Kamera liefert kein GREY-Format (falscher Knoten?)";
    stop();
    return false;
  }
  width_ = static_cast<int>(fmt.fmt.pix.width);
  height_ = static_cast<int>(fmt.fmt.pix.height);
  stride_ = fmt.fmt.pix.bytesperline ? static_cast<int>(fmt.fmt.pix.bytesperline) : width_;
  if (width_ <= 0 || height_ <= 0 || width_ > 4096 || height_ > 4096 || stride_ < width_) {
    error = "unplausible Bildgröße";
    stop();
    return false;
  }

  v4l2_requestbuffers req{};
  req.count = 4;
  req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  req.memory = V4L2_MEMORY_MMAP;
  if (xioctl(fd_, VIDIOC_REQBUFS, &req) != 0 || req.count < 2) {
    error = errnoText("VIDIOC_REQBUFS");
    stop();
    return false;
  }
  buffers_.resize(req.count);
  for (uint32_t i = 0; i < req.count; ++i) {
    v4l2_buffer buf{};
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    buf.index = i;
    if (xioctl(fd_, VIDIOC_QUERYBUF, &buf) != 0) {
      error = errnoText("VIDIOC_QUERYBUF");
      stop();
      return false;
    }
    void* p = mmap(nullptr, buf.length, PROT_READ, MAP_SHARED, fd_, buf.m.offset);
    if (p == MAP_FAILED) {
      error = errnoText("mmap");
      stop();
      return false;
    }
    buffers_[i].start = p;
    buffers_[i].length = buf.length;
    if (xioctl(fd_, VIDIOC_QBUF, &buf) != 0) {
      error = errnoText("VIDIOC_QBUF");
      stop();
      return false;
    }
  }

  v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  if (xioctl(fd_, VIDIOC_STREAMON, &type) != 0) {
    error = errnoText("VIDIOC_STREAMON");
    stop();
    return false;
  }
  streaming_ = true;
  return true;
}

bool V4l2IrCamera::read(IrFrame& frame, int timeout_ms, std::string& error) {
  if (fd_ < 0 || !streaming_) {
    error = "Kamera läuft nicht";
    return false;
  }
  using clock = std::chrono::steady_clock;
  const auto deadline = clock::now() + std::chrono::milliseconds(timeout_ms);
  const size_t needed = static_cast<size_t>(stride_) * static_cast<size_t>(height_);

  for (;;) {
    const auto left =
        std::chrono::duration_cast<std::chrono::milliseconds>(deadline - clock::now()).count();
    if (left <= 0) {
      error = "Zeitüberschreitung beim Warten auf ein Bild";
      return false;
    }
    pollfd pfd{fd_, POLLIN, 0};
    const int r = poll(&pfd, 1, static_cast<int>(left));
    if (r < 0) {
      if (errno == EINTR) continue;
      error = errnoText("poll");
      return false;
    }
    if (r == 0) continue;  // Schleife prüft die Frist
    if (pfd.revents & (POLLERR | POLLHUP | POLLNVAL)) {
      error = "Kamera meldet Fehler (getrennt?)";
      return false;
    }

    v4l2_buffer buf{};
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    if (xioctl(fd_, VIDIOC_DQBUF, &buf) != 0) {
      if (errno == EAGAIN) continue;
      error = errnoText("VIDIOC_DQBUF");
      return false;
    }

    bool ok = buf.index < buffers_.size() && !(buf.flags & V4L2_BUF_FLAG_ERROR) &&
              buffers_[buf.index].length >= needed && (buf.bytesused == 0 || buf.bytesused >= needed);
    if (ok) {
      frame.image = GrayImage(width_, height_);
      const auto* src = static_cast<const uint8_t*>(buffers_[buf.index].start);
      for (int y = 0; y < height_; ++y) {
        std::memcpy(&frame.image.data[static_cast<size_t>(y) * width_],
                    src + static_cast<size_t>(y) * stride_, static_cast<size_t>(width_));
      }
      frame.sequence = buf.sequence;
      frame.timestamp_us =
          static_cast<int64_t>(buf.timestamp.tv_sec) * 1000000 + buf.timestamp.tv_usec;
      frame.mean = meanBrightness(frame.image);
    } else {
      ++dropped_;
    }

    if (xioctl(fd_, VIDIOC_QBUF, &buf) != 0) {
      error = errnoText("VIDIOC_QBUF");
      return false;
    }
    if (ok) return true;
  }
}

void V4l2IrCamera::stop() {
  if (fd_ >= 0 && streaming_) {
    v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    xioctl(fd_, VIDIOC_STREAMOFF, &type);
  }
  streaming_ = false;
  for (auto& b : buffers_) {
    if (b.start) munmap(b.start, b.length);
  }
  buffers_.clear();
  if (fd_ >= 0) {
    v4l2_requestbuffers req{};
    req.count = 0;
    req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    xioctl(fd_, VIDIOC_REQBUFS, &req);
    ::close(fd_);
  }
  fd_ = -1;
}

StrobeTracker::Result StrobeTracker::push(float mean) {
  window_.push_back(mean);
  while (window_.size() > 4) window_.pop_front();
  const auto [lo_it, hi_it] = std::minmax_element(window_.begin(), window_.end());
  const float lo = *lo_it, hi = *hi_it;
  Result r;
  if (window_.size() >= 2 && hi - lo >= 8.0f) {
    r.strobing = true;
    r.lit = mean >= lo + 0.5f * (hi - lo);
  } else {
    r.lit = mean >= 12.0f;
  }
  return r;
}

}  // namespace winky
