#include "entscheidung.h"

#include <algorithm>
#include <cmath>

namespace winky {

float ueberlappung(const Rahmen& a, const Rahmen& b) {
  const float w = std::max(0.0f, std::min(a.x2, b.x2) - std::max(a.x1, b.x1));
  const float h = std::max(0.0f, std::min(a.y2, b.y2) - std::max(a.y1, b.y1));
  const float schnitt = w * h;
  const float fa = (a.x2 - a.x1) * (a.y2 - a.y1);
  const float fb = (b.x2 - b.x1) * (b.y2 - b.y1);
  const float vereinigung = fa + fb - schnitt;
  return vereinigung > 0 ? schnitt / vereinigung : 0.0f;
}

Ergebnis Entscheidung::neu(const Beobachtung& b) {
  if (b.gesicht) gesicht_gesehen_ = true;
  if (b.brauchbar) {
    brauchbar_gesehen_ = true;
    bester_ = std::max(bester_, b.wert);
    const bool blink_ok = !r_.blink_pruefung || (b.dunkel_gesicht >= 0 &&
                                                 b.hell_gesicht - b.dunkel_gesicht >= r_.blink_abstand);
    if (b.wert >= r_.schwelle && blink_ok) {
      if (hat_letzten_ && ueberlappung(letzter_, b.rahmen) >= 0.3f) {
        ++treffer_;
      } else {
        treffer_ = 1;  // neuer Gesichtsverlauf
      }
      letzter_ = b.rahmen;
      hat_letzten_ = true;
      if (treffer_ >= r_.mindest_treffer) return Ergebnis::Treffer;
    } else if (hat_letzten_ && ueberlappung(letzter_, b.rahmen) < 0.3f) {
      treffer_ = 0;  // anderes Gesicht im Bild: Verlauf beginnt neu
      hat_letzten_ = false;
    }
  }
  return zeit(b.t_ms);
}

Ergebnis Entscheidung::zeit(double t_ms) {
  if (!brauchbar_gesehen_ && t_ms >= r_.ohne_gesicht_ms) return Ergebnis::KeinGesicht;
  if (t_ms >= r_.gesamt_ms)
    return brauchbar_gesehen_ ? Ergebnis::KeinTreffer : Ergebnis::KeinGesicht;
  return Ergebnis::Offen;
}

Ergebnis GestenEntscheidung::neu(const Beobachtung& b, int gesichter, const HandBeobachtung& h) {
  const Ergebnis g = gesicht_.neu(b);
  if (g == Ergebnis::Treffer) {
    gesicht_ok_ = true;
    erkannt_ = b.rahmen;
  }
  bool zeichen = h.zeichen && gesichter == 1 && b.gesicht;
  if (zeichen) {
    const float fw = b.rahmen.x2 - b.rahmen.x1, fh = b.rahmen.y2 - b.rahmen.y1;
    const float fx = (b.rahmen.x1 + b.rahmen.x2) / 2, fy = (b.rahmen.y1 + b.rahmen.y2) / 2;
    zeichen = fw > 0 && fh > 0 && std::fabs(h.x - fx) <= r_.naehe_x * fw &&
              std::fabs(h.y - fy) <= r_.naehe_y * fh;
  }
  // Das Gesicht beim Zeichen muss das erkannte sein (sofern schon erkannt)
  if (zeichen && gesicht_ok_ && ueberlappung(erkannt_, b.rahmen) < 0.3f) zeichen = false;
  folge_ = zeichen ? folge_ + 1 : 0;
  if (gesicht_ok_ && b.gesicht && gesichter == 1 && ueberlappung(erkannt_, b.rahmen) >= 0.3f)
    erkannt_ = b.rahmen;  // Kopf darf sich bewegen
  if (gesicht_ok_ && folge_ >= r_.bilder) return Ergebnis::Treffer;
  return zeit(b.t_ms);
}

Ergebnis GestenEntscheidung::zeit(double t_ms) {
  const Ergebnis g = gesicht_.zeit(t_ms);
  if (g == Ergebnis::Offen) return Ergebnis::Offen;
  return gesicht_ok_ ? Ergebnis::KeinTreffer : g;  // Gesicht ja, aber kein Zeichen
}

}  // namespace winky
