# backupctl

Web-UI zur zentralen Verwaltung von Backup-Jobs (Borg, Rsync, Proxmox, Remote-Geräte).

## Voraussetzungen

- Python >= 3.11
- GitLab-Token mit Lesezugriff auf die Package-Registry (für `astrapi-core`)

### Systemabhängigkeiten

```bash
apt install borgbackup wakeonlan openssh-client
```

> Borg wird unter `/var/lib/backupadm/.venv/bin/borg` erwartet.

## Setup nach dem Klonen

1. Virtuelles Environment erstellen und aktivieren:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. pip für die GitLab Package-Registry konfigurieren:

   Datei `~/.config/pip/pip.conf` anlegen (wird von pip automatisch geladen):

   ```ini
   [global]
   extra-index-url = https://<TOKEN_NAME>:<TOKEN_SECRET>@gitlab.com/api/v4/projects/79861535/packages/pypi/simple
   ```

   `<TOKEN_NAME>` und `<TOKEN_SECRET>` sind ein GitLab Deploy-Token oder Personal Access Token
   mit mindestens dem Scope `read_package_registry`.

3. Abhängigkeiten inklusive `astrapi-core` installieren:

   ```bash
   pip install -e .
   ```

## Starten

```bash
backupctl --work-dir data --port 9999
```

**Mit Auto-Reload (Entwicklung):**

```bash
backupctl --work-dir data --port 9999 --reload
```

| Parameter    | Standard    | Beschreibung                            |
|--------------|-------------|-----------------------------------------|
| `--work-dir` | (Pflicht)   | Datenpfad für SQLite-DB und Laufzeitdaten |
| `--port`     | `5001`      | HTTP-Port                               |
| `--host`     | `0.0.0.0`   | Bind-Adresse                            |
| `--reload`   | –           | Auto-Reload bei Dateiänderungen         |

Die Web-Oberfläche ist danach erreichbar unter: `http://localhost:9999`

## Projektstruktur

```
backupctl/
├── _cli.py            # Einstiegspunkt (CLI)
├── _app.py            # ASGI-App-Factory
├── _paths.py          # Pfad-Utilities
├── runner.py          # Job-Executor (Borg, Rsync, Proxmox)
├── api/               # FastAPI-Router und SQLite-Backend
└── modules/           # Feature-Module
    ├── borg/
    ├── rsync/
    ├── proxmox_lxc/
    ├── proxmox_hosts/
    ├── proxmox_jobs/
    └── remotes/
```
