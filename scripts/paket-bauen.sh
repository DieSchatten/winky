#!/usr/bin/env bash
# Baut bau/winky_<version>_amd64.deb im Container ohne Netz: Abhängigkeiten prüfen, bauen,
# Tests (brechen bei Fehlern ab), paketieren.
set -euo pipefail
cd "$(dirname "$0")/.."

./scripts/abhaengigkeiten.sh >/dev/null
VERSION=$(sed -n 's/^project(winky VERSION \([0-9.]*\).*/\1/p' CMakeLists.txt)
COMMIT=$(git rev-parse --short HEAD)$(git diff --quiet HEAD -- . ':!messungen' || echo "+")
GEBAUT=$(date '+%Y-%m-%d %H:%M')

# Metainfo prüfen (Bildschirmfotos liegen im Repo und werden über GitHub geladen)
if command -v appstreamcli >/dev/null; then
  PRUEF=$(mktemp -d)
  sed "s/@VERSION@/$VERSION/;s/@DATUM@/${GEBAUT%% *}/;s|@HERAUSGEBER_NAME@|Winky|" \
    packaging/io.github.dieschatten.Winky.metainfo.xml > "$PRUEF"/io.github.dieschatten.Winky.metainfo.xml
  appstreamcli validate --no-net "$PRUEF"/io.github.dieschatten.Winky.metainfo.xml | tail -1
  rm -rf "$PRUEF"
fi

podman run --rm --network=none -v "$PWD":/src:Z -w /src \
  -e VERSION="$VERSION" -e COMMIT="$COMMIT" -e GEBAUT="$GEBAUT" \
  localhost/winky-bau:2 bash -euo pipefail -c '
    cmake -S . -B bau -G Ninja -DCMAKE_BUILD_TYPE=Release >/dev/null
    cmake --build bau | tail -1
    echo "== Komponententests: $(bau/test_dienst | tail -1)"
    echo "== PAM-Tests: $(python3 tests/pam_test.py bau/pam_winky.so | tail -1)"
    python3 -c "import ast,sys; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]" \
      src/verwalten/winky-verwalten src/hinweis/winky-hinweis src/schluessel/winky-schluessel src/app/*.py
    ./scripts/uebersetzungen.sh
    ./scripts/paket-zusammenstellen.sh
  '
ls -la bau/*.deb
