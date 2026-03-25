"""
core/ui/schema_loader.py  –  Lädt schema.yaml für Create/Edit-Dialoge

Jedes Modul legt neben __init__.py eine schema.yaml ab:

  app/modules/<key>/schema.yaml

Aufbau:
  id_field:          # optionales ID-Feld (nur beim Anlegen angezeigt)
    name: host_id
    label: Host-ID
    placeholder: "..."
    max: 50

  fields:            # Formularfelder
    - name: description
      type: text     # text | number | boolean | select | list
      label: Beschreibung
      row: 1
      column: 1
      ...
"""

import yaml
from pathlib import Path
from functools import lru_cache


def _normalize_id_field(raw) -> dict | None:
    """Normalisiert id_field auf einheitliches Dict-Format.

    Unterstützte Formate in schema.yaml:
      id_field: id            → String "id" bedeutet auto-increment → None
      id_field:               → kein Wert → None (auto-increment)
        name: host_id         → Dict-Format (astrapi-Stil, User gibt ID ein)
        label: Host-ID
        ...
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    # String-Wert (z.B. "id") → auto-increment, kein Formular-Feld
    return None


@lru_cache(maxsize=32)
def load_schema(schema_path: str) -> dict:
    """Lädt und cached schema.yaml. Gibt {'id_field': ..., 'fields': [...]} zurück.

    id_field ist entweder None (auto-increment, kein ID-Eingabefeld) oder
    ein Dict {name, label, ...} (User gibt ID beim Anlegen ein).
    """
    path = Path(schema_path)
    if not path.exists():
        return {"id_field": None, "fields": []}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        "id_field":    _normalize_id_field(data.get("id_field")),
        "fields":      data.get("fields", []),
        "modal_width": data.get("modal_width", 620),
    }
