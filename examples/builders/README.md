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

- `arch-builder/` — `arch-builder.dockerfile` + `arch-build.sh`
- `debian-builder/`
- `debian-builder-rust/`
- `debian-builder-python/`
- `debian-builder-php/`
