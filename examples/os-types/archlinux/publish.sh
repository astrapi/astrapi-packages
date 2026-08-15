#!/bin/bash
# publish.sh – Aktualisiert die Pacman-Repo-Datenbank, läuft nur nach einem
# erfolgreichen build.sh (siehe astrapi_packages/utils/build_runner.py).
#
# /repo ist beschreibbar gemountet. REPO_NAME hier direkt anpassen, falls das
# Repo anders heissen soll als "pkgctl" (frueher eine Einstellung, jetzt Teil
# des Skripts -- siehe projects/packages/planung-datei-editor.md,
# "Virtuelles OS-Modul": ein OS-Typ bringt sein Verhalten selbst mit).

set -euo pipefail

REPO_NAME="pkgctl"
LOCAL_REPO="/repo"

shopt -s nullglob
pkgs=("${LOCAL_REPO}"/*.pkg.tar.*)
if [ "${#pkgs[@]}" -eq 0 ]; then
    echo "==> Keine Pakete in ${LOCAL_REPO} gefunden, nichts zu tun."
    exit 0
fi

echo "==> Aktualisiere Repo-Datenbank '${REPO_NAME}' ..."
# Kein --new: das fügt nur Pakete hinzu, die noch nicht in der Datenbank
# sind. Zusammen mit "makepkg --force" in build.sh fuehrt das sonst zu
# veralteten Eintraegen, siehe Kommentar im vormaligen arch-build.sh.
repo-add --remove "${LOCAL_REPO}/${REPO_NAME}.db.tar.gz" "${pkgs[@]}"

echo "==> Fertig."
