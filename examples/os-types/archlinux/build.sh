#!/bin/bash
# build.sh – Baut ein Arch-Linux-Paket, ausgefuehrt im arch-builder-Image.
#
# Vertrag (siehe astrapi_packages/utils/build_runner.py):
#   /build/src   – PKGBUILD + Zusatzdateien, read-only gemountet (egal ob
#                  die Quelle git oder DB-verwaltet war -- das hat der Host
#                  vorher vereinheitlicht, kein Klonen hier mehr noetig)
#   /repo        – Repo-Verzeichnis, beschreibbar
#
# Portiert aus dem vormaligen examples/builders/arch-builder/arch-build.sh
# (siehe projects/packages/planung-datei-editor.md, "Virtuelles OS-Modul") --
# der Host erledigt jetzt das Klonen, dieses Skript nur noch den eigentlichen
# Bau. Das frühere lokale-Repo-als-pacman-Quelle-Registrieren + repo-add
# stehen jetzt in publish.sh (läuft nur nach erfolgreichem Bau).

set -euo pipefail

BUILD_DIR="/tmp/build-$$"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
cp -r /build/src/. .

echo "==> System aktualisieren ..."
sudo pacman -Syu --noconfirm

echo "==> Importiere GPG-Keys aus PKGBUILD ..."
mapfile -t pgpkeys < <(
    grep -E '^\s*validpgpkeys\s*=' PKGBUILD 2>/dev/null \
    | grep -oP "'[A-F0-9]{16,}'" \
    | tr -d "'"
)
for key in "${pgpkeys[@]}"; do
    echo "    gpg --recv-keys ${key}"
    gpg --keyserver hkps://keys.openpgp.org --recv-keys "$key" 2>/dev/null \
    || gpg --keyserver hkps://keyserver.ubuntu.com --recv-keys "$key" 2>/dev/null \
    || true
done

echo "==> Installiere Abhängigkeiten ..."
mapfile -t deps < <(
    makepkg --printsrcinfo 2>/dev/null \
    | grep -E '^\s+(make)?depends\s*=' \
    | sed 's/.*= //; s/[<>=].*//; s/[[:space:]]//g; s/"//g' \
    | grep -v '^$'
)
if [ "${#deps[@]}" -gt 0 ]; then
    echo "    Pakete: ${deps[*]}"
    yay -S --noconfirm --needed --asdeps "${deps[@]}"
fi

echo "==> Starte makepkg ..."
PKGDEST="/repo" makepkg --nodeps --noconfirm --noprogressbar --force

echo "==> Fertig (build.sh) -- Repo-Index folgt in publish.sh."
