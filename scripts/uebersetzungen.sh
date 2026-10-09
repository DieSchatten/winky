#!/usr/bin/env bash
# Übersetzungen (gettext, Domäne winky): Vorlage po/winky.pot aus den Quellen erzeugen, jede
# po/<sprache>.po prüfen und nach bau/locale übersetzen. Unvollständige Sprachen brechen ab.
# Läuft im Bau-Container. „./scripts/uebersetzungen.sh aktualisieren“ gleicht die .po-Dateien
# an neue Texte an (für Übersetzer).
set -euo pipefail
cd "$(dirname "$0")/.."
xgettext --force-po -L Python -k_ -kngettext:1,2 --from-code=UTF-8 --add-location=file \
  --package-name=winky --msgid-bugs-address=https://github.com/DieSchatten/winky/issues \
  -o po/winky.pot src/app/*.py src/hinweis/winky-hinweis src/verwalten/winky-verwalten
sed -i '/^"POT-Creation-Date:/d' po/winky.pot
for po in po/*.po; do
  sprache=$(basename "$po" .po)
  if [[ "${1:-}" == aktualisieren ]]; then
    msgmerge -q -U --backup=none --no-fuzzy-matching "$po" po/winky.pot
  fi
  mkdir -p "bau/locale/$sprache/LC_MESSAGES"
  msgmerge -q --no-fuzzy-matching -o "bau/locale/$sprache.po" "$po" po/winky.pot
  stand=$(msgfmt -c --statistics -o "bau/locale/$sprache/LC_MESSAGES/winky.mo" "bau/locale/$sprache.po" 2>&1)
  case "$stand" in
    *untranslated*|*fuzzy*) echo "Übersetzung $sprache unvollständig: $stand" >&2; exit 1 ;;
  esac
  echo "== Übersetzung $sprache: $stand"
done
