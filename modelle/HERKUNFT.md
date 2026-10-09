# MediaPipe-Modelle für das Handzeichen ✌

Die geprüften ONNX-Dateien liegen hier im Repo, weil die Umwandlung nicht bitgenau
wiederholbar ist (tf2onnx schreibt wechselnde Namen); die Rechenergebnisse sind es.
`scripts/abhaengigkeiten.sh` kopiert sie nach `vendor/` und prüft dabei die Prüfsummen.

## Handzeichen

Googles MediaPipe Gesture Recognizer (Apache-2.0), ebenso umgewandelt mit
`scripts/mediapipe-umwandeln.sh`:

- Quelle: `gesture_recognizer.task` Version 1, float16, von
  `storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/`,
  SHA-256 `97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482`.
- Gegenprobe TFLite gegen ONNX: höchstens 1,9·10⁻⁴ Abweichung.
- Abgleich der ganzen Kette (`src/core/hand_gesture.cc`) mit MediaPipe 0.10.14 an Googles
  Testbild `pointing_up.jpg` in Graustufen: Geste Pointing_Up 0,86 (MediaPipe 0,84), Handgelenk
  auf 2 Pixel gleich. `thumb_up.jpg` und `victory.jpg` findet in Graustufen weder MediaPipe noch
  der Nachbau.
- Klassen des Klassifikators (aus den Metadaten): None, Closed_Fist, Open_Palm, Pointing_Up,
  Thumb_Down, Thumb_Up, Victory, ILoveYou.

| Datei | Inhalt | SHA-256 |
|---|---|---|
| `hand_detector.onnx` | Handflächen, 192 × 192, 2016 Anker | `c2f2712a853c66c4676034bb908db2182aa39047662a62260d2633daf61ddcda` |
| `hand_landmarks_detector.onnx` | 21 Handpunkte, Händigkeit, 224 × 224 | `0b2553f58f580d12a2f28abef6ac4f70a9cb1318d0e0fdba62c40ceb99a800e7` |
| `gesture_embedder.onnx` | 128 Merkmale aus Handpunkten | `ee17ca08a56d583de19752be6047acbf31844e3087273a4c9214caa78c9a662e` |
| `canned_gesture_classifier.onnx` | 8 Gestenklassen | `8b550b99f1d35adc82993c82def3d010600ffdf27b9244fe6af7d37dcf0d7031` |
