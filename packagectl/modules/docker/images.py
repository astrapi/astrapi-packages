"""app/modules/docker/images.py – Lädt Image-Definitionen aus images.yaml.

Neues Image hinzufügen:
  1. dockerfiles/<name>.dockerfile anlegen
  2. dockerfiles/<name>-build.sh anlegen (Entrypoint)
  3. Eintrag in images.yaml ergänzen
"""

import yaml
from pathlib import Path

_DIR = Path(__file__).parent


def _load() -> dict[str, dict]:
    meta = yaml.safe_load((_DIR / "images.yaml").read_text(encoding="utf-8")) or {}
    return {
        img_id: {"tag": cfg.get("tag", "latest")}
        for img_id, cfg in meta.items()
    }


IMAGES: dict[str, dict] = _load()
