// Hand und Handzeichen über MediaPipe Gesture Recognizer (Google, Apache-2.0), nach ONNX
// umgewandelt. Ablauf wie in MediaPipe (hand_detector_graph, hand_landmarks_detector_graph,
// hand_gesture_recognizer_graph):
//   1. Handfläche suchen (192 x 192, Ankerraster wie SsdAnchorsCalculator)
//   2. gedrehter Ausschnitt um die Handfläche (2,6-fach, um eine halbe Höhe zu den Fingern
//      verschoben), 224 x 224 -> 21 Handpunkte, Händigkeit, Handwahrscheinlichkeit
//   3. Gesten-Merkmal aus den Punkten (am Handgelenk ausgerichtet und auf Größe 1
//      normiert) und Klassifikator mit 8 Klassen, darunter Thumb_Up.
// Wie die MediaPipe-Bibliothek selbst wird das Bild nicht gespiegelt (abgeglichen mit
// MediaPipe 0.10.14 an Googles Testbildern). Die Handflächensuche liefert ihren besten
// Wert immer; Handpunkte und Geste gibt es ab min_palm (MediaPipe: 0,5).
// Video wie MediaPipe im Videomodus: Ist eine Hand sicher erkannt (presence >= 0,5),
// kommt der nächste Ausschnitt aus ihren Punkten (Handgelenk, Daumen, Fingeransätze;
// 2,0-fach, leicht zu den Fingern verschoben) statt aus einer neuen Handflächensuche.
#pragma once

#include <array>
#include <memory>
#include <string>
#include <vector>

#include "image.h"
#include "onnx_session.h"

namespace winky {

constexpr int kHandPoints = 21;

enum HandGesture { kGestureNone, kClosedFist, kOpenPalm, kPointingUp, kThumbDown, kThumbUp,
                   kVictory, kILoveYou, kGestureCount };

struct HandResult {
  bool found = false;                        // Hand gefunden und Punkte berechnet
  bool tracked = false;                      // Ausschnitt aus dem vorigen Bild
  float palm_score = 0;                      // bester Wert der Handflächensuche (auch darunter)
  float presence = 0;                        // Hand im Ausschnitt laut Punktenetz
  float right_hand = 0;                      // Wahrscheinlichkeit rechte Hand
  std::array<float, kHandPoints * 2> pts{};  // x, y im Originalbild
  std::array<float, kGestureCount> gesture{};  // Klassenwahrscheinlichkeiten
  double palm_ms = 0, landmarks_ms = 0, gesture_ms = 0;
};

class HandGestureRecognizer {
 public:
  // Ordner mit hand_detector.onnx, hand_landmarks_detector.onnx, gesture_embedder.onnx,
  // canned_gesture_classifier.onnx
  HandGestureRecognizer(Ort::Env& env, const std::string& models_dir, int threads,
                        float min_palm = 0.5f);

  // verfolgen = false: jedes Bild für sich (Einzelbilder, Abgleich mit MediaPipe)
  HandResult analyse(const GrayImage& img, bool verfolgen = true);
  void vergessen() { spur_ = false; }

 private:
  struct Anchor {
    float x, y;
  };
  OnnxModel palm_, landmarks_, embedder_, classifier_;
  std::vector<Anchor> anchors_;
  bool handflaeche(const GrayImage& img, HandResult& r, double& mx, double& my, double& seite,
                   double& drehung);
  void punkteUndGeste(const GrayImage& img, HandResult& r, double mx, double my, double seite,
                      double drehung);

  std::vector<float> buffer_;
  float min_palm_;
  bool spur_ = false;
  double spur_x_ = 0, spur_y_ = 0, spur_seite_ = 0, spur_drehung_ = 0;
};

}  // namespace winky
