// Gesichtsausrichtung: die 5 Gesichtspunkte per Ähnlichkeitsabbildung auf feste Sollpositionen
// im 112 x 112-Bild (übliche Vorlage dieser Netzgröße, mit der auch SFace trainiert wurde).
#pragma once

#include <array>
#include <cmath>

#include "image.h"

namespace winky {

constexpr int kAlignedFaceSize = 112;

// Wie YuNet: Auge links/rechts im Bild, Nasenspitze, Mundwinkel links/rechts (je x, y).
constexpr std::array<float, 10> kSollPunkte = {38.2946f, 51.6963f, 73.5318f, 51.5014f,
                                               56.0252f, 71.7366f, 41.5493f, 92.3655f,
                                               70.7299f, 92.2041f};

// Ähnlichkeitsabbildung ziel = s·R·quelle + t als (a, b, tx, ty), a = s·cos, b = s·sin;
// kleinste Quadrate mit schwerpunktfreien q, z: a = Σ(q·z) / Σ|q|², b = Σ(q×z) / Σ|q|².
struct Aehnlichkeit {
  double a = 1, b = 0, tx = 0, ty = 0;
};

inline bool schaetzeAehnlichkeit(const std::array<float, 10>& quelle,
                                 const std::array<float, 10>& ziel, Aehnlichkeit& t) {
  constexpr int n = 5;
  double qx = 0, qy = 0, zx = 0, zy = 0;
  for (int i = 0; i < n; ++i) {
    qx += quelle[2 * i];
    qy += quelle[2 * i + 1];
    zx += ziel[2 * i];
    zy += ziel[2 * i + 1];
  }
  qx /= n, qy /= n, zx /= n, zy /= n;
  double nenner = 0, punkt = 0, kreuz = 0;
  for (int i = 0; i < n; ++i) {
    const double ux = quelle[2 * i] - qx, uy = quelle[2 * i + 1] - qy;
    const double vx = ziel[2 * i] - zx, vy = ziel[2 * i + 1] - zy;
    nenner += ux * ux + uy * uy;
    punkt += ux * vx + uy * vy;
    kreuz += ux * vy - uy * vx;
  }
  if (!(nenner > 1e-6) || !std::isfinite(nenner)) return false;
  t.a = punkt / nenner;
  t.b = kreuz / nenner;
  t.tx = zx - (t.a * qx - t.b * qy);
  t.ty = zy - (t.b * qx + t.a * qy);
  const double s = std::hypot(t.a, t.b);
  return std::isfinite(s) && s > 1e-6;
}

// Ausgerichteter 112 x 112-Ausschnitt, abgetastet über die Umkehrabbildung; leer ohne Abbildung.
inline GrayImage alignFace(const GrayImage& src, const std::array<float, 10>& punkte) {
  Aehnlichkeit t;
  if (src.empty() || !schaetzeAehnlichkeit(punkte, kSollPunkte, t)) return {};
  const double s2 = t.a * t.a + t.b * t.b;
  GrayImage out(kAlignedFaceSize, kAlignedFaceSize);
  for (int y = 0; y < kAlignedFaceSize; ++y) {
    for (int x = 0; x < kAlignedFaceSize; ++x) {
      const double dx = x - t.tx, dy = y - t.ty;
      const double sx = (t.a * dx + t.b * dy) / s2;
      const double sy = (t.a * dy - t.b * dx) / s2;
      const float v = sampleBilinear(src, sx, sy);
      out.at(y, x) = static_cast<uint8_t>(std::lround(std::fmin(std::fmax(v, 0.0f), 255.0f)));
    }
  }
  return out;
}

}  // namespace winky
