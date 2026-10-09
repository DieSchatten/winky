// Graustufenbild der IR-Kamera und Umwandlung in Netzeingaben (ein Kanal -> drei gleiche).
#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace winky {

struct GrayImage {
  int width = 0;
  int height = 0;
  std::vector<uint8_t> data;  // width * height, zeilenweise

  GrayImage() = default;
  GrayImage(int w, int h)
      : width(w > 0 ? w : 0), height(h > 0 ? h : 0),
        data(static_cast<size_t>(width) * static_cast<size_t>(height), 0) {}

  bool empty() const { return data.empty(); }
  uint8_t at(int y, int x) const { return data[static_cast<size_t>(y) * width + x]; }
  uint8_t& at(int y, int x) { return data[static_cast<size_t>(y) * width + x]; }
};

// Mittlere Helligkeit (jedes zweite Pixel jeder zweiten Zeile reicht).
inline float meanBrightness(const GrayImage& img) {
  if (img.empty()) return 0.0f;
  uint64_t summe = 0;
  uint64_t n = 0;
  for (int y = 0; y < img.height; y += 2) {
    const uint8_t* zeile = &img.data[static_cast<size_t>(y) * img.width];
    for (int x = 0; x < img.width; x += 2) {
      summe += zeile[x];
      ++n;
    }
  }
  return n ? static_cast<float>(summe) / static_cast<float>(n) : 0.0f;
}

// Bilineare Abtastung; außerhalb des Bildes zählt Schwarz.
inline float sampleBilinear(const GrayImage& img, double sx, double sy) {
  const double fx0 = std::floor(sx), fy0 = std::floor(sy);
  const int x0 = static_cast<int>(fx0), y0 = static_cast<int>(fy0);
  const double ax = sx - fx0, ay = sy - fy0;
  auto px = [&](int x, int y) -> double {
    return (x < 0 || y < 0 || x >= img.width || y >= img.height) ? 0.0 : img.at(y, x);
  };
  const double oben = px(x0, y0) * (1.0 - ax) + px(x0 + 1, y0) * ax;
  const double unten = px(x0, y0 + 1) * (1.0 - ax) + px(x0 + 1, y0 + 1) * ax;
  return static_cast<float>(oben * (1.0 - ay) + unten * ay);
}

// Lage des Bildes in der Netzeingabe: um `faktor` verkleinert, oben links, Rest schwarz.
struct Einpassung {
  float faktor = 1.0f;  // Netzpixel je Bildpixel
};

// Drei gleiche Kanäle (CHW, 0..255) in seite x seite; nur größere Bilder werden verkleinert.
inline Einpassung einpassen(const GrayImage& src, int seite, std::vector<float>& out) {
  Einpassung e;
  const size_t ebene = static_cast<size_t>(seite) * static_cast<size_t>(seite);
  out.assign(ebene * 3, 0.0f);
  if (src.empty() || seite <= 0) return e;
  e.faktor = std::min(1.0f, std::min(static_cast<float>(seite) / src.width,
                                     static_cast<float>(seite) / src.height));
  const int b = std::min(seite, static_cast<int>(std::floor(src.width * e.faktor)));
  const int h = std::min(seite, static_cast<int>(std::floor(src.height * e.faktor)));
  for (int y = 0; y < h; ++y) {
    float* ziel = &out[static_cast<size_t>(y) * seite];
    if (e.faktor == 1.0f) {
      const uint8_t* zeile = &src.data[static_cast<size_t>(y) * src.width];
      for (int x = 0; x < b; ++x) ziel[x] = zeile[x];
    } else {
      const double sy = (y + 0.5) / e.faktor - 0.5;
      for (int x = 0; x < b; ++x) {
        ziel[x] = sampleBilinear(src, (x + 0.5) / e.faktor - 0.5, sy);
      }
    }
  }
  std::copy_n(out.begin(), ebene, out.begin() + static_cast<std::ptrdiff_t>(ebene));
  std::copy_n(out.begin(), ebene, out.begin() + static_cast<std::ptrdiff_t>(2 * ebene));
  return e;
}

}  // namespace winky
