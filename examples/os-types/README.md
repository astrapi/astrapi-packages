# OS-Typen-Beispiele

Diese Dateien sind reine Referenz — sie werden von der App zur Laufzeit
**nicht** gelesen. Seit dem "Virtuellen OS-Modul"
(`projects/packages/planung-datei-editor.md` im Vault) ist die Liste der
Betriebssysteme selbst vollständig datengetrieben (Modul `os_types`) und
startet auf einer frisch aufgesetzten Instanz leer ("nackter Start").

Jeder Unterordner enthält, zum Abschreiben beim manuellen Neuanlegen über
die UI:

- Empfohlene Werte für den OS-Typ selbst (`key`, `repo_subdir`, ...), siehe
  jeweiliges `README.md`.
- `build.sh` — läuft im zugehörigen Builder-Image (siehe
  `../builders/`), baut ein einzelnes Paket. Wird als Datei-Eintrag des
  Builder-Image-Eintrags angelegt (Datei-Editor-Tab, Dateiname exakt
  `build.sh`).
- `publish.sh` — läuft nach einem erfolgreichen `build.sh` im selben Image,
  aktualisiert den Repo-Index. Optional (fehlt die Datei, wird der Schritt
  übersprungen) — Dateiname exakt `publish.sh`.

Reihenfolge zum Nachbauen eines OS-Typs:

1. Builder-Image anlegen (`../builders/<name>/`-Dockerfile abschreiben) +
   `build.sh`/`publish.sh` aus dem passenden Unterordner hier im
   Datei-Editor-Tab des Images anlegen.
2. OS-Typ unter „OS-Typen" anlegen (Werte aus dem jeweiligen README).
3. Erstes Paket unter „Pakete" anlegen, das neue Builder-Image auswählen.
