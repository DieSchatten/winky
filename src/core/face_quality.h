// Qualitätsmaße eines gefundenen Gesichts. Nur Gesichter, die alle Grenzen
// einhalten, werden verglichen; das filtert Unschärfe, Anschnitt und Profil.
#pragma once

#include "face_detection.h"
#include "image.h"

namespace winky {

struct QualityLimits {
  float min_conf = 0.6f;
  float min_width_anteil = 0.14f;  // Gesichtsbreite relativ zur Bildbreite (90 px bei 640)
  float min_kps_conf = 0.5f;
  float max_roll_deg = 20.0f;
  float min_yaw_ratio = 0.25f;  // Nase zwischen den Augen: 0,5 = frontal
  float max_yaw_ratio = 0.75f;
  float max_saturated = 0.05f;  // Anteil überbelichteter Pixel im Gesicht
};

struct FaceQuality {
  float conf = 0;
  float width = 0;
  float kps_min = 0;
  float roll_deg = 0;
  float yaw_ratio = 0;
  float eye_dist = 0;
  float mean = 0;       // Helligkeit im Gesicht
  float saturated = 0;  // Anteil Pixel >= 250
  bool usable = false;
  const char* reason = "";
};

FaceQuality assessFace(const GrayImage& img, const FaceBox& face, const QualityLimits& lim);

// Mittlere Helligkeit im Rechteck des Gesichts (z. B. im dunklen Nachbarbild).
float regionMean(const GrayImage& img, const FaceBox& face);

}  // namespace winky
