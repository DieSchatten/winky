// Entscheidungsregel für eine Entsperrprüfung, ohne Kamera und ohne Modelle
// (rein rechnerisch, damit sie sich mit erfundenen Daten testen lässt).
//
// Erfolg erst, wenn mindest_treffer beleuchtete Bilder mit brauchbarem Gesicht
// über der Schwelle liegen, im selben Gesichtsverlauf (Rahmen überlappen) und
// mit plausiblem Blinkmuster: Im vorherigen, unbeleuchteten Bild muss der
// Gesichtsbereich deutlich dunkler sein. Ein Bildschirm oder eine
// eingespielte Aufnahme ohne Strahler fällt damit heraus.
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
  float hell_gesicht = 0;    // Gesichtsbereich in diesem (beleuchteten) Bild
  float dunkel_gesicht = -1; // derselbe Bereich im vorherigen dunklen Bild, -1 = keins
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

// sudo bestätigen: Gesicht erkannt (Regel wie oben) und Handzeichen ✌ in mehreren
// beleuchteten Bildern hintereinander. Ein Bild zählt für das Zeichen nur, wenn genau ein
// Gesicht zu sehen ist, die Hand nah an diesem Gesicht ist und das Gesicht dasselbe ist,
// das erkannt wurde (Rahmen überlappen). So kann niemand neben einem zufällig in die
// Kamera schauenden Besitzer ein Zeichen zeigen.
struct HandBeobachtung {
  bool zeichen = false;  // ✌ sicher erkannt (Hand sicher, wahrscheinlichste Geste, >= 0,5)
  float x = 0, y = 0;    // Mitte der Hand im Bild
};

struct GestenRegeln {
  int bilder = 3;        // so viele Bilder in Folge mit Zeichen
  float naehe_x = 2.5f;  // Hand höchstens so viele Gesichtsbreiten seitlich vom Gesicht
  float naehe_y = 2.0f;  // und so viele Gesichtshöhen darüber oder darunter
};

class GestenEntscheidung {
 public:
  GestenEntscheidung(const Regeln& gesicht, const GestenRegeln& g) : gesicht_(gesicht), r_(g) {}

  // gesichter: Anzahl der Gesichter im Bild
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
