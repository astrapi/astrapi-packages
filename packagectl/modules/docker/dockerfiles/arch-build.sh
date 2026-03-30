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

# Lokales Repo als pacman-Quelle registrieren (nur wenn Pakete vorhanden)
_repo_db=$(ls "${LOCAL_REPO}"/*.db.tar.gz 2>/dev/null | head -1) || true
_pkg_count=$(ls "${LOCAL_REPO}"/*.pkg.tar.* 2>/dev/null | wc -l) || true
if [ -n "$_repo_db" ] && [ "${_pkg_count}" -gt 0 ]; then
    _repo_name=$(basename "$_repo_db" .db.tar.gz)
    echo "==> Registriere lokales Repo '${_repo_name}' (${LOCAL_REPO}) ..."
    # Repo ist read-only gemountet – beschreibbare Kopie anlegen damit pacman
    # den benötigten <name>.db Symlink vorfindet
    _repo_tmp=$(mktemp -d)
    chmod 755 "${_repo_tmp}"
    cp "${LOCAL_REPO}"/*.db.tar.gz "${_repo_tmp}/"
    cp "${LOCAL_REPO}"/*.pkg.tar.* "${_repo_tmp}/"
    # Pacman benötigt <name>.db als echte Datei (kein Symlink) und lesbaren Zugriff
    cp "${_repo_tmp}/${_repo_name}.db.tar.gz" "${_repo_tmp}/${_repo_name}.db"
    chmod 644 "${_repo_tmp}"/*
    sudo tee -a /etc/pacman.conf > /dev/null <<EOF

[${_repo_name}]
SigLevel = Optional TrustAll
Server = file://${_repo_tmp}
EOF
else
    echo "==> Lokales Repo leer oder nicht vorhanden – wird übersprungen."
fi

# Paketdatenbanken aktualisieren (nach lokaler Repo-Registrierung)
sudo pacman -Sy --noconfirm

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

if [ -n "$SOURCE_URL" ]; then
    echo "==> Klone ${SOURCE_URL} ..."
    git clone "$SOURCE_URL" src
    cd src
    if [ -n "${SOURCE_SUBDIR:-}" ]; then
        echo "==> Wechsle in Unterordner '${SOURCE_SUBDIR}' ..."
        cd "${SOURCE_SUBDIR}"
    fi
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
find . -maxdepth 1 -name "*.pkg.tar.*" ! -name "*-debug-*" -exec cp {} "$PKG_OUT"/ \;

echo "==> Fertig."
