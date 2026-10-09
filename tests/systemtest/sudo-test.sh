#!/bin/bash
# sudo mit Gesicht und ✌ im Wegwerf-System: echter Prüfdienst, echte Kamera, echtes libpam.
# Ein Handzeichen wird nicht gezeigt; geprüft werden Vorbedingungen, Hinweisdatei,
# Begrenzung, gleichzeitige Anfragen, Zurücksetzen und Rückbau.
# Aufruf (Kamera durchreichen, Test-Drop-in: _winky darf die Kamera im rootless Container
# nicht öffnen):
#   podman run -d --name winky-sudo --systemd=always --privileged --network=none <systemtest-abbild>
#   podman cp bau/winky_<version>_amd64.deb winky-sudo:/root/winky.deb
#   podman cp tests/systemtest/sudo-test.sh winky-sudo:/root/; podman exec -t winky-sudo /root/sudo-test.sh
F=0
pruefe() { if eval "$1"; then echo "ok      $2"; else echo "FEHLER  $2"; F=$((F+1)); fi; }
until systemctl is-system-running 2>/dev/null | grep -qE 'running|degraded'; do sleep 0.5; done
V=/usr/libexec/winky/winky-verwalten
G=/usr/libexec/winky/winky-gesicht
erg() { tr -c "[:print:]\n" "?" | grep -o "ERGEBNIS.*" | cut -c1-160; }
anfrage() { python3 -c "import json;print(json.load(open('/run/winky/anfrage/1000.json'))['stand'])" 2>/dev/null; }
journal_n() { journalctl -t winky -o cat --no-pager | grep -c "zweck=sudo"; }
sudo_pam() { pamtester -I tty=/dev/pts/0 "$@" 2>&1; }

dpkg -i /root/winky.deb >/dev/null 2>&1
pruefe '[ "$(stat -c %U:%a /run/winky/anfrage)" = "_winky:755" ]' "Ordner für Hinweise gehört dem Prüfdienst"
pruefe '[ -f /etc/xdg/autostart/io.github.dieschatten.Winky.Hinweis.desktop ] && [ -x /usr/libexec/winky/winky-hinweis ]' "Hinweisprogramm mit Autostart installiert"
pruefe '[ -f /usr/share/winky/models/hand_detector.onnx ]' "Handmodelle installiert"
pruefe 'grep -q "geste=sudo" /usr/share/pam-configs/winky' "PAM-Profil kennt den sudo-Weg"
mkdir -p /etc/systemd/system/winky@.service.d
printf "[Service]\nUser=root\nGroup=root\n" > /etc/systemd/system/winky@.service.d/test.conf
mkdir -p /etc/systemd/system/winky-polkit@.service.d
cp /etc/systemd/system/winky@.service.d/test.conf /etc/systemd/system/winky-polkit@.service.d/
# Als root ohne Capabilities darf der Dienst nur in root-eigene Ordner schreiben
systemctl daemon-reload; chown root:root /run/winky/sperre /run/winky/anfrage

# Einrichtung wie in der App, Vorlagen künstlich (passen zu keinem Gesicht)
SUDO_UID=1000 $V kamera auto </dev/null | erg
echo "sitzungspruefung = nein" >> /etc/winky/winky.conf
python3 - <<'PY'
import grp, math, os, random, struct, time
d = "/var/lib/winky/1000"; os.makedirs(d, exist_ok=True)
gid = grp.getgrnam("_winky").gr_gid; os.chown(d, 0, gid); os.chmod(d, 0o750)
sha = b"0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
werte = []
for _ in range(10):
    v = [random.gauss(0, 1) for _ in range(128)]; n = math.sqrt(sum(x * x for x in v))
    werte += [x / n for x in v]
b = b"WNKV" + struct.pack("III", 1, 128, 10) + sha + struct.pack("q", int(time.time())) + struct.pack(f"{len(werte)}f", *werte)
open(f"{d}/vorlagen.bin", "wb").write(b); os.chown(f"{d}/vorlagen.bin", 0, gid); os.chmod(f"{d}/vorlagen.bin", 0o640)
PY
mkdir -p /var/lib/winky/status
echo '{"vorlagen": 10, "eingelernt": 1, "test_ok": 2}' > /var/lib/winky/status/1000.json
printf "auth [success=done default=ignore] pam_winky.so services=gdm-password,sudo geste=sudo timeout_ms=3000 geste_timeout_ms=10000\nauth requisite pam_deny.so\n" > /etc/pam.d/sudo-nurgeste

pruefe 'SUDO_UID=1000 $V sudo an </dev/null | erg | grep -q "Gesichtsentsperrung"' "sudo an verlangt aktive Gesichtsentsperrung"
SUDO_UID=1000 $V aktivieren </dev/null >/dev/null
pruefe 'SUDO_UID=1000 $V sudo an </dev/null | erg | grep -q "Gesicht und"' "sudo an verlangt bestandenen ✌-Test"
install -m0640 -g _winky /dev/null /var/lib/winky/1000/geste-ok   # Test ersetzt hier den ✌-Test
pruefe 'SUDO_UID=1000 $V sudo an </dev/null | erg | grep -q "\"ok\": true"' "sudo an mit Administratorrechten"
pruefe '[ -f /etc/winky/sudo-ein ] && grep -q "^sudo = ja" /etc/winky/winky.conf' "Schalter und Konfiguration gesetzt"
pruefe 'grep -q "pam_winky.so services=gdm-password,sudo geste=sudo" /etc/pam.d/common-auth' "common-auth enthält den sudo-Weg"

# 1. Anfrage ohne Handzeichen: Aufforderung, dann nicht bestätigt, Hinweisdatei, Zähler
cp /etc/pam.d/sudo-nurgeste /etc/pam.d/sudo
t0=$(date +%s%N); AUS=$(sudo_pam sudo ubuntu authenticate); t=$(( ($(date +%s%N)-t0)/1000000 ))
pruefe 'echo "$AUS" | grep -q "Kamera zeigen" && echo "$AUS" | grep -q "nicht bestätigt"' "Aufforderung erscheint, ohne ✌ nicht bestätigt (${t} ms)"
pruefe '[ $t -lt 10500 ]' "innerhalb des Zeitlimits von 10 s"
pruefe '[ "$(anfrage)" = nicht_bestaetigt ]' "Hinweisdatei: nicht bestätigt"
pruefe 'grep -q pamtester /run/winky/anfrage/1000.json && grep -q "/dev/pts/0" /run/winky/anfrage/1000.json' "Hinweisdatei nennt Befehl und Terminal"
pruefe '[ "$(cut -d" " -f1 /run/winky/sperre/sudo-1000)" = 1 ]' "eine unbestätigte Anfrage gezählt"
pruefe 'journalctl -t winky -o cat --no-pager | grep "zweck=sudo" | tail -1 | grep -q "befehl=\"pamtester"' "Journal nennt zweck=sudo und den Befehl"

# 2. Gleichzeitige Anfragen brechen beide ab
# Hintergrundjobs bekommen sonst /dev/null als Eingabe, und pam_winky verlangt ein Terminal
( sudo_pam sudo ubuntu authenticate < /dev/tty > /root/erste.txt ) &
sleep 2
t0=$(date +%s%N); sudo_pam sudo ubuntu authenticate > /root/zweite.txt; t=$(( ($(date +%s%N)-t0)/1000000 ))
wait
pruefe '[ $t -lt 1500 ] && ! grep -q "Kamera zeigen" /root/zweite.txt' "zweite gleichzeitige Anfrage sofort abgelehnt (${t} ms)"
pruefe 'grep -q "nicht bestätigt" /root/erste.txt' "erste Anfrage wurde abgebrochen"
pruefe 'journalctl -t winky -o cat --no-pager | grep "zweck=sudo" | tail -2 | grep -c "grund=gleichzeitig" | grep -q 2' "beide mit Grund gleichzeitig im Journal"

# 3. Begrenzung: nach drei unbestätigten gilt nur das Passwort
pruefe '[ "$(cut -d" " -f1 /run/winky/sperre/sudo-1000)" -ge 3 ]' "drei unbestätigte Anfragen gezählt"
t0=$(date +%s%N); AUS=$(sudo_pam sudo ubuntu authenticate); t=$(( ($(date +%s%N)-t0)/1000000 ))
pruefe '! echo "$AUS" | grep -q "Kamera zeigen" && [ $t -lt 1500 ]' "vierte Anfrage: keine Kamera, sofort Passwort (${t} ms)"
pruefe '[ "$(anfrage)" = begrenzt ]' "Hinweisdatei meldet die Pause"

# 4. Passwortanmeldung setzt zurück (Stapel: Gesicht, sonst pam_permit als Passwort)
printf "auth [success=done default=ignore] pam_winky.so services=gdm-password,sudo geste=sudo timeout_ms=3000 geste_timeout_ms=10000\nauth required pam_permit.so\n" > /etc/pam.d/sudo
sudo_pam sudo ubuntu authenticate setcred >/dev/null
# pam_winky wartet beim Zurücksetzen nur 300 ms, der Dienst erledigt es auch danach
for _ in $(seq 30); do [ -e /run/winky/sperre/sudo-1000 ] || break; sleep 0.1; done
pruefe '[ ! -e /run/winky/sperre/sudo-1000 ]' "Passwort-Erfolg setzt die Begrenzung zurück"

# 5. Ohne Terminal und mit ausgeschaltetem Schalter keine Verbindung
cp /etc/pam.d/sudo-nurgeste /etc/pam.d/sudo
n=$(journal_n)
pamtester sudo ubuntu authenticate >/dev/null 2>&1
pruefe '[ "$(journal_n)" = "$n" ]' "ohne Terminal keine Anfrage an den Prüfdienst"
SUDO_UID=1000 $V sudo aus </dev/null >/dev/null
sudo_pam sudo ubuntu authenticate >/dev/null
pruefe '[ "$(journal_n)" = "$n" ] && [ ! -e /etc/winky/sudo-ein ]' "sudo aus: keine Anfrage mehr"
echo "sudo = ja" >> /etc/winky/winky.conf   # nur die Konfiguration ohne Schalterdatei
sudo_pam sudo ubuntu authenticate >/dev/null
pruefe '[ "$(journal_n)" = "$n" ]' "Konfiguration allein reicht nicht (Schalterdatei fehlt)"

# 6. Andere Dienste bleiben unberührt
# Die Winky-Zeile aus common-auth, aber ohne pam_unix (dessen Passwortfrage am Terminal hinge)
SUDO_UID=1000 $V sudo an </dev/null >/dev/null
for d in su login polkit-1; do
  { grep pam_winky /etc/pam.d/common-auth | sed 's/success=[0-9a-z]*/success=done/'
    echo "auth requisite pam_deny.so"; } > /etc/pam.d/$d
done
for d in su login polkit-1; do sudo_pam $d ubuntu authenticate >/dev/null; done
pruefe '[ "$(journal_n)" = "$n" ]' "su, login, polkit-1: keine Anfrage"

# 7. KeePassXC über das Polkit-Prüfprogramm: Vorgabe Gesicht und ✌, abschaltbar
SUDO_UID=1000 $V sudo an </dev/null >/dev/null
pruefe 'SUDO_UID=1000 $V keepassxc an </dev/null | erg | grep -q "\"ok\": true"' "KeePassXC an (✌-Test vorhanden)"
t0=$(date +%s%N); /usr/libexec/winky/winky-polkit-pruefung ubuntu; rc=$?; t=$(( ($(date +%s%N)-t0)/1000000 ))
pruefe '[ $rc = 1 ] && [ $t -lt 9900 ]' "KeePassXC ohne ✌ nicht freigegeben, unter dem Polkit-Limit (${t} ms)"
pruefe 'journalctl -t winky -o cat --no-pager | grep "zweck=keepassxc" | tail -1 | grep -q "geste=1"' "KeePassXC-Prüfung verlangt ✌ (Journal)"
pruefe 'grep -q "\"zweck\":\"keepassxc\"" /run/winky/anfrage/1000.json && [ "$(anfrage)" = nicht_bestaetigt ]' "Desktop-Hinweis für KeePassXC: nicht bestätigt"
SUDO_UID=1000 $V keepassxc geste-aus </dev/null >/dev/null
t0=$(date +%s%N); /usr/libexec/winky/winky-polkit-pruefung ubuntu; t=$(( ($(date +%s%N)-t0)/1000000 ))
pruefe 'journalctl -t winky -o cat --no-pager | grep "zweck=keepassxc" | tail -1 | grep -vq "geste=1" && [ $t -lt 4500 ]' "ohne ✌-Pflicht nur Gesicht, wie bisher (${t} ms)"
SUDO_UID=1000 $V keepassxc geste-an </dev/null >/dev/null
rm -f /var/lib/winky/1000/geste-ok; SUDO_UID=1000 $V keepassxc aus </dev/null >/dev/null
pruefe 'SUDO_UID=1000 $V keepassxc an </dev/null | erg | grep -q "Gesicht und"' "KeePassXC mit ✌ verlangt bestandenen ✌-Test"
install -m0640 -g _winky /dev/null /var/lib/winky/1000/geste-ok

# 8. Rückbau
SUDO_UID=1000 $V sudo an </dev/null >/dev/null
dpkg -r winky >/dev/null 2>&1
pruefe '[ ! -e /etc/winky/sudo-ein ] && ! grep -q pam_winky /etc/pam.d/common-auth' "Deinstallieren entfernt Schalter und PAM-Eintrag"
pruefe '[ ! -e /var/lib/winky/1000/geste-ok ]' "Freigabe mit den Gesichtsdaten gelöscht"
echo; echo "$F Fehler"
