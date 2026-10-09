#!/usr/bin/env bash
# Baut das Messwerkzeug bau/winky-messung im Container ohne Netz.
set -euo pipefail
cd "$(dirname "$0")/.."

./scripts/abhaengigkeiten.sh >/dev/null

podman run --rm --network=none -v "$PWD":/src:Z -w /src localhost/winky-bau:1 \
  bash -c 'cmake -S . -B bau -G Ninja -DCMAKE_BUILD_TYPE=Release >/dev/null && cmake --build bau'

# ONNX Runtime neben das Programm legen (RUNPATH $ORIGIN)
cp -L vendor/onnxruntime/lib/libonnxruntime.so.1 bau/libonnxruntime.so.1
echo "Fertig: bau/winky-messung"
