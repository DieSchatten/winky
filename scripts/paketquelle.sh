#!/usr/bin/env bash
# Baut die APT-Paketquelle (für GitHub Pages) aus bau/winky_<version>_amd64.deb nach
# bau/paketquelle und unterschreibt sie. Mit den AppStream-Daten (DEP-11) findet die
# Software-Verwaltung Winky, sobald die Quelle eingerichtet ist. apt lädt Einträge nur, wenn die
# Release-Datei auch die unkomprimierte Fassung nennt (wie bei Ubuntu).
# Aufruf auf dem eigenen Rechner (Signaturschlüssel, gpg fragt nach dessen Passwort):
#   ./scripts/paketquelle.sh
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(sed -n 's/^project(winky VERSION \([0-9.]*\).*/\1/p' CMakeLists.txt)
DEB=bau/winky_${VERSION}_amd64.deb
RING=${WINKY_SCHLUESSELRING:-packaging/winky-archive-keyring.gpg}
SCHLUESSEL=$(gpg --show-keys --with-colons "$RING" | awk -F: '/^fpr/ {print $10; exit}')
Q=bau/paketquelle
D=$Q/dists/stable/main
ID=io.github.dieschatten.Winky
[[ -f "$DEB" ]] || { echo "$DEB fehlt, erst ./scripts/paket-bauen.sh" >&2; exit 1; }

rm -rf "$Q"
mkdir -p "$Q/pool/main/w/winky" "$D/binary-amd64" "$D/dep11"
cp "$DEB" "$Q/pool/main/w/winky/"
cp "$RING" "$Q/winky-archive-keyring.gpg"
cp packaging/winky.sources packaging/paketquelle-index.html "$Q/"
mv "$Q/paketquelle-index.html" "$Q/index.html"
# Für Suchmaschinen: Bestätigung der Google Search Console und Sitemap der Projektseite
cp packaging/google*.html packaging/sitemap.xml "$Q/"
( cd "$Q" && apt-ftparchive packages pool ) > "$D/binary-amd64/Packages"
gzip -9nk "$D/binary-amd64/Packages"; xz -k "$D/binary-amd64/Packages"

# DEP-11: Metainfo aus dem Paket als Katalog mit Paketname und zwischengespeicherten Symbolen
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
dpkg-deb --fsys-tarfile "$DEB" | tar -x -C "$T" ./usr/share/metainfo ./usr/share/icons
python3 - "$T" "$ID" <<'PY'
import os, sys, xml.etree.ElementTree as ET
import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf
t, ID = sys.argv[1], sys.argv[2]
komp = ET.parse(f"{t}/usr/share/metainfo/{ID}.metainfo.xml").getroot()
ET.SubElement(komp, "pkgname").text = "winky"
# Katalogformat: eine Beschreibung je Sprache statt Absätzen mit xml:lang (auch je Version)
LANG = "{http://www.w3.org/XML/1998/namespace}lang"
def aufteilen(eltern):
    beschr = eltern.find("description")
    if beschr is None:
        return
    je_sprache = {}
    for kind in list(beschr):
        if kind.tag == "p":
            sprache = kind.attrib.pop(LANG, "C")
            kind.text = " ".join((kind.text or "").split())
            je_sprache.setdefault(sprache, []).append(kind)
        elif kind.tag in ("ul", "ol"):
            listen = {}
            for li in kind:
                sprache = li.attrib.pop(LANG, "C")
                li.text = " ".join((li.text or "").split())
                listen.setdefault(sprache, ET.Element(kind.tag)).append(li)
            for sprache, liste in listen.items():
                je_sprache.setdefault(sprache, []).append(liste)
    eltern.remove(beschr)
    for sprache, kinder in je_sprache.items():
        neu = ET.SubElement(eltern, "description")
        if sprache != "C":
            neu.set(LANG, sprache)
        neu.extend(kinder)
aufteilen(komp)
# Versionshinweise übernimmt das Katalogformat nur in einer Sprache: Englisch
for version in komp.iter("release"):
    aufteilen(version)
    for b in [b for b in version.findall("description") if LANG in b.attrib]:
        version.remove(b)
# Suchbegriffe aller Sprachen gelten überall (so findet auch „Gesichtserkennung“ auf Englisch)
woerter = komp.find("keywords")
alle = list(dict.fromkeys(k.text for k in woerter))
woerter.clear()
for w in alle:
    ET.SubElement(woerter, "keyword").text = w
# Das Katalogformat kennt nur ein Bild je Bildschirmfoto: das englische
for foto in komp.iter("screenshot"):
    for bild in [b for b in foto.findall("image") if LANG in b.attrib]:
        foto.remove(bild)
svg = f"{t}/usr/share/icons/hicolor/scalable/apps/{ID}.svg"
for groesse, ordner in ((48, "48x48"), (64, "64x64"), (128, "128x128"), (128, "64x64@2"), (256, "128x128@2")):
    os.makedirs(f"{t}/icons/{ordner}", exist_ok=True)
    GdkPixbuf.Pixbuf.new_from_file_at_size(svg, groesse, groesse).savev(
        f"{t}/icons/{ordner}/winky_{ID}.png", "png", [], [])
for groesse, skala in ((48, 1), (64, 1), (128, 1), (64, 2), (128, 2)):
    sym = ET.SubElement(komp, "icon", type="cached", width=str(groesse), height=str(groesse))
    if skala > 1:
        sym.set("scale", str(skala))
    sym.text = f"winky_{ID}.png"
katalog = ET.Element("components", version="1.0", origin="winky")
katalog.append(komp)
ET.ElementTree(katalog).write(f"{t}/katalog.xml", encoding="utf-8", xml_declaration=True)
PY
appstreamcli convert --format=yaml "$T/katalog.xml" "$D/dep11/Components-amd64.yml" >/dev/null
gzip -9nk "$D/dep11/Components-amd64.yml"
for ordner in 48x48 64x64 128x128 64x64@2 128x128@2; do
  tar -C "$T/icons/$ordner" --owner=0 --group=0 --mtime=@0 -cf "$D/dep11/icons-$ordner.tar" .
  gzip -9nk "$D/dep11/icons-$ordner.tar"
done

apt-ftparchive \
  -o APT::FTPArchive::Release::Origin=Winky -o APT::FTPArchive::Release::Label=Winky \
  -o APT::FTPArchive::Release::Suite=stable -o APT::FTPArchive::Release::Codename=stable \
  -o APT::FTPArchive::Release::Architectures=amd64 -o APT::FTPArchive::Release::Components=main \
  -o "APT::FTPArchive::Release::Description=Winky face unlock" \
  release "$Q/dists/stable" > "$T/Release"
mv "$T/Release" "$Q/dists/stable/Release"
gpg --yes --pinentry-mode loopback --local-user "$SCHLUESSEL" --clearsign -o "$Q/dists/stable/InRelease" "$Q/dists/stable/Release"
gpg --yes --pinentry-mode loopback --local-user "$SCHLUESSEL" -abs -o "$Q/dists/stable/Release.gpg" "$Q/dists/stable/Release"
gpgv --keyring "$(realpath "$RING")" "$Q/dists/stable/InRelease" 2>&1 | tail -1
touch "$Q/.nojekyll"
echo "== Paketquelle: $Q (Winky $VERSION, Schlüssel ${SCHLUESSEL: -16})"
