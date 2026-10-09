#!/usr/bin/env bash
# Lädt die Fremd-Abhängigkeiten nach vendor/ und prüft jede per SHA-256 und Größe (bei
# Abweichung: Datei löschen, Abbruch). ONNX Runtime: Prüfsumme aus der GitHub-Release-API;
# YuNet (MIT) und SFace (Apache-2.0) aus dem OpenCV Zoo (github.com/opencv/opencv_zoo).
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p vendor

ORT_VERSION="1.30.0"

# name|url|sha256|groesse
DATEIEN=(
  "onnxruntime-linux-x64-${ORT_VERSION}.tgz|https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-x64-${ORT_VERSION}.tgz|a5ed5a3cac51fbb2e90da632ae43d19212faaa20e76484e62bcb7c23ddb3b3fd|11306877"
  "face_detection_yunet_2023mar.onnx|https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx|8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4|232589"
  "face_recognition_sface_2021dec.onnx|https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx|0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79|38696353"
)

for eintrag in "${DATEIEN[@]}"; do
  IFS='|' read -r name url soll groesse <<<"$eintrag"
  ziel="vendor/$name"
  if [[ ! -f "$ziel" ]]; then
    echo "Lade $name ..."
    curl -fsSL --proto '=https' --tlsv1.2 --retry 3 -o "$ziel.teil" "$url"
    mv "$ziel.teil" "$ziel"
  fi
  ist_groesse=$(stat -c %s "$ziel")
  ist=$(sha256sum "$ziel" | cut -d' ' -f1)
  if [[ "$ist" != "$soll" || "$ist_groesse" != "$groesse" ]]; then
    echo "FEHLER: $name hat Prüfsumme $ist / Größe $ist_groesse, erwartet $soll / $groesse" >&2
    rm -f "$ziel"
    exit 1
  fi
  echo "ok  $name"
done

# MediaPipe-Handmodelle (Apache-2.0) liegen im Repo; Herkunft in modelle/HERKUNFT.md
for eintrag in \
  "hand_detector.onnx|c2f2712a853c66c4676034bb908db2182aa39047662a62260d2633daf61ddcda" \
  "hand_landmarks_detector.onnx|0b2553f58f580d12a2f28abef6ac4f70a9cb1318d0e0fdba62c40ceb99a800e7" \
  "gesture_embedder.onnx|ee17ca08a56d583de19752be6047acbf31844e3087273a4c9214caa78c9a662e" \
  "canned_gesture_classifier.onnx|8b550b99f1d35adc82993c82def3d010600ffdf27b9244fe6af7d37dcf0d7031"; do
  IFS='|' read -r name soll <<<"$eintrag"
  ist=$(sha256sum "modelle/$name" | cut -d' ' -f1)
  if [[ "$ist" != "$soll" ]]; then
    echo "FEHLER: modelle/$name hat Prüfsumme $ist, erwartet $soll" >&2
    exit 1
  fi
  install -m0644 "modelle/$name" "vendor/$name"
  echo "ok  $name"
done

if [[ ! -d "vendor/onnxruntime" ]]; then
  tmp=$(mktemp -d vendor/ort.XXXXXX)
  tar -xzf "vendor/onnxruntime-linux-x64-${ORT_VERSION}.tgz" -C "$tmp"
  mv "$tmp/onnxruntime-linux-x64-${ORT_VERSION}" vendor/onnxruntime
  rmdir "$tmp"
fi
echo "ONNX Runtime: $(ls vendor/onnxruntime/lib/ | tr '\n' ' ')"
