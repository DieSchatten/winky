#!/usr/bin/env bash
# Startet das Kalibrierwerkzeug (Entwicklung, nicht Teil des Pakets).
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -x bau/winky-messung ]] || ./scripts/messwerkzeug-bauen.sh
exec python3 werkzeuge/kalibrierung/kalibrierung.py
