# Builder-Beispiele

Diese Dateien sind reine Referenz — sie werden von der App zur Laufzeit
**nicht** gelesen. Seit Etappe 2 der Planung
(`projects/packages/planung-datei-editor.md` im Vault) sind Builder-Images
vollständig DB-verwaltet und starten auf einer frisch aufgesetzten Instanz
leer ("nackter Start", Michaels ausdrücklicher Wunsch).

Diese fünf Ordner enthalten den Stand der bisher fest im Repo verankerten
Dockerfiles/Skripte (vor der Umstellung), zum Abschreiben/Kopieren beim
manuellen Neuanlegen der jeweiligen Builder-Images über die neue UI
("Neu" → Dateien-Tab):

- `arch-builder/` — `arch-builder.dockerfile` (+ historisches `arch-build.sh`,
  siehe unten)
- `debian-builder/`
- `debian-builder-rust/`
- `debian-builder-python/`
- `debian-builder-php/`

**Seit dem "Virtuellen OS-Modul"** (siehe
`projects/packages/planung-datei-editor.md`) kommt zum Dockerfile noch ein
zweites, ebenfalls DB-editierbares Artefakt hinzu: `build.sh` (Paket bauen)
und optional `publish.sh` (Repo-Index aktualisieren nach erfolgreichem Bau).
Aktuelle Referenz dafür liegt unter `../os-types/{debian,archlinux}/` --
`arch-build.sh` in diesem Ordner ist der alte, VOR dieser Aufteilung
gültige Stand (Klonen + Bauen + Repo-Index in einem Skript, per
ENTRYPOINT ins Image gebacken) und dient nur noch als Kontext, nicht mehr
als Vorlage.
