# packagectl – Projekt-Grundsätze

## Was ist packagectl?

Basierend auf astrapi-framework soll eine Webanwendung entstehen die aus lokalen oder
offiziellen PKGBUILDs Pakete für Arch Linux baut. Dafür soll ein Arch Linux Docker Image
genutzt werden. Als Module stehen "Docker" und "Pakete" zur Verfügung. Zusätzlich soll
alles über den Scheduler steuerbar sein. Langfristig soll das auf Debian- und Alpine-Pakete
erweiterbar sein.

---

## Modul: Docker

Verwaltet Build-Container-Images.

**Felder:** Name (ID), Tag, Dockerfile-Inhalt
**Image-Name:** wird automatisch als `ctl/<name>:<tag>` zusammengesetzt
**Aktionen:** Image bauen, aktualisieren (Base-Image pullen + rebuild), Build-Log
**Status-Felder:** `last_status`, `last_built`, `last_log`

### Dockerfile (Arch Linux Build-Container)

```dockerfile
# ── Stage 1: Bootstrap herunterladen und entpacken ────────────────────────
FROM alpine AS bootstrap
RUN apk add --no-cache zstd
ADD https://geo.mirror.pkgbuild.com/iso/latest/archlinux-bootstrap-x86_64.tar.zst /tmp/
RUN mkdir /archroot && \
    zstd -d /tmp/archlinux-bootstrap-x86_64.tar.zst --stdout | \
    tar -x -C /archroot --strip-components=1

# ── Stage 2: Arch Linux from Scratch ──────────────────────────────────────
FROM scratch
COPY --from=bootstrap /archroot /

ARG LOCAL_MIRROR=https://geo.mirror.pkgbuild.com
RUN sed -i '/^\[options\]/a DisableSandbox' /etc/pacman.conf && \
    echo "Server = ${LOCAL_MIRROR}/\$repo/os/\$arch" > /etc/pacman.d/mirrorlist && \
    pacman-key --init && \
    pacman-key --populate archlinux && \
    pacman -Syu --noconfirm && \
    rm -rf /var/cache/pacman/pkg/*

RUN pacman -S --needed --noconfirm base-devel git wget zsh && \
    rm -rf /var/cache/pacman/pkg/*

RUN sed -i "s/^#MAKEFLAGS=.*/MAKEFLAGS=\"-j$(nproc)\"/" /etc/makepkg.conf
RUN wget -q -O /etc/zsh/zshrc https://git.grml.org/f/grml-etc-core/etc/zsh/zshrc

ARG user=makepkg
RUN useradd --system --create-home $user && \
    echo "$user ALL=(ALL:ALL) NOPASSWD:ALL" > /etc/sudoers.d/$user

# run.sh als base64 einbetten (Legacy-Builder-kompatibel, kein BuildKit nötig)
# Dekodiert: #!/bin/bash – nimmt $1=Paketname, $2=Git-URL (optional für custom-Builds)
RUN echo 'IyEvYmluL2Jhc2gKCmlmIHRlc3QgLXogIiQxIjsgdGhlbgogICAgZWNobyAiRVJST1I6IHBscyBzcGVjaWZ5IGEgc29mdHdhcmUgdG8gYnVpbGQhIgogICAgZXhpdCAxCmZpCgojICQyIG9wdGlvbmFsOiB3ZW5uIGFuZ2VnZWJlbiAtPiBnaXQgY2xvbmUgKEFVUiksIHNvbnN0IHZvci1nZW1vdW50ZXRlIFNvdXJjZSBudXR6ZW4gKGN1c3RvbSkKaWYgdGVzdCAtbiAiJDIiOyB0aGVuCiAgICBnaXQgY2xvbmUgIiQyIiB+L3NvdXJjZQpmaQoKY2Qgfi9zb3VyY2UKCmVjaG8gIklORk86IGluc3RhbGxpbmcgYWxsIG1pc3NpbmcgZGVwZW5kZW5jaWVzLi4uIgptYWtlcGtnIC0tcHJpbnRzcmNpbmZvID4gU0lORk8KCnN1ZG8gcGFjbWFuIC1TeXVxIC0tbm9jb25maXJtCgp3aGlsZSByZWFkIC1yIC11IDkga2V5IHZhbHVlOyBkbwogICAgaWYgWyAiJGtleSIgPT0gImRlcGVuZHMiIF07IHRoZW4KICAgICAgICBkZXA9JChlY2hvICIkdmFsdWUiIHwgY3V0IC1kICcgJyAtZjIgfCBjdXQgLWQgJz4nIC1mMSkKICAgICAgICBlY2hvICJpbnN0YWxsaW5nICRkZXAuLi4iCiAgICAgICAgeWF5IC0tbm9jb25maXJtIC0tbm9lZGl0IC0tcmVtb3ZlbWFrZSAtUyAiJGRlcCIKICAgIGZpCmRvbmUgOTwgIlNJTkZPIgoKZWNobyAiZm91bmQgJChucHJvYykgY29yZXMiCm1ha2Vwa2cgLXMgLWMgLUMgLS1ub2NvbmZpcm0gLS1ub3Byb2dyZXNzYmFyIHwgdGVlIH4vJDEtYnVpbGQubG9nCnN1ZG8gY2hvd24gbWFrZXBrZyAvaG9tZS9tYWtlcGtnL3BrZwpta2RpciAtcCAvaG9tZS9tYWtlcGtnL3BrZwpjcCAuLyoucGtnLnRhci4qIC9ob21lL21ha2Vwa2cvcGtnCg==' \
    | base64 -d > /usr/bin/run.sh && chmod +x /usr/bin/run.sh

USER makepkg
WORKDIR /home/makepkg

RUN git clone https://aur.archlinux.org/yay-bin.git && \
    cd yay-bin && \
    makepkg -sri --needed --noconfirm && \
    cd && \
    rm -rf .cache yay-bin

ENTRYPOINT ["run.sh"]
```

---

## Modul: Pakete

Verwaltet Paketdefinitionen und startet Builds.

**Felder:** Name (ID), Typ (`aur` / `custom`), Quelle (AUR-URL oder PKGBUILD-Inhalt)
**Status-Felder:** `last_status`, `last_built`, `last_log`
**Aktionen:** Paket bauen, Build-Log

### Build-Ablauf

| Typ | Ablauf |
|-----|--------|
| `aur` | `docker run <image> <name> <git-url>` → run.sh klont und baut |
| `custom` | PKGBUILD aus DB in temp-Verzeichnis schreiben → als Volume in Container mounten → run.sh baut aus lokalem Source |

**Nach erfolgreichem Build:**
```
repo-add <repo_path>/<repo_name>.db.tar.gz <paket>.pkg.tar.zst
```

---

## App-Einstellungen (global)

| Einstellung     | Bedeutung                                      | Beispiel                    |
|-----------------|------------------------------------------------|-----------------------------|
| `default_image` | Standard-Build-Container                       | `ctl/arch-builder:latest`   |
| `repo_path`     | Pfad zum lokalen Pacman-Repo auf dem Host      | `/srv/pacman-repo`          |
| `repo_name`     | Name der Repo-Datenbank                        | `local`                     |

---

## Scheduler

- `docker.build` — Image-Build zeitgesteuert auslösen
- `pakete.build` — Paket-Build zeitgesteuert auslösen

---

## Erweiterbarkeit

Das Typ-Feld (`aur` / `custom`) ist der Erweiterungspunkt: `debian` oder `alpine` wären
später weitere Typen mit eigenem Build-Image und Build-Ablauf.

---

## Framework-Konventionen (astrapi-framework)

Stack: FastAPI (`/api/...`) + Flask (HTMX-UI `/`) via `a2wsgi`.

### Modul-Struktur

```
app/modules/<name>/
  __init__.py       → load_modul(Path(__file__).parent, KEY, router, bp)
  api.py            → FastAPI-Router (make_crud_router)
  ui.py             → Flask-Blueprint (make_crud_blueprint + modulspez. Routen)
  jobs.py           → Build-Logik (subprocess, Daemon-Threads)
  storage.py        → store = YamlStorage(KEY)
  schema.yaml       → Felder für CRUD-Modal
  modul.yaml        → label, icon, nav_group, card_actions
  templates/partials/
    list.html       → Card-Body-Inhalt
    list_header.html → Tabellen-Spaltenköpfe
    list_row.html   → Tabellenzeile
```

### jobs.py – Muster

```python
def build(item_id: str) -> None:
    from .storage import store
    item = store.get(item_id)
    store.update(item_id, {"last_status": "building", "last_built": _now()})
    rc, output = _run(cmd, timeout=3600)
    store.update(item_id, {
        "last_status": "ok" if rc == 0 else "error",
        "last_built":  _now(),
        "last_log":    output[-20_000:],
    })

def build_async(item_id: str) -> None:
    threading.Thread(target=build, args=(item_id,), daemon=True).start()
```

### Referenz-Modul

`app/modules/docker/` — immer als Vorlage für neue Module verwenden.
