// Entscheidungsregel ohne Kamera und Modelle (mit erfundenen Daten testbar). Treffer erst nach
// mindest_treffer beleuchteten Bildern über der Schwelle im selben Gesichtsverlauf, jedes mit
// deutlich dunklerem Gesicht im Dunkelbild davor (weist Bildschirme/Aufnahmen ohne Strahler ab).
#pragma once

namespace winky {

struct Rahmen {
  float x1 = 0, y1 = 0, x2 = 0, y2 = 0;
};

struct Beobachtung {
  double t_ms = 0;           // seit Beginn der Prüfung
  bool gesicht = false;      // irgendein Gesicht gefunden
  bool brauchbar = false;    // Qualitätsprüfung bestanden
  float wert = -1;           // Ähnlichkeit (nur wenn brauchbar)
  Rahmen rahmen;
  float hell_gesicht = 0;    // Gesichtshelligkeit in diesem hellen Bild
  float dunkel_gesicht = -1; // dieselbe im Dunkelbild davor, -1 = keins
};

struct Regeln {
  float schwelle = 0.6f;
  int mindest_treffer = 2;
  double ohne_gesicht_ms = 1200;
  double gesamt_ms = 2600;
  float blink_abstand = 15;
  bool blink_pruefung = true;
};

enum class Ergebnis { Offen, Treffer, KeinTreffer, KeinGesicht };

class Entscheidung {
 public:
  explicit Entscheidung(const Regeln& r) : r_(r) {}

  Ergebnis neu(const Beobachtung& b);
  Ergebnis zeit(double t_ms);  // ohne neues Bild: Fristen prüfen

  float besterWert() const { return bester_; }
  bool gesichtGesehen() const { return brauchbar_gesehen_; }
  int treffer() const { return treffer_; }

 private:
  Regeln r_;
  int treffer_ = 0;
  bool hat_letzten_ = false;
  Rahmen letzter_;
  float bester_ = -1;
  bool brauchbar_gesehen_ = false;
  bool gesicht_gesehen_ = false;
};

float ueberlappung(const Rahmen& a, const Rahmen& b);

// Gestenregel: erkanntes Gesicht plus ✌ in mehreren Bildern in Folge, jeweils bei genau einem
// Gesicht, Hand nahe daran und Gesicht = erkanntes (kein Fremdzeichen neben dem Besitzer).
struct HandBeobachtung {
  bool zeichen = false;  // ✌ sicher erkannt
  float x = 0, y = 0;    // Handmitte in Bildpixeln
};

struct GestenRegeln {
  int bilder = 3;        // Bilder in Folge mit Zeichen
  float naehe_x = 2.5f;  // max. seitlicher Abstand zur Gesichtsmitte in Gesichtsbreiten
  float naehe_y = 2.0f;  // max. senkrechter Abstand in Gesichtshöhen
};

class GestenEntscheidung {
 public:
  GestenEntscheidung(const Regeln& gesicht, const GestenRegeln& g) : gesicht_(gesicht), r_(g) {}

  Ergebnis neu(const Beobachtung& b, int gesichter, const HandBeobachtung& h);
  Ergebnis zeit(double t_ms);

  bool gesichtErkannt() const { return gesicht_ok_; }
  int zeichenFolge() const { return folge_; }
  float besterWert() const { return gesicht_.besterWert(); }
  bool gesichtGesehen() const { return gesicht_.gesichtGesehen(); }

 private:
  Entscheidung gesicht_;
  GestenRegeln r_;
  bool gesicht_ok_ = false;
  Rahmen erkannt_;  // letzter Rahmen des erkannten Gesichts
  int folge_ = 0;
};

}  // namespace winky
