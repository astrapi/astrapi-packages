#!/bin/bash
# arch-build.sh – Baut ein Arch Linux Paket und legt es in /home/makepkg/pkg ab.
#
# Aufruf:
#   <item_id> [source_url]
#
#   item_id     – Paketname (für Logging)
#   source_url  – AUR-Git-URL; fehlt sie, wird PKGBUILD aus /home/makepkg/source verwendet

set -euo pipefail

ITEM_ID="${1:?Fehler: Item-ID fehlt}"
SOURCE_URL="${2:-}"
PKG_OUT="/home/makepkg/pkg"
LOCAL_REPO="/home/makepkg/repo"
BUILD_DIR="/tmp/build-${ITEM_ID}"

# Upstream-Datenbanken aktualisieren (vor lokaler Repo-Registrierung)
sudo pacman -Sy --noconfirm

# Lokales Repo als pacman-Quelle registrieren (falls gemountet und DB vorhanden)
_repo_db=$(ls "${LOCAL_REPO}"/*.db.tar.gz 2>/dev/null | head -1) || true
if [ -n "$_repo_db" ]; then
    _repo_name=$(basename "$_repo_db" .db.tar.gz)
    echo "==> Registriere lokales Repo '${_repo_name}' (${LOCAL_REPO}) ..."
    sudo tee -a /etc/pacman.conf > /dev/null <<EOF

[${_repo_name}]
SigLevel = Optional TrustAll
Server = file://${LOCAL_REPO}
EOF
fi

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

if [ -n "$SOURCE_URL" ]; then
    echo "==> Klone ${SOURCE_URL} ..."
    git clone "$SOURCE_URL" src
    cd src
else
    echo "==> Verwende gemountetes PKGBUILD ..."
    cp /home/makepkg/source/PKGBUILD .
fi

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
makepkg --nodeps --noconfirm --noprogressbar

echo "==> Kopiere Pakete nach ${PKG_OUT} ..."
cp -- *.pkg.tar.* "$PKG_OUT"/

echo "==> Fertig."
