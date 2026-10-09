// Eingelernte Merkmalsvektoren eines Benutzers.
//
// Datei /var/lib/winky/<uid>/vorlagen.bin, geschrieben nur vom
// Verwaltungshelfer (root). Format:
//   0  "WNKV"            4 Byte
//   4  Version (1)       u32
//   8  Dimension         u32
//   12 Anzahl            u32
//   16 Modell-SHA-256    64 Zeichen hex
//   80 erstellt (Unix)   i64
//   88 Anzahl*Dimension float32, jeder Vektor auf Länge 1 normiert
//
// Jeder Pfadteil wird ohne Verknüpfungen geöffnet und muss root gehören und
// darf für Gruppe/andere nicht beschreibbar sein.
#pragma once

#include <sys/types.h>

#include <cstdint>
#include <string>
#include <vector>

namespace winky {

constexpr const char* kVorlagenBasis = "/var/lib/winky";
constexpr const char* kErkennungsModellSha =
    "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79";
constexpr uint32_t kVorlagenDim = 128;
constexpr uint32_t kVorlagenMax = 64;
constexpr size_t kVorlagenKopf = 88;

struct Vorlagen {
  uint32_t dim = 0;
  std::vector<float> daten;  // anzahl * dim
  int64_t erstellt = 0;
  size_t anzahl() const { return dim ? daten.size() / dim : 0; }
  const float* zeile(size_t i) const { return &daten[i * dim]; }
};

bool ladeVorlagen(const std::string& basis, uid_t uid, Vorlagen& v, std::string& fehler);

// Prüft einen Speicherblock im Vorlagenformat (für Laden und Tests).
bool pruefeVorlagen(const std::vector<uint8_t>& roh, Vorlagen& v, std::string& fehler);

// Mittel der drei besten Ähnlichkeiten (Skalarprodukt normierter Vektoren).
float bewerte(const std::vector<float>& merkmal, const Vorlagen& v);

}  // namespace winky
