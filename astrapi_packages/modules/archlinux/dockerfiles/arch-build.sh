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
LOCAL_REPO="/home/makepkg/repo"
REPO_NAME="${REPO_NAME:-pkgctl}"
BUILD_DIR="/tmp/build-${ITEM_ID}"

# Lokales Repo als pacman-Quelle registrieren (nur wenn Pakete vorhanden)
_repo_db="${LOCAL_REPO}/${REPO_NAME}.db.tar.gz"
_pkg_count=$(ls "${LOCAL_REPO}"/*.pkg.tar.* 2>/dev/null | wc -l) || true
if [ -f "$_repo_db" ] && [ "${_pkg_count}" -gt 0 ]; then
    echo "==> Registriere lokales Repo '${REPO_NAME}' (${LOCAL_REPO}) ..."
    # pacman liest die Datenbank direkt aus dem Mount: repo-add legt
    # <name>.db als Symlink auf <name>.db.tar.gz an, und die Pakete liegen im
    # selben Verzeichnis. Eine beschreibbare Kopie ist dafür nicht nötig – der
    # Mount ist ohnehin beschreibbar, makepkg und repo-add schreiben unten
    # direkt hinein.
    #
    # Nötig ist aber eins: pacman 7 lädt mit "DownloadUser = alpm", also als
    # unprivilegierter Benutzer. Der Mount liegt unter /home/makepkg, und ein
    # per useradd angelegtes Home ist 0700 – alpm kommt dort nicht durch und
    # quittiert die file://-Quelle mit "curl: (37) Could not open file",
    # obwohl das Repo-Verzeichnis selbst für alle lesbar ist.
    sudo chmod 755 /home/makepkg
    # Gleichnamigen Abschnitt aus pacman.conf entfernen. Das Image bringt für
    # dieses Repo bereits einen [<name>]-Eintrag auf den HTTPS-Mirror mit;
    # zwei Abschnitte gleichen Namens quittiert pacman mit
    # "database already registered" und später mit einem harten
    # "Database should be null: failed to register sync database".
    # Die lokale file://-Quelle gewinnt, sie enthält auch die Pakete aus
    # diesem Lauf, die es auf dem Mirror noch nicht gibt.
    awk -v name="[${REPO_NAME}]" '
        $0 == name { skip = 1; next }
        /^\[/      { skip = 0 }
        !skip
    ' /etc/pacman.conf | sudo tee /etc/pacman.conf.new > /dev/null
    sudo mv /etc/pacman.conf.new /etc/pacman.conf
    sudo tee -a /etc/pacman.conf > /dev/null <<EOF

[${REPO_NAME}]
SigLevel = Optional TrustAll
Server = file://${LOCAL_REPO}
EOF
else
    echo "==> Lokales Repo leer oder nicht vorhanden – wird übersprungen."
fi

# System vollständig aktualisieren (nach lokaler Repo-Registrierung)
sudo pacman -Syu --noconfirm

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
PKGDEST="$LOCAL_REPO" makepkg --nodeps --noconfirm --noprogressbar --force

echo "==> Aktualisiere Repo-Datenbank '${REPO_NAME}' ..."
# Kein --new: das fügt nur Pakete hinzu, die noch nicht in der Datenbank sind.
# Zusammen mit "makepkg --force" oben führt das zu veralteten Einträgen – wird
# dieselbe Version neu gebaut, ersetzt makepkg die .pkg.tar.zst, repo-add
# überspringt den vorhandenen Eintrag und die DB behält die alte Prüfsumme.
# Pacman quittiert das beim Installieren mit
# "invalid or corrupted package (checksum)".
repo-add --remove "${LOCAL_REPO}/${REPO_NAME}.db.tar.gz" "${LOCAL_REPO}"/*.pkg.tar.*

echo "==> Fertig."
