#!/usr/bin/env bash
# Wandelt Googles MediaPipe Gesture Recognizer (Apache-2.0) von TFLite nach ONNX um:
# Handflächen, Handpunkte und Gesten aus gesture_recognizer.task. Quelle ist das offizielle
# Paket (Version 1, float16), per SHA-256 geprüft. Die Umwandlung läuft in einem
# Wegwerf-Container mit festen Werkzeugversionen und vergleicht danach die
# Ausgaben von TFLite und ONNX mit Zufallseingaben.
#
# Aufruf: scripts/mediapipe-umwandeln.sh ZIELORDNER
set -euo pipefail
ZIEL=$(realpath "${1:?Zielordner fehlt}")
GESTEN_URL=https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task
GESTEN_SHA=97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482
ARBEIT=$(mktemp -d)
trap 'rm -rf "$ARBEIT"' EXIT

curl -fsSL --proto '=https' --tlsv1.2 --retry 3 -o "$ARBEIT/gesture_recognizer.task" "$GESTEN_URL"
echo "$GESTEN_SHA  $ARBEIT/gesture_recognizer.task" | sha256sum -c --status - ||
  { echo "FEHLER: gesture_recognizer.task hat eine falsche Prüfsumme" >&2; exit 1; }
python3 - "$ARBEIT" <<'ENTPACKEN'
import io, sys, zipfile
ziel = sys.argv[1]
aussen = zipfile.ZipFile(f"{ziel}/gesture_recognizer.task")
for innen in ("hand_landmarker.task", "hand_gesture_recognizer.task"):
    zipfile.ZipFile(io.BytesIO(aussen.read(innen))).extractall(ziel)
ENTPACKEN

cat > "$ARBEIT/umwandeln.py" <<'PY'
import subprocess, sys
import numpy as np
import tensorflow as tf
import onnxruntime as ort

for name in ("hand_detector",
             "hand_landmarks_detector", "gesture_embedder", "canned_gesture_classifier"):
    subprocess.run([sys.executable, "-m", "tf2onnx.convert", "--tflite", f"/m/{name}.tflite",
                    "--output", f"/m/{name}.onnx", "--opset", "17"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    it = tf.lite.Interpreter(model_path=f"/m/{name}.tflite")
    it.allocate_tensors()
    ein, aus = it.get_input_details(), it.get_output_details()
    s = ort.InferenceSession(f"/m/{name}.onnx", providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(1)
    abw = 0.0
    for _ in range(5):
        feeds = {}
        for e in ein:
            x = rng.random(e["shape"], dtype=np.float32)
            it.set_tensor(e["index"], x)
            oi = next(o for o in s.get_inputs() if o.name.split(":")[0] == e["name"].split(":")[0])
            feeds[oi.name] = x
        it.invoke()
        ref = [it.get_tensor(a["index"]) for a in aus]
        for r in s.run(None, feeds):
            abw = max(abw, min(float(np.max(np.abs(v - r))) for v in ref if v.shape == r.shape))
    print(f"{name}: größte Abweichung TFLite/ONNX {abw:.2e}")
    if abw > 1e-2:
        sys.exit(f"{name}: Umwandlung weicht zu stark ab")
PY

podman run --rm -v "$ARBEIT":/m:Z docker.io/library/python:3.11-slim bash -c '
  pip install -q --no-cache-dir --disable-pip-version-check tensorflow-cpu==2.15.1 tf2onnx==1.16.1 \
    onnx==1.15.0 onnxruntime==1.17.3 "numpy<2" >/dev/null 2>&1
  python3 /m/umwandeln.py 2>&1 | grep -E "Abweichung|weicht"'
for m in hand_detector hand_landmarks_detector \
         gesture_embedder canned_gesture_classifier; do
  install -m0644 "$ARBEIT/$m.onnx" "$ZIEL/"
  sha256sum "$ZIEL/$m.onnx"
done
