#!/usr/bin/env bash
# Startet die App mit Attrappe in GTK-Broadway (Browser: http://localhost:8087), ohne Kamera und Desktop.
# Aufruf: gui-broadway.sh TESTWURZEL
set -euo pipefail
cd "$(dirname "$0")/../.."
gtk4-broadwayd :7 &
BW=$!
trap 'kill $BW 2>/dev/null' EXIT
sleep 1
GDK_BACKEND=broadway BROADWAY_DISPLAY=:7 WINKY_ATTRAPPE=1 WINKY_TESTWURZEL="$1" \
  python3 src/app/gesicht_app.py
