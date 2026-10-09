#!/usr/bin/env bash
# Erzeugt die Bildschirmfotos für die Software-Verwaltung neu
# (packaging/bildschirmfotos/*.png). Braucht gtk4-broadwayd, läuft ohne Kamera und ohne root.
set -euo pipefail
cd "$(dirname "$0")/.."
WURZEL=$(mktemp -d)
gtk4-broadwayd :17 >/dev/null 2>&1 &
BROADWAY=$!
trap 'kill $BROADWAY 2>/dev/null; rm -rf "$WURZEL"' EXIT
sleep 1
# Standarddesign (libadwaita hell): Desktop-Einstellungen wie das Zorin-Design ausblenden
ADW_DISABLE_PORTAL=1 GDK_DEBUG=no-portals GSETTINGS_BACKEND=memory WINKY_ATTRAPPE=1 WINKY_TESTWURZEL="$WURZEL" GDK_BACKEND=broadway BROADWAY_DISPLAY=:17 \
  python3 werkzeuge/bildschirmfotos/aufnehmen.py
