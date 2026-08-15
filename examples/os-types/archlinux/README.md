# OS-Typ „archlinux" — Beispielwerte

Unter „OS-Typen" → „Neu":

| Feld | Wert |
|---|---|
| Schlüssel | `archlinux` |
| Anzeigename | `Arch Linux` |
| Repo-Unterordner | `arch/x86_64` |
| Abhängigkeiten-URL-Vorlage | `https://aur.archlinux.org/{name}.git` |
| GPG-Homedir | leer |
| GPG-Signierschlüssel-ID | leer (pacman-Repos werden hier nicht signiert) |

Builder-Image: `../../builders/arch-builder/arch-builder.dockerfile`, dazu
`build.sh` + `publish.sh` aus diesem Ordner im Datei-Editor-Tab des Images
anlegen. `publish.sh` hat den Repo-Namen (`pkgctl`) fest im Skript stehen —
bei Bedarf dort direkt anpassen.

**Achtung Betriebs-Konsequenz:** die URL-Struktur unter `/files/` ändert
sich ggü. dem alten `archlinux`-Modul: `/files/archlinux/x86_64/...` wird zu
`/files/archlinux/...` (der Architektur-Unterordner steckt jetzt im
Repo-Unterordner-Wert `arch/x86_64`, nicht mehr in der URL) —
`pacman.conf` auf anderen Maschinen muss entsprechend angepasst werden.
