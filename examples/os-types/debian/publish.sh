#!/bin/bash
# publish.sh – Aktualisiert den APT-Packages-Index, laeuft nur nach einem
# erfolgreichen build.sh (siehe astrapi_packages/utils/build_runner.py).
#
# /repo ist beschreibbar gemountet. GPG_KEY_ID (optional, siehe os_types.
# gpg_key_id) signiert Release -> InRelease + Release.gpg, falls gesetzt und
# der Docker-Aufruf ~/.gnupg gemountet hat (os_types.gnupg_home).
#
# Portiert aus dem vormaligen debian/jobs.py:_update_packages_index()/
# _sign_release() (siehe projects/packages/planung-datei-editor.md,
# "Virtuelles OS-Modul").

set -e

cd /repo

echo "==> Aktualisiere Packages-Index ..."
dpkg-scanpackages --multiversion . > Packages 2>/dev/null
gzip -fk Packages
apt-ftparchive release . > Release
echo "==> Index und Release aktualisiert."

if [ -n "${GPG_KEY_ID:-}" ]; then
    echo "==> Signiere Release (Key: ${GPG_KEY_ID}) ..."
    gpg --batch --yes --clearsign -u "$GPG_KEY_ID" --output InRelease Release
    gpg --batch --yes --armor --detach-sign -u "$GPG_KEY_ID" Release
    echo "==> InRelease + Release.gpg erzeugt."
else
    echo "==> Kein GPG_KEY_ID gesetzt -- Signierung übersprungen."
fi
