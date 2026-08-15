# OS-Typ „debian" — Beispielwerte

Unter „OS-Typen" → „Neu":

| Feld | Wert |
|---|---|
| Schlüssel | `debian` |
| Anzeigename | `Debian` |
| Repo-Unterordner | `debian` |
| Abhängigkeiten-URL-Vorlage | leer (kein Auto-Anlegen von Deps) |
| GPG-Homedir | z.B. `/home/ottoadm/.gnupg` (leer = keine Signierung) |
| GPG-Signierschlüssel-ID | z.B. `astrapi@localhost` (leer = keine Signierung) |

Builder-Image: `../../builders/debian-builder/debian-builder.dockerfile`
(oder `-rust`/`-python`/`-php` je nach Paket-Bedarf), dazu `build.sh` +
`publish.sh` aus diesem Ordner im Datei-Editor-Tab des Images anlegen.
