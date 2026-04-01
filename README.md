# packagectl

Web-UI zum Bauen von Paketen für Arch Linux, Debian und Alpine über Docker-Container.

## Voraussetzungen

- Python >= 3.11
- Docker (für Container-Builds)

## Installation

1. Virtuelles Environment erstellen und aktivieren:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. pip für die GitLab Package-Registry konfigurieren:

   Datei `~/.config/pip/pip.conf` anlegen:

   ```ini
   [global]
   extra-index-url = https://gitlab.com/api/v4/projects/79861535/packages/pypi/simple
   ```

3. packagectl installieren:

   ```bash
   pip install packagectl
   ```

## Starten

```bash
packagectl --work-dir data --port 9999
```

**Mit Auto-Reload (Entwicklung):**

```bash
packagectl --work-dir data --port 9999 --reload
```

| Parameter    | Standard    | Beschreibung                            |
|--------------|-------------|-----------------------------------------|
| `--work-dir` | (Pflicht)   | Datenpfad für SQLite-DB und Laufzeitdaten |
| `--port`     | `5001`      | HTTP-Port                               |
| `--host`     | `0.0.0.0`   | Bind-Adresse                            |
| `--reload`   | –           | Auto-Reload bei Dateiänderungen         |

Die Web-Oberfläche ist danach erreichbar unter: `http://localhost:9999`

## Module

### Docker
Verwaltet Build-Container-Images für verschiedene Distributionen.

- **Felder:** Name (ID), Tag, Dockerfile-Inhalt
- **Image-Name:** wird automatisch als `ctl/<name>:<tag>` zusammengesetzt
- **Aktionen:** Image bauen, aktualisieren, Build-Log anzeigen

### Pakete
Verwaltet Paketdefinitionen und startet Builds.

- **Typen:** `aur` (Arch User Repository), `custom` (lokale PKGBUILD)
- **Status:** last_status, last_built, last_log
- **Aktionen:** Paket bauen, Build-Log anzeigen

## App-Einstellungen

| Einstellung     | Beschreibung                          | Beispiel              |
|-----------------|---------------------------------------|-----------------------|
| `default_image` | Standard-Build-Container              | `ctl/arch-builder:latest` |
| `repo_path`     | Pfad zum lokalen Pacman-Repo          | `/srv/pacman-repo`    |
| `repo_name`     | Name der Repo-Datenbank               | `local`               |

## Projektstruktur

```
packagectl/
├── _cli.py                # Einstiegspunkt (CLI)
├── _app.py                # ASGI-App-Factory
├── _paths.py              # Pfad-Utilities
├── api/                   # FastAPI-Router
└── modules/               # Feature-Module
    ├── docker/            # Docker-Image-Verwaltung
    └── pakete/            # Paket-Build-Verwaltung
        ├── api.py
        ├── ui.py
        ├── jobs.py
        ├── storage.py
        ├── schema.yaml
        └── templates/
```

## Framework

- **Backend:** FastAPI (`/api/...`)
- **Frontend:** Flask mit HTMX (`/`) via `a2wsgi`
- **Framework:** astrapi-framework
