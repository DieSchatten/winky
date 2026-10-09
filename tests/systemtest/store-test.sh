#!/bin/bash
# Software-Verwaltungs-Weg im Wegwerf-System: PackageKit installiert, aktualisiert, deinstalliert
# Aufruf (--privileged nur, damit polkitd im rootless Container seine Sandbox aufbauen kann):
#   podman build -t localhost/winky-systemtest:4 tests/systemtest
#   podman run -d --name winky-store --systemd=always --privileged --network=none localhost/winky-systemtest:4
#   podman cp bau/winky_<version>_amd64.deb winky-store:/root/neu.deb
#   podman cp tests/systemtest/store-test.sh winky-store:/root/; podman exec winky-store /root/store-test.sh
# Dateien nach /root, nicht /tmp: systemd legt im Container ein frisches /tmp darüber.
# Die „ältere Version“ für den Aktualisierungstest baut das Skript selbst aus neu.deb.
F=0
pruefe() { if eval "$1"; then echo "ok      $2"; else echo "FEHLER  $2"; F=$((F+1)); fi; }
pk() { pkcon -y --allow-untrusted "$@" >/tmp/pk.log 2>&1; if grep -qiE "failed|fatal|error" /tmp/pk.log; then echo "pkcon $*:"; tail -5 /tmp/pk.log; fi; }
until systemctl is-system-running 2>/dev/null | grep -qE 'running|degraded'; do sleep 0.5; done

# Ausgangslage wie auf einem eingerichteten Rechner (ältere Version, aktiv, Gesicht eingelernt)
rm -rf /root/alt && dpkg-deb -R /root/neu.deb /root/alt
sed -i 's/^Version: .*/Version: 0.0.1/' /root/alt/DEBIAN/control
# Ältere Fassungen hatten winky.conf als dpkg-Konfigurationsdatei mit anderer Vorgabe
install -Dm0644 /root/alt/usr/share/winky/winky.conf /root/alt/etc/winky/winky.conf
sed -i '1i # Vorgabe einer älteren Version' /root/alt/etc/winky/winky.conf
echo /etc/winky/winky.conf > /root/alt/DEBIAN/conffiles
dpkg-deb --root-owner-group -b /root/alt /root/alt.deb >/dev/null
dpkg -i /root/alt.deb >/dev/null 2>&1
pam-auth-update --package --enable winky
install -d -m0750 -g _winky /var/lib/winky/1000 && echo WNKVx > /var/lib/winky/1000/vorlagen.bin
echo '{"vorlagen": 30}' > /var/lib/winky/status/1000.json
# Zweite Person mit Gesichtsdaten eines älteren Modells (ohne Kennung WNKV)
install -d -m0750 -g _winky /var/lib/winky/1001 && echo BPZVx > /var/lib/winky/1001/vorlagen.bin
touch /var/lib/winky/1001/geste-ok; echo '{"vorlagen": 30}' > /var/lib/winky/status/1001.json
echo sicherung > /var/lib/winky/sicherung/common-auth.test
cp /usr/share/winky/polkit/50-winky-keepassxc.rules /etc/polkit-1/rules.d/
systemctl enable --now winky-polkit.socket >/dev/null 2>&1
echo "schwelle = 0.70" >> /etc/winky/winky.conf
pruefe 'grep -q pam_winky /etc/pam.d/common-auth' "Ausgang: Gesicht am Sperrbildschirm aktiv"

# 1. Aktualisieren über PackageKit (wie Doppelklick auf die .deb)
pk install-local /root/neu.deb
pruefe '[ "$(dpkg-query -W -f="\${Version}" winky)" = "$(dpkg-deb -f /root/neu.deb Version)" ]' "Aktualisierung über PackageKit"
pruefe '[ -f /var/lib/winky/1000/vorlagen.bin ] && [ -f /var/lib/winky/status/1000.json ]' "Aktualisieren behält die Gesichtsdaten"
pruefe '[ ! -e /var/lib/winky/1001/vorlagen.bin ] && [ ! -e /var/lib/winky/1001/geste-ok ] && [ ! -e /var/lib/winky/status/1001.json ]' "Gesichtsdaten im alten Format werden gelöscht"
pruefe 'grep -q pam_winky /etc/pam.d/common-auth' "Aktualisieren lässt die Anmeldung eingeschaltet"
pruefe 'grep -q "schwelle = 0.70" /etc/winky/winky.conf' "Aktualisieren behält die Einstellungen"
pruefe '! dpkg-deb -I /root/neu.deb conffiles >/dev/null 2>&1 && [ ! -e /etc/winky/winky.conf.dpkg-new ] && [ ! -e /etc/winky/winky.conf.dpkg-old ]' "Einstellungen ohne dpkg-Rückfrage (keine Konfigurationsdatei mehr)"
pruefe 'systemctl is-active -q winky.socket' "Prüfdienst-Socket nach dem Aktualisieren aktiv"

# 2. Store-Anzeige: Beschreibung vorhanden, Paket über die Desktop-Datei auffindbar
appstreamcli refresh-cache --force >/dev/null 2>&1
pruefe 'appstreamcli get io.github.dieschatten.Winky 2>/dev/null | grep -q "Name: Winky"' "AppStream kennt die App"
pruefe 'appstreamcli dump io.github.dieschatten.Winky 2>/dev/null | grep -q "<description>"' "mit Beschreibung (Bedingung für „Installiert“)"
pruefe '[ -f /usr/share/icons/hicolor/scalable/apps/io.github.dieschatten.Winky.svg ]' "Icon installiert"
pruefe '[ "$(appstreamcli dump io.github.dieschatten.Winky | grep -c "https://raw.githubusercontent.com/DieSchatten/winky/main/packaging/bildschirmfotos/")" -ge 3 ]' "drei Bildschirmfotos (GitHub)"
pruefe 'appstreamcli dump io.github.dieschatten.Winky | grep -q "<keyword>Windows Hello</keyword>"' "Suchbegriff Windows Hello"
pruefe 'dpkg -L winky | grep -q /usr/share/locale/de/LC_MESSAGES/winky.mo' "deutsche Übersetzung im Paket (Container-Abbilder lassen locale weg)"
pkcon search file /usr/share/applications/io.github.dieschatten.Winky.desktop > /tmp/suche.log 2>&1
pruefe 'grep -q "winky-$(dpkg-deb -f /root/neu.deb Version)" /tmp/suche.log' "PackageKit ordnet die App dem Paket zu (Deinstallieren-Knopf)"

# 3. Deinstallieren über PackageKit (wie in der Software-Verwaltung)
pk remove winky
pruefe '! dpkg-query -W -f="\${Status}" winky 2>/dev/null | grep -q "ok installed"' "Deinstalliert über PackageKit"
pruefe '! grep -q pam_winky /etc/pam.d/common-auth' "Anmeldung wieder nur Passwort"
pruefe 'grep -q pam_unix /etc/pam.d/common-auth' "pam_unix unverändert vorhanden"
pruefe '[ ! -e /etc/polkit-1/rules.d/50-winky-keepassxc.rules ]' "KeePassXC-Regel entfernt"
pruefe '! systemctl is-active -q winky.socket && ! systemctl is-active -q winky-polkit.socket' "beide Sockets gestoppt"
pruefe '[ ! -e /var/lib/winky/1000 ] && [ ! -e /var/lib/winky/status ]' "Gesichtsdaten gelöscht"
pruefe '[ -f /var/lib/winky/sicherung/common-auth.test ]' "PAM-Sicherung bleibt"
pruefe '[ -f /etc/winky/winky.conf ]' "Einstellungsdatei bleibt (wie bei jedem Paket)"
pruefe '[ ! -e /usr/lib/x86_64-linux-gnu/security/pam_winky.so ]' "PAM-Modul entfernt"

# 4. purge räumt den Rest weg
dpkg --purge winky >/dev/null 2>&1
pruefe '[ ! -e /var/lib/winky ] && [ ! -e /etc/winky ]' "purge entfernt Rest und Einstellungen"

# 5. Neuinstallation über PackageKit auf frischem Stand
pk install-local /root/neu.deb
pruefe 'systemctl is-active -q winky.socket' "Neuinstallation: Socket aktiv"
pruefe '! grep -q pam_winky /etc/pam.d/common-auth' "Neuinstallation: nichts aktiv"
pruefe 'id _winky >/dev/null 2>&1' "Systembenutzer angelegt"
pruefe 'cmp -s /etc/winky/winky.conf /usr/share/winky/winky.conf' "Neuinstallation legt die Einstellungsdatei an"
echo; echo "$F Fehler"
