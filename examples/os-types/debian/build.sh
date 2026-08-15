#!/bin/bash
# build.sh – Baut ein Debian-Paket, ausgefuehrt im debian-builder-Image.
#
# Vertrag (siehe astrapi_packages/utils/build_runner.py):
#   /build/src   – PKGBUILD + Zusatzdateien, read-only gemountet
#   /repo        – Repo-Verzeichnis, beschreibbar
#
# Portiert aus dem vormaligen astrapi_packages/modules/debian/jobs.py:_build_cmd()
# (Python-generierter Bash-String) -- inhaltlich unveraendert, jetzt aber ein
# echtes, im Datei-Editor bearbeitbares Skript statt Python-Code (siehe
# projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul").

set -e

BUILD_DIR="/tmp/build-$$"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
cp -r /build/src/. .

[[ ! -f PKGBUILD ]] && { echo "FEHLER: PKGBUILD nicht gefunden in $(pwd)"; exit 1; }

# Variablen-Stand vor dem Einlesen merken, um alle von der PKGBUILD neu
# gesetzten Variablen zu erkennen -- auch eigene Hilfsvariablen, nicht nur
# eine feste Standardliste.
_vars_before=$(compgen -v)
source ./PKGBUILD
_pkgbuild_vars=$(comm -13 <(echo "$_vars_before" | sort) <(compgen -v | sort) | tr '\n' ' ')

export srcdir="$(pwd)"
export startdir="$(pwd)"

# Architektur: PKGBUILD 'any' → Debian 'all'
DEB_ARCH="${arch[0]:-all}"
[[ "$DEB_ARCH" == "any" ]] && DEB_ARCH="all"
[[ "$DEB_ARCH" == "x86_64" ]] && DEB_ARCH="amd64"
[[ "$DEB_ARCH" == "aarch64" ]] && DEB_ARCH="arm64"

STAGING=/tmp/staging-$$
rm -rf "$STAGING"
mkdir -p "$STAGING/DEBIAN"
export pkgdir="$STAGING"

if declare -f prepare &>/dev/null; then
    echo "=== Starte prepare() ==="
    prepare
    echo "=== prepare() abgeschlossen ==="
fi

if declare -f build &>/dev/null; then
    echo "=== Starte build() ==="
    build
    echo "=== build() abgeschlossen ==="
fi

if declare -f check &>/dev/null; then
    echo "=== Starte check() ==="
    check
    echo "=== check() abgeschlossen ==="
fi

echo "=== Starte package() ==="
fakeroot -- bash -c "$(declare -p $_pkgbuild_vars pkgdir srcdir startdir 2>/dev/null || true); $(declare -f package); package"
echo "=== package() abgeschlossen ==="

{
  echo "Package: $pkgname"
  echo "Version: ${pkgver}-${pkgrel}"
  echo "Architecture: $DEB_ARCH"
  echo "Maintainer: ${maintainer:-astrapi <astrapi@localhost>}"
  echo "Description: ${pkgdesc:-(no description)}"
  if [[ ${#depends[@]} -gt 0 ]]; then
    deps=$(printf '%s, ' "${depends[@]}")
    echo "Depends: ${deps%, }"
  fi
} > "$STAGING/DEBIAN/control"

echo "--- DEBIAN/control ---"
cat "$STAGING/DEBIAN/control"
echo "---"

DEB_FILE="/repo/${pkgname}_${pkgver}-${pkgrel}_${DEB_ARCH}.deb"
fakeroot dpkg-deb --build "$STAGING" "$DEB_FILE"
echo "Gebaut: $DEB_FILE"
