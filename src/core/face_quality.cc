#include "face_quality.h"

#include <algorithm>
#include <cmath>

namespace winky {

namespace {

struct Rect {
  int x1, y1, x2, y2;
};

Rect clampRect(const GrayImage& img, const FaceBox& f) {
  Rect r;
  r.x1 = std::clamp(static_cast<int>(f.x1), 0, img.width);
  r.y1 = std::clamp(static_cast<int>(f.y1), 0, img.height);
  r.x2 = std::clamp(static_cast<int>(f.x2), 0, img.width);
  r.y2 = std::clamp(static_cast<int>(f.y2), 0, img.height);
  return r;
}

}  // namespace

float regionMean(const GrayImage& img, const FaceBox& face) {
  if (img.empty()) return 0.0f;
  const Rect r = clampRect(img, face);
  uint64_t sum = 0, n = 0;
  for (int y = r.y1; y < r.y2; ++y) {
    for (int x = r.x1; x < r.x2; ++x) {
      sum += img.at(y, x);
      ++n;
    }
  }
  return n ? static_cast<float>(sum) / static_cast<float>(n) : 0.0f;
}

FaceQuality assessFace(const GrayImage& img, const FaceBox& face, const QualityLimits& lim) {
  FaceQuality q;
  q.conf = face.conf;
  q.width = face.width();

  const Rect r = clampRect(img, face);
  uint64_t sum = 0, n = 0, sat = 0;
  for (int y = r.y1; y < r.y2; ++y) {
    for (int x = r.x1; x < r.x2; ++x) {
      const uint8_t v = img.at(y, x);
      sum += v;
      sat += (v >= 250);
      ++n;
    }
  }
  q.mean = n ? static_cast<float>(sum) / n : 0.0f;
  q.saturated = n ? static_cast<float>(sat) / n : 1.0f;

  if (face.has_kps) {
    q.kps_min = *std::min_element(face.kps_conf.begin(), face.kps_conf.end());
    const float lx = face.kps[0], ly = face.kps[1];  // linkes Auge (im Bild links)
    const float rx = face.kps[2], ry = face.kps[3];  // rechtes Auge
    const float nx = face.kps[4];                    // Nase
    q.eye_dist = std::hypot(rx - lx, ry - ly);
    q.roll_deg = static_cast<float>(std::atan2(ry - ly, rx - lx) * 180.0 / M_PI);
    q.yaw_ratio = (rx - lx) != 0.0f ? (nx - lx) / (rx - lx) : -1.0f;
  }

  if (!face.has_kps) {
    q.reason = "keine_punkte";
  } else if (q.conf < lim.min_conf) {
    q.reason = "unsicher";
  } else if (q.width < std::max(40.0f, lim.min_width_anteil * img.width)) {
    q.reason = "zu_klein";
  } else if (q.kps_min < lim.min_kps_conf) {
    q.reason = "punkte_unsicher";
  } else if (std::fabs(q.roll_deg) > lim.max_roll_deg) {
    q.reason = "geneigt";
  } else if (q.yaw_ratio < lim.min_yaw_ratio || q.yaw_ratio > lim.max_yaw_ratio) {
    q.reason = "gedreht";
  } else if (q.saturated > lim.max_saturated) {
    q.reason = "ueberbelichtet";
  } else {
    q.usable = true;
    q.reason = "ok";
  }
  return q;
}

}  // namespace winky
