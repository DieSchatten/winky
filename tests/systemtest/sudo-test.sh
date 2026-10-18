#!/bin/bash
# sudo mit Gesicht und ✌ im Wegwerf-System (echter Prüfdienst, Kamera, libpam), ohne gezeigtes
# Handzeichen: Vorbedingungen, Hinweisdatei, Begrenzung, gleichzeitige Anfragen, Zurücksetzen, Rückbau.
# Aufruf (Kamera durchreichen; Test-Drop-in, da _winky sie im rootless Container nicht öffnen darf):
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

# Ergänzen mit echtem Prüfdienst: die künstlichen Vorlagen passen zu keinem Gesicht, also darf
# nichts übernommen werden (fremdes Gesicht oder keins im Bild)
vorher=$(sha256sum /var/lib/winky/1000/vorlagen.bin)
# Eingabe offen halten: Schließt sie sich, bricht der Helfer ab (so endet ein Lauf aus der App)
ERG=$(sleep 40 | SUDO_UID=1000 $G ergaenzen Test | erg)
sleep 1   # der Prüfdienst gibt die Kamera erst beim Beenden frei
pruefe 'echo "$ERG" | grep -qE "\"nicht_erkannt\": true|Too few usable" && [ "$(sha256sum /var/lib/winky/1000/vorlagen.bin)" = "$vorher" ]' "Ergänzen mit echter Aufnahme: ohne erkanntes Gesicht ändert sich nichts"
echo "$ERG" | grep -qE "\"nicht_erkannt\": true|Too few usable" || echo "        Antwort: $ERG"
pruefe '[ "$(stat -c %U:%G:%a /var/lib/winky/1000/vorlagen.bin)" = "root:_winky:640" ]' "Vorlagen danach weiter root:_winky 0640"
pruefe 'SUDO_UID=1000 $V sudo an </dev/null | erg | grep -q "face unlock"' "sudo an verlangt aktive Gesichtsentsperrung"
SUDO_UID=1000 $V aktivieren </dev/null >/dev/null
pruefe 'SUDO_UID=1000 $V sudo an </dev/null | erg | grep -q "face and"' "sudo an verlangt bestandenen ✌-Test"
install -m0640 -g _winky /dev/null /var/lib/winky/1000/geste-ok   # Test ersetzt hier den ✌-Test
pruefe 'SUDO_UID=1000 $V sudo an </dev/null | erg | grep -q "\"ok\": true"' "sudo an mit Administratorrechten"
pruefe '[ -f /etc/winky/sudo-ein ] && grep -q "^sudo = ja" /etc/winky/winky.conf' "Schalter und Konfiguration gesetzt"
pruefe 'grep -q "pam_winky.so services=gdm-password,sudo,polkit-1 geste=sudo,polkit-1" /etc/pam.d/common-auth' "common-auth enthält sudo- und Dialog-Weg"

# 1. Anfrage ohne Handzeichen: Aufforderung, dann nicht bestätigt, Hinweisdatei, Zähler
cp /etc/pam.d/sudo /root/pam-sudo.orig   # echter Stapel (common-auth mit pam_unix) für später
cp /etc/pam.d/sudo-nurgeste /etc/pam.d/sudo
t0=$(date +%s%N); AUS=$(sudo_pam sudo ubuntu authenticate); t=$(( ($(date +%s%N)-t0)/1000000 ))
pruefe 'echo "$AUS" | grep -q "to the camera" && echo "$AUS" | grep -q "not confirmed"' "Aufforderung erscheint, ohne ✌ nicht bestätigt (${t} ms)"
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
pruefe '[ $t -lt 1500 ] && ! grep -q "to the camera" /root/zweite.txt' "zweite gleichzeitige Anfrage sofort abgelehnt (${t} ms)"
pruefe 'grep -q "not confirmed" /root/erste.txt' "erste Anfrage wurde abgebrochen"
pruefe 'journalctl -t winky -o cat --no-pager | grep "zweck=sudo" | tail -2 | grep -c "grund=gleichzeitig" | grep -q 2' "beide mit Grund gleichzeitig im Journal"

# 3. Begrenzung: nach drei unbestätigten gilt nur das Passwort
pruefe '[ "$(cut -d" " -f1 /run/winky/sperre/sudo-1000)" -ge 3 ]' "drei unbestätigte Anfragen gezählt"
t0=$(date +%s%N); AUS=$(sudo_pam sudo ubuntu authenticate); t=$(( ($(date +%s%N)-t0)/1000000 ))
pruefe '! echo "$AUS" | grep -q "to the camera" && [ $t -lt 1500 ]' "vierte Anfrage: keine Kamera, sofort Passwort (${t} ms)"
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
pruefe 'SUDO_UID=1000 $V keepassxc an </dev/null | erg | grep -q "face and"' "KeePassXC mit ✌ verlangt bestandenen ✌-Test"
install -m0640 -g _winky /dev/null /var/lib/winky/1000/geste-ok

P=/usr/libexec/winky/winky-polkit-pruefung
# 7b. Einstellbare Zeit für das ✌: sudo wartet länger, Polkit-Wege bleiben unter 10 s
pruefe 'SUDO_UID=1000 $V geste-zeit 40 </dev/null | erg | grep -q "\"ok\": false"' "mehr als 30 Sekunden abgelehnt"
SUDO_UID=1000 $V geste-zeit 15 </dev/null >/dev/null
cp /etc/pam.d/sudo-nurgeste /etc/pam.d/sudo
sed -i "s/geste_timeout_ms=10000/geste_timeout_ms=35000/" /etc/pam.d/sudo
SUDO_UID=1000 $V keepassxc an </dev/null >/dev/null
rm -f /run/winky/sperre/sudo-1000   # Begrenzung nach unbestätigten Anfragen nicht auslösen
t0=$(date +%s%N); sudo_pam sudo ubuntu authenticate >/dev/null; t=$(( ($(date +%s%N)-t0)/1000000 ))
pruefe '[ $t -ge 14000 ] && [ $t -lt 16500 ] && grep -q "\"frist\":15000" /run/winky/anfrage/1000.json' "sudo wartet die eingestellten 15 s (${t} ms)"
t0=$(date +%s%N); $P ubuntu; t=$(( ($(date +%s%N)-t0)/1000000 ))
pruefe '[ $t -lt 9900 ] && grep -q "\"frist\":9000" /run/winky/anfrage/1000.json' "KeePassXC bleibt unter dem Polkit-Limit (${t} ms)"
SUDO_UID=1000 $V geste-zeit 8 </dev/null >/dev/null
SUDO_UID=1000 $V keepassxc aus </dev/null >/dev/null
# Die Kamera sieht im Test ein fremdes Gesicht: Fehlversuchs- und sudo-Zähler zurücksetzen
rm -f /run/winky/sperre/sudo-1000 /run/winky/sperre/1000

# 8. Administrator-Dialoge (PAM polkit-1): ein Schalter, immer mit ✌, Pause wirkt, Umstellung aus 0.10.0
R=/etc/polkit-1/rules.d/zz-winky-freigaben.rules
dialog_anfrage() { python3 -c "import json;d=json.load(open('/run/winky/anfrage/1000.json'));print(d['zweck'],d['stand'])" 2>/dev/null; }
rm -f /run/winky/sperre/sudo-1000 /run/winky/sperre/1000
n=$(journalctl -t winky -o cat --no-pager | grep -c "zweck=dialog")
pamtester polkit-1 ubuntu authenticate </dev/null >/dev/null 2>&1
pruefe '[ "$(journalctl -t winky -o cat --no-pager | grep -c "zweck=dialog")" = "$n" ]' "ab Werk: Passwortdialog ohne Winky"
pruefe 'SUDO_UID=1000 $V dialoge an </dev/null | erg | grep -q "\"ok\": true" && [ -f /etc/winky/dialoge-ein ] && grep -q "^dialoge = ja" /etc/winky/winky.conf' "Administrator-Dialoge eingeschaltet"
t0=$(date +%s%N); AUS=$(pamtester polkit-1 ubuntu authenticate </dev/null 2>&1); t=$(( ($(date +%s%N)-t0)/1000000 ))
pruefe 'echo "$AUS" | grep -q "to approve" && [ "$(dialog_anfrage)" = "dialog nicht_bestaetigt" ]' "echter polkit-1-Dialog: Aufforderung, ohne ✌ weiter zum Passwort (${t} ms)"
pruefe '[ $t -ge 7500 ] && [ $t -lt 12000 ]' "Dialog wartet die eingestellte ✌-Zeit (8 s), ohne Polkit-Grenze"
pruefe '[ ! -e $R ]' "keine Polkit-Regel: Hintergrund-Abfragen erreichen Winky nie"
SUDO_UID=1000 $V pausieren </dev/null >/dev/null
n=$(journalctl -t winky -o cat --no-pager | grep -c "zweck=dialog")
pamtester polkit-1 ubuntu authenticate </dev/null >/dev/null 2>&1
pruefe '[ "$(journalctl -t winky -o cat --no-pager | grep -c "zweck=dialog")" = "$n" ]' "Pause: Dialog ohne Kamera"
P=/usr/libexec/winky/winky-polkit-pruefung
SUDO_UID=1000 $V keepassxc an </dev/null >/dev/null
t0=$(date +%s%N); $P ubuntu; t=$(( ($(date +%s%N)-t0)/1000000 ))
pruefe '[ $t -lt 1500 ] && journalctl -t winky -o cat --no-pager | tail -1 | grep -q "zweck=keepassxc grund=pausiert"' "Pause gilt auch für KeePassXC (${t} ms)"
SUDO_UID=1000 $V keepassxc aus </dev/null >/dev/null
SUDO_UID=1000 $V fortsetzen </dev/null >/dev/null
SUDO_UID=1000 $V dialoge aus </dev/null >/dev/null
pruefe '[ ! -e /etc/winky/dialoge-ein ] && grep -q "^dialoge = nein" /etc/winky/winky.conf' "Administrator-Dialoge wieder aus"
# Umstellung von 0.10.0: Gruppen-Regel weg, Gruppen werden zum Dialog-Schalter
echo "// alt" > $R; echo "freigaben = updates,system" >> /etc/winky/winky.conf
SUDO_UID=1000 $V migrieren; rc=$?   # wie postinst unter „sudo apt install“
pruefe '[ $rc = 0 ] && [ ! -e $R ] && ! grep -q "^freigaben" /etc/winky/winky.conf && [ -f /etc/winky/dialoge-ein ] && grep -q "^dialoge = ja" /etc/winky/winky.conf' "Update stellt 0.10.0-Gruppen auf den Dialog-Schalter um"
rm -f /run/winky/sperre/sudo-1000 /run/winky/sperre/1000

# 9. Erste Anmeldung nach dem Start: eigener Schalter, nur gdm-password ohne Wiederanmeldung
printf "auth [success=done default=ignore] pam_winky.so services=gdm-password timeout_ms=3000\nauth requisite pam_deny.so\n" > /etc/pam.d/gdm-password
n=$(journalctl -t winky -o cat --no-pager | grep -c "zweck=anmeldung")
pamtester gdm-password ubuntu authenticate >/dev/null 2>&1
pruefe '[ "$(journalctl -t winky -o cat --no-pager | grep -c "zweck=anmeldung")" = "$n" ]' "Erstanmeldung ab Werk: keine Anfrage"
pruefe 'SUDO_UID=1000 $V anmeldung an </dev/null | erg | grep -q "\"ok\": true" && [ -f /etc/winky/anmeldung-ein ] && grep -q "^anmeldung = ja" /etc/winky/winky.conf' "Erstanmeldung eingeschaltet"
pamtester gdm-password ubuntu authenticate >/dev/null 2>&1
for i in $(seq 1 30); do   # der Prüfdienst protokolliert erst am Ende seiner Prüfung
  [ "$(journalctl -t winky -o cat --no-pager | grep -c "zweck=anmeldung")" -gt "$n" ] && break; sleep 0.2
done
pruefe 'journalctl -t winky -o cat --no-pager | grep "zweck=anmeldung" | tail -1 | grep -q "Ergebnis uid=1000"' "Erstanmeldung fragt den Prüfdienst (zweck=anmeldung)"
SUDO_UID=1000 $V anmeldung aus </dev/null >/dev/null
pruefe '[ ! -e /etc/winky/anmeldung-ein ] && grep -q "^anmeldung = nein" /etc/winky/winky.conf' "Erstanmeldung wieder aus"
SUDO_UID=1000 $V anmeldung an </dev/null >/dev/null

# 9b. Schlüsselbund aus dem TPM (im Container ohne TPM: Hostschlüssel für die Logik)
pruefe 'systemctl is-active -q winky-schluessel.socket && [ "$(stat -c %a /run/winky-schluessel.sock)" = 600 ]' "Schlüsselbund-Dienst: Socket aktiv, nur root"
pruefe 'echo geheim | SUDO_UID=1000 $G schluesselbund an | erg | grep -q "TPM"' "ohne TPM-Chip: klare Meldung, nichts versiegelt"
echo "ubuntu:Testpasswort1" | chpasswd
printf "Testpasswort1" | systemd-creds encrypt --with-key=host --name=winky-schluesselbund-1000 - /var/lib/winky/1000/schluesselbund.cred
chmod 600 /var/lib/winky/1000/schluesselbund.cred
schluessel_frage() { python3 -c "
import socket,struct
s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET); s.connect('/run/winky-schluessel.sock')
s.send(struct.pack('IIII',0x314B4E57,11,1000,0)); s.settimeout(15); print(s.recv(2000)[:1].decode())"; }
pruefe '[ "$(schluessel_frage)" = N ] && journalctl -t winky -o cat --no-pager | tail -3 | grep -q "keine frisch erkannte Erstanmeldung"' "ohne frische Gesichtserkennung kein Passwort"
touch /run/winky/sperre/anmeldung-1000
pruefe '[ "$(schluessel_frage)" = N ] && [ ! -e /run/winky/sperre/anmeldung-1000 ] && journalctl -t winky -o cat --no-pager | tail -3 | grep -q "keine Anmeldemaske"' "ohne Anmeldemaske kein Passwort, Marke verbraucht"
S=/usr/libexec/winky/winky-schluessel
entsiegeln() { python3 -c "
import importlib.machinery as m, importlib.util as u
l=m.SourceFileLoader('s','$S'); s=u.module_from_spec(u.spec_from_loader('s',l)); l.exec_module(s)
p=s.entsiegeln(1000,'ubuntu'); print(p.decode() if p else '-')" 2>/dev/null; }
pruefe '[ "$(entsiegeln)" = Testpasswort1 ]' "Entsiegeln und Prüfung gegen /etc/shadow"
echo "ubuntu:AnderesPasswort2" | chpasswd
pruefe '[ "$(entsiegeln)" = - ] && [ ! -e /var/lib/winky/1000/schluesselbund.cred ] && grep -q schluesselbund_veraltet /var/lib/winky/status/1000.json' "geändertes Passwort: Versiegelung gelöscht, App erfährt es"
U=/usr/lib/systemd/system/winky-schluessel@.service
pruefe 'systemd-analyze security --offline=true $U 2>/dev/null | tail -1 | grep -q "OK"' "Sandbox des Schlüsselbund-Dienstes: $(systemd-analyze security --offline=true $U 2>/dev/null | tail -1 | grep -o "[0-9.]* OK")"

# 9c. Entsperren nur mit ✌: Sperrbildschirm fragt den Gestenweg, das Gesicht allein reicht nicht
rm -f /run/winky/sperre/sudo-1000 /run/winky/sperre/1000
printf "auth [success=done default=ignore] pam_winky.so services=winky-test timeout_ms=3000 geste_timeout_ms=35000\nauth requisite pam_deny.so\n" > /etc/pam.d/winky-test
pruefe 'SUDO_UID=1000 $V entsperren-geste an </dev/null | erg | grep -q "\"ok\": true" && [ -f /etc/winky/entsperren-geste ] && grep -q "^entsperren_geste = ja" /etc/winky/winky.conf' "Entsperren nur mit ✌ eingeschaltet"
t0=$(date +%s%N); AUS=$(pamtester winky-test ubuntu authenticate </dev/null 2>&1); t=$(( ($(date +%s%N)-t0)/1000000 ))
pruefe 'echo "$AUS" | grep -q "to unlock" && journalctl -t winky -o cat --no-pager | tail -1 | grep -q "zweck=sperrbildschirm geste=1"' "Sperrbildschirm: Aufforderung zum ✌, Gestenweg im Prüfdienst"
pruefe '[ $t -ge 7500 ] && [ $t -lt 11000 ]' "ohne ✌ kommt das Passwort nach höchstens 8 s (${t} ms)"
auth_direkt() { python3 -c "
import socket,struct
s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET); s.connect('/run/winky.sock')
s.send(struct.pack('IIII',0x314B4E57,1,1000,0)); s.settimeout(15); print(struct.unpack('IIfI',s.recv(64))[1])"; }
pruefe '[ "$(auth_direkt)" = 6 ] && journalctl -t winky -o cat --no-pager | tail -1 | grep -q "grund=geste_noetig"' "Prüfdienst lehnt den reinen Gesichtsweg ab, solange ✌ verlangt ist"
SUDO_UID=1000 $V entsperren-geste aus </dev/null >/dev/null
pruefe '[ ! -e /etc/winky/entsperren-geste ] && grep -q "^entsperren_geste = nein" /etc/winky/winky.conf' "Entsperren nur mit ✌ wieder aus"
rm -f /run/winky/sperre/sudo-1000 /run/winky/sperre/1000

# 9d. Echtes sudo im Terminal: verpasstes ✌, Enter ohne Passwort, Winky fragt noch einmal
rm -f /run/winky/sperre/sudo-1000 /run/winky/sperre/1000
SUDO_UID=1000 $V sudo an </dev/null >/dev/null
echo "ubuntu:Testpasswort1" | chpasswd
echo "ubuntu ALL=(ALL) ALL" > /etc/sudoers.d/ubuntu; chmod 440 /etc/sudoers.d/ubuntu
SUDO_AUS=$(python3 - <<'TERMINAL'
import os, pty, select, time
pid, fd = pty.fork()
if pid == 0:
    os.execvp("setpriv", ["setpriv", "--reuid=ubuntu", "--regid=ubuntu", "--init-groups",
                          "--reset-env", "bash", "-c", "sudo -k; LANG=C sudo true; echo ENDE=$?"])
aus, gesendet, ende = b"", 0, time.time() + 40
while time.time() < ende and b"ENDE=" not in aus:
    if select.select([fd], [], [], 0.5)[0]:
        try:
            d = os.read(fd, 4096)
        except OSError:
            break
        if not d:
            break
        aus += d
        if aus.count(b"password for") > gesendet:
            time.sleep(0.3)
            # erst verpasst: Enter ohne Passwort; beim zweiten Mal abbrechen
            os.write(fd, b"\n" if gesendet == 0 else b"\x03")
            gesendet += 1
print(aus.decode(errors="replace"))
TERMINAL
)
pruefe 'echo "$SUDO_AUS" | grep -q "Enter without a password" && echo "$SUDO_AUS" | grep -q "Sorry, try again" && [ "$(echo "$SUDO_AUS" | grep -c "show ✌ to the camera")" -ge 2 ]' "echtes sudo: nach verpasstem ✌ und Enter fragt Winky noch einmal"
# Passwort während des Wartens aufs ✌, mit dem echten Stapel (common-auth mit pam_unix): ohne
# Anzeige, ohne Warten, Kamera gleich aus; falsch Getipptes bleibt nicht für den nächsten Versuch
cp /root/pam-sudo.orig /etc/pam.d/sudo
cat > /root/terminal.py <<'TERMINAL'
import json, os, pty, select, sys, time
schritte = json.loads(sys.argv[1])   # [[Auslöser, Text], …]: Text tippen, sobald Auslöser erscheint
pid, fd = pty.fork()
if pid == 0:
    os.execvp("setpriv", ["setpriv", "--reuid=ubuntu", "--regid=ubuntu", "--init-groups",
                          "--reset-env", "bash", "-c", "sudo -k; LANG=C sudo true; echo ENDE=$?"])
aus, ab, getippt, ende = b"", 0, None, time.time() + 60
while time.time() < ende and b"ENDE=" not in aus:
    if select.select([fd], [], [], 0.2)[0]:
        try:
            d = os.read(fd, 4096)
        except OSError:
            break
        if not d:
            break
        aus += d
    if schritte and schritte[0][0].encode() in aus[ab:]:
        ab = aus.index(schritte[0][0].encode(), ab) + len(schritte[0][0])
        time.sleep(0.5)
        os.write(fd, schritte.pop(0)[1].encode())
        getippt = time.time()
print(aus.decode(errors="replace"))
print(f"DAUER_MS={int((time.time() - getippt) * 1000) if getippt else 99999}")
TERMINAL
rm -f /run/winky/sperre/sudo-1000 /run/winky/sperre/1000
SUDO_AUS=$(python3 /root/terminal.py '[["to the camera", "Testpasswort1\n"]]')
pruefe 'echo "$SUDO_AUS" | grep -q "ENDE=0" && echo "$SUDO_AUS" | grep -q "Winky: password: \*\*\*" && ! echo "$SUDO_AUS" | grep -q -e Testpasswort1 -e "password for" && [ "$(echo "$SUDO_AUS" | sed -n "s/^DAUER_MS=//p")" -lt 3000 ]' "echtes sudo: Passwort während des Wartens getippt, Sterne statt Zeichen, sofort weiter"
echo "$SUDO_AUS" | grep -q "ENDE=0" || echo "$SUDO_AUS" | tr -d "\r" | sed 's/^/        /' | tail -8
sleep 1
pruefe 'journalctl -t winky -o cat --no-pager | grep "zweck=sudo" | tail -1 | grep -q "grund=passwort" && [ "$(anfrage)" = passwort ]' "Prüfdienst: Passwort statt ✌, Kamera aus, Hinweis schließt"
SUDO_AUS=$(python3 /root/terminal.py '[["to the camera", "falsch\n"], ["to the camera", "\n"], ["password for", "Testpasswort1\n"]]')
pruefe 'echo "$SUDO_AUS" | grep -q "ENDE=0" && echo "$SUDO_AUS" | grep -q "Sorry, try again" && echo "$SUDO_AUS" | grep -q "password for" && ! echo "$SUDO_AUS" | grep -q -e falsch -e Testpasswort1' "falsch getippt: sudo fragt neu, Enter führt zur Passwortfrage, nichts bleibt hängen"
echo "$SUDO_AUS" | grep -q "ENDE=0" || echo "$SUDO_AUS" | tr -d "\r" | sed 's/^/        /' | tail -8
rm -f /etc/sudoers.d/ubuntu /run/winky/sperre/sudo-1000 /run/winky/sperre/1000
SUDO_UID=1000 $V sudo aus </dev/null >/dev/null

# 9e. IR-Schutz: im Container ohne Geräteverwaltung klar abgelehnt, keine halbe Regel zurück
pruefe 'SUDO_UID=1000 $V ir-schutz an </dev/null | erg | grep -q "\"ok\": false" && [ ! -e /etc/udev/rules.d/72-winky-ir-kamera.rules ]' "IR-Schutz ohne udev: abgelehnt, keine Regel zurückgelassen"
pruefe 'SUDO_UID=1000 $G ir-schutz an </dev/null | erg | grep -qi "administrator"' "IR-Schutz nur mit Administratorpasswort"

# 9f. Gesichtsdaten im TPM versiegeln: ohne Chip klar abgelehnt; mit vorgetäuschtem Chip
#     (Hostschlüssel) Versiegeln, Rücknahme bei Fehlern, Entsiegeln beim Start, Prüfdienst nur
#     aus dem Arbeitsspeicher, nicht mehr entsiegelbar, neue Aufnahme, Ausschalten
B=/var/lib/winky/1000/vorlagen.bin; C=/var/lib/winky/1000/vorlagen.cred; R=/run/winky/vorlagen/1000/vorlagen.bin
cp $B /root/vorlagen.orig
pruefe 'systemctl is-enabled -q winky-entsiegeln.service' "Entsiegel-Dienst beim Start eingeschaltet"
pruefe 'SUDO_UID=1000 $V vorlagen-tpm an </dev/null | erg | grep -q "TPM" && cmp -s $B /root/vorlagen.orig && [ ! -e $C ] && ! grep -q "^vorlagen_tpm = ja" /etc/winky/winky.conf' "ohne TPM-Chip: Versiegeln abgelehnt, Gesichtsdaten unverändert"
pruefe 'SUDO_UID=1000 $G vorlagen-tpm an </dev/null | erg | grep -qi "administrator"' "Versiegeln nur mit Administratorpasswort"
mv /usr/bin/systemd-creds /usr/bin/systemd-creds.echt
cat > /usr/bin/systemd-creds <<'ATTRAPPE'
#!/bin/bash
# Test: TPM-Chip vortäuschen (Hostschlüssel statt host+tpm2); mit /root/fehler-1001 scheitert uid 1001
[ "$1" = has-tpm2 ] && exit 0
args=()
for a in "$@"; do
  case "$a" in
    --with-key=host+tpm2) args+=(--with-key=host) ;;
    --tpm2-pcrs=*) ;;
    --name=winky-vorlagen-1001) [ -e /root/fehler-1001 ] && exit 1; args+=("$a") ;;
    *) args+=("$a") ;;
  esac
done
exec /usr/bin/systemd-creds.echt "${args[@]}"
ATTRAPPE
chmod 755 /usr/bin/systemd-creds
mkdir -m750 /var/lib/winky/1001 && chgrp _winky /var/lib/winky/1001 && cp -p $B /var/lib/winky/1001/
touch /root/fehler-1001
pruefe 'SUDO_UID=1000 $V vorlagen-tpm an </dev/null | erg | grep -q "\"ok\": false" && [ ! -e $C ] && [ ! -e $R ] && cmp -s $B /root/vorlagen.orig && [ -e /var/lib/winky/1001/vorlagen.bin ] && ! grep -q "^vorlagen_tpm = ja" /etc/winky/winky.conf' "scheitert es bei einem Benutzer: nichts Halbes, alle Daten wie vorher"
rm /root/fehler-1001
pruefe 'SUDO_UID=1000 $V vorlagen-tpm an </dev/null | erg | grep -q "\"versiegelt\": 2" && grep -q "^vorlagen_tpm = ja" /etc/winky/winky.conf && [ ! -e $B ] && [ ! -e /var/lib/winky/1001/vorlagen.bin ]' "für alle Benutzer versiegelt, unverschlüsselte Dateien gelöscht"
pruefe '[ "$(stat -c %U:%a $C)" = "root:600" ] && ! grep -qa WNKV $C && cmp -s $R /root/vorlagen.orig && [ "$(stat -c %U:%G:%a $R)" = "root:_winky:640" ]' "Festplatte nur verschlüsselt (root 0600), Arbeitsspeicher root:_winky 0640"
rm -rf /var/lib/winky/1001 /run/winky/vorlagen/1001
letztes() { sleep 0.5; journalctl -t winky -o cat --no-pager | grep "Ergebnis uid=1000" | tail -1; }
rm -f /run/winky/sperre/1000
auth_direkt >/dev/null
pruefe 'letztes | grep -qE "status=(treffer|kein_treffer|kein_gesicht) "' "Prüfdienst prüft mit der entsiegelten Kopie"
rm -f /run/winky/sperre/1000; mv $R /root/ram.bin   # wie nach einem Neustart: Arbeitsspeicher leer
auth_direkt >/dev/null
pruefe 'letztes | grep -q "status=nicht_eingerichtet.*grund=vorlagen"' "ohne Kopie im Arbeitsspeicher kein Rückgriff auf die Festplatte"
systemctl start winky-entsiegeln.service
pruefe 'cmp -s $R /root/vorlagen.orig && [ "$(stat -c %U:%G:%a $R)" = "root:_winky:640" ] && ! grep -q vorlagen_tpm_fehler /var/lib/winky/status/1000.json' "beim Start entsiegelt (winky-entsiegeln.service)"
cp $C /root/vorlagen.cred.gut; head -c 64 /root/vorlagen.cred.gut > $C
systemctl start winky-entsiegeln.service
pruefe '[ ! -e $R ] && grep -q vorlagen_tpm_fehler /var/lib/winky/status/1000.json' "nicht mehr entsiegelbar: keine Kopie, die App erfährt es"
cp /root/vorlagen.cred.gut $C; systemctl start winky-entsiegeln.service
pruefe '[ -e $R ] && ! grep -q vorlagen_tpm_fehler /var/lib/winky/status/1000.json' "wieder entsiegelbar: Fehlermeldung verschwindet"
python3 -c "d=bytearray(open('/root/vorlagen.orig','rb').read()); d[-1]^=1; open('/root/vorlagen.neu','wb').write(d)"
python3 -c "
import importlib.machinery as m, importlib.util as u
l=m.SourceFileLoader('v','$V'); v=u.module_from_spec(u.spec_from_loader('v',l)); l.exec_module(v)
v.speichere_vorlagen(1000, open('/root/vorlagen.neu','rb').read())"
pruefe '[ ! -e $B ] && cmp -s $R /root/vorlagen.neu && systemd-creds decrypt --name=winky-vorlagen-1000 $C - | cmp -s - /root/vorlagen.neu' "neue Aufnahme bleibt versiegelt, Kopie im Arbeitsspeicher aktuell"
rm $R   # Ausschalten entschlüsselt dann selbst
pruefe 'SUDO_UID=1000 $V vorlagen-tpm aus </dev/null | erg | grep -q "\"verloren\": \[\]" && cmp -s $B /root/vorlagen.neu && [ "$(stat -c %U:%G:%a $B)" = "root:_winky:640" ] && [ ! -e $C ] && grep -q "^vorlagen_tpm = nein" /etc/winky/winky.conf' "Ausschalten: Gesichtsdaten wieder unverschlüsselt, nichts verloren"
SUDO_UID=1000 $V vorlagen-tpm an </dev/null >/dev/null; rm -f $R; head -c 64 /root/vorlagen.cred.gut > $C
pruefe 'SUDO_UID=1000 $V vorlagen-tpm aus </dev/null | erg | grep -q "\"verloren\": \[1000\]" && [ ! -e $B ] && [ ! -e $C ] && ! grep -q "\"vorlagen\"" /var/lib/winky/status/1000.json' "Ausschalten mit unlesbarem Siegel: Gesicht gilt als nicht aufgenommen"
U=/usr/lib/systemd/system/winky-entsiegeln.service
pruefe 'systemd-analyze security --offline=true $U 2>/dev/null | tail -1 | grep -q "OK"' "Sandbox des Entsiegel-Dienstes: $(systemd-analyze security --offline=true $U 2>/dev/null | tail -1 | grep -o "[0-9.]* OK")"
mv /usr/bin/systemd-creds.echt /usr/bin/systemd-creds
cp -p /root/vorlagen.orig $B; chown root:_winky $B; chmod 640 $B
echo '{"vorlagen": 10, "eingelernt": 1, "test_ok": 2}' > /var/lib/winky/status/1000.json
rm -f /run/winky/sperre/1000

# 10. Rückbau
SUDO_UID=1000 $V sudo an </dev/null >/dev/null
dpkg -r winky >/dev/null 2>&1
pruefe '[ ! -e /etc/winky/sudo-ein ] && ! grep -q pam_winky /etc/pam.d/common-auth' "Deinstallieren entfernt Schalter und PAM-Eintrag"
pruefe '[ ! -e /etc/winky/dialoge-ein ]' "Deinstallieren entfernt den Dialog-Schalter"
pruefe '[ ! -e /etc/winky/anmeldung-ein ]' "Deinstallieren entfernt den Schalter für die Erstanmeldung"
pruefe '! systemctl is-enabled -q winky-entsiegeln.service 2>/dev/null' "Deinstallieren schaltet den Entsiegel-Dienst ab"
pruefe '[ ! -e /var/lib/winky/1000/geste-ok ]' "Freigabe mit den Gesichtsdaten gelöscht"
echo; echo "$F Fehler"
