#!/usr/bin/env bash
# Stellt im Bau-Container den Paketbaum zusammen und baut das .deb.
# Erwartet VERSION, COMMIT, GEBAUT in der Umgebung.
set -euo pipefail
cd "$(dirname "$0")/.."
P=bau/paket
# Herausgeber aus AUTHORS, für control und Software-Verwaltung
HERAUSGEBER=$(grep -v '^#' AUTHORS | grep -m1 .)
HERAUSGEBER_NAME=${HERAUSGEBER% <*}
rm -rf "$P" bau/*.deb
mkdir -p "$P"

DESTDIR="$PWD/$P" cmake --install bau --prefix /usr >/dev/null
strip --strip-unneeded "$P"/usr/libexec/winky/winky-matcher \
  "$P"/usr/libexec/winky/winky-polkit-pruefung \
  "$P"/usr/lib/x86_64-linux-gnu/security/pam_winky.so
chmod 0644 "$P"/usr/lib/x86_64-linux-gnu/security/pam_winky.so

# Derselbe Helfer in zwei Rollen: eigenes Gesicht (eigenes Passwort) und System (Administrator)
install -Dm0755 src/verwalten/winky-verwalten "$P"/usr/libexec/winky/winky-verwalten
install -Dm0755 src/verwalten/winky-verwalten "$P"/usr/libexec/winky/winky-gesicht
# Desktop-Hinweis zu sudo-Anfragen, startet in jeder Sitzung
install -Dm0755 src/hinweis/winky-hinweis "$P"/usr/libexec/winky/winky-hinweis
install -Dm0644 packaging/winky-hinweis.desktop "$P"/etc/xdg/autostart/io.github.dieschatten.Winky.Hinweis.desktop
install -Dm0644 vendor/onnxruntime/lib/libonnxruntime.so.1.30.0 "$P"/usr/lib/winky/libonnxruntime.so.1
# Gesichtssuche, Erkennung und Handzeichen (MediaPipe Gesture Recognizer, für sudo mit ✌)
for m in face_detection_yunet_2023mar.onnx face_recognition_sface_2021dec.onnx hand_detector.onnx hand_landmarks_detector.onnx \
         gesture_embedder.onnx canned_gesture_classifier.onnx; do
  install -Dm0644 "vendor/$m" "$P/usr/share/winky/models/$m"
done
for f in src/app/*.py; do install -Dm0644 "$f" "$P/usr/share/winky/app/$(basename "$f")"; done
chmod 0755 "$P"/usr/share/winky/app/gesicht_app.py
install -Dm0755 packaging/winky "$P"/usr/bin/winky
install -Dm0644 packaging/io.github.dieschatten.Winky.desktop "$P"/usr/share/applications/io.github.dieschatten.Winky.desktop
install -Dm0644 packaging/icons/io.github.dieschatten.Winky.svg \
  "$P"/usr/share/icons/hicolor/scalable/apps/io.github.dieschatten.Winky.svg
for f in packaging/bildschirmfotos/*.png; do
  install -Dm0644 "$f" "$P/usr/share/winky/bildschirmfotos/$(basename "$f")"
done
# Beschreibung für die Software-Verwaltung (Anzeige unter „Installiert“, Deinstallieren)
mkdir -p "$P"/usr/share/metainfo
sed "s/@VERSION@/$VERSION/;s/@DATUM@/${GEBAUT%% *}/;s|@HERAUSGEBER_NAME@|$HERAUSGEBER_NAME|" packaging/io.github.dieschatten.Winky.metainfo.xml \
  > "$P"/usr/share/metainfo/io.github.dieschatten.Winky.metainfo.xml
# Jedes Bildschirmfoto aus der Beschreibung muss im Paket liegen
for bild in $(sed -n 's|.*file://\([^<]*\)<.*|\1|p' "$P"/usr/share/metainfo/io.github.dieschatten.Winky.metainfo.xml); do
  [[ -f "$P$bild" ]] || { echo "Bildschirmfoto fehlt im Paket: $bild" >&2; exit 1; }
done
install -Dm0644 packaging/systemd/winky.socket "$P"/usr/lib/systemd/system/winky.socket
install -Dm0644 packaging/systemd/winky@.service "$P"/usr/lib/systemd/system/winky@.service
install -Dm0644 packaging/systemd/winky-polkit.socket "$P"/usr/lib/systemd/system/winky-polkit.socket
install -Dm0644 packaging/systemd/winky-polkit@.service "$P"/usr/lib/systemd/system/winky-polkit@.service
install -Dm0644 packaging/polkit/50-winky-keepassxc.rules "$P"/usr/share/winky/polkit/50-winky-keepassxc.rules
install -Dm0644 packaging/sysusers.conf "$P"/usr/lib/sysusers.d/winky.conf
install -Dm0644 packaging/tmpfiles.conf "$P"/usr/lib/tmpfiles.d/winky.conf
install -Dm0644 packaging/pam-config "$P"/usr/share/pam-configs/winky
install -Dm0644 packaging/polkit/io.github.dieschatten.winky.policy "$P"/usr/share/polkit-1/actions/io.github.dieschatten.winky.policy
# Vorgabe der Einstellungen; postinst legt /etc/winky/winky.conf nur an, wenn sie fehlt
install -Dm0644 packaging/winky.conf "$P"/usr/share/winky/winky.conf
install -Dm0644 README.md "$P"/usr/share/doc/winky/README.md
install -Dm0644 NOTICE "$P"/usr/share/doc/winky/copyright
install -Dm0644 LICENSE "$P"/usr/share/doc/winky/LICENSE
install -Dm0644 vendor/onnxruntime/ThirdPartyNotices.txt "$P"/usr/share/doc/winky/onnxruntime-ThirdPartyNotices.txt
printf '{"version": "%s", "commit": "%s", "gebaut": "%s"}\n' "$VERSION" "$COMMIT" "$GEBAUT" \
  > "$P"/usr/share/winky/version.json

mkdir -p "$P"/DEBIAN
sed "s/@VERSION@/$VERSION/;s|@HERAUSGEBER@|$HERAUSGEBER|" packaging/debian/control > "$P"/DEBIAN/control
echo "Installed-Size: $(du -sk --exclude=DEBIAN "$P" | cut -f1)" >> "$P"/DEBIAN/control
install -m0755 packaging/debian/postinst packaging/debian/prerm packaging/debian/postrm "$P"/DEBIAN/
( cd "$P" && find . -type f ! -path './DEBIAN/*' -printf '%P\0' | sort -z | xargs -0 md5sum ) \
  > "$P"/DEBIAN/md5sums

# Keine fremden Bibliothekspfade und kein ldconfig
readelf -d "$P"/usr/libexec/winky/winky-matcher | grep -q 'RUNPATH.*\[/usr/lib/winky\]'
dpkg-deb --root-owner-group -Zxz --build "$P" "bau/winky_${VERSION}_amd64.deb" >/dev/null
echo "== Paket: bau/winky_${VERSION}_amd64.deb ($COMMIT)"
