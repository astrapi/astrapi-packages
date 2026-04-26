"""tests/test_button_aktionen.py

Prüft ob alle Button-Aktionen (Speichern, Bearbeiten, Toggle, Löschen,
Paket bauen, Docker-Image bauen) die erwarteten HTTP-Statuscodes liefern.

Pakete-Tests (REST-CRUD) nutzen eine feste Test-ID und bereinigen via
try/finally. Docker-Tests verwenden vorhandene Image-Definitionen.
"""

_TEST_ID = "__test_button__"

_PAKETE_DATA = {
    "source_url": "https://aur.archlinux.org/__test_dummy__",
    "pkg_type": "package",
    "enabled": True,
}


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────


def _pakete_create(client):
    return client.post(
        "/api/pakete/",
        params={"item_id": _TEST_ID},
        json=_PAKETE_DATA,
    )


def _pakete_delete(client):
    client.delete(f"/api/pakete/{_TEST_ID}")


# ── Pakete ────────────────────────────────────────────────────────────────────


def test_pakete_erstellen(client):
    """Speichern-Button im Erstellen-Dialog legt neues Paket an (201)."""
    try:
        resp = _pakete_create(client)
        assert resp.status_code == 201
        # Eintrag muss abrufbar sein
        assert client.get(f"/api/pakete/{_TEST_ID}").status_code == 200
    finally:
        _pakete_delete(client)


def test_pakete_bearbeiten(client):
    """Speichern-Button im Bearbeiten-Dialog aktualisiert das Paket."""
    _pakete_create(client)
    try:
        resp = client.put(
            f"/api/pakete/{_TEST_ID}",
            json={**_PAKETE_DATA, "source_url": "https://aur.archlinux.org/__test_edited__"},
        )
        assert resp.status_code == 200
        item = client.get(f"/api/pakete/{_TEST_ID}").json()
        assert item["source_url"] == "https://aur.archlinux.org/__test_edited__"
    finally:
        _pakete_delete(client)


def test_pakete_toggle(client):
    """Toggle-Button schaltet ein deaktiviertes Paket auf aktiv."""
    _pakete_create(client)
    # Zuerst deaktivieren
    client.patch(f"/api/pakete/{_TEST_ID}/toggle")
    try:
        # Dann wieder aktivieren
        resp = client.patch(f"/api/pakete/{_TEST_ID}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
    finally:
        _pakete_delete(client)


def test_pakete_loeschen(client):
    """Löschen-Button (nach Bestätigung) entfernt das Paket (204)."""
    _pakete_create(client)
    resp = client.delete(f"/api/pakete/{_TEST_ID}")
    assert resp.status_code == 204
    assert client.get(f"/api/pakete/{_TEST_ID}").status_code == 404


def test_pakete_bauen(client):
    """Bauen-Button startet den Paket-Build (202 Accepted)."""
    _pakete_create(client)
    try:
        resp = client.post(f"/api/pakete/{_TEST_ID}/build")
        assert resp.status_code == 202
        assert resp.json()["status"] == "building"
    finally:
        _pakete_delete(client)


# ── Docker ────────────────────────────────────────────────────────────────────


def test_docker_bauen(client):
    """Bauen-Button startet den Docker-Image-Build (202 Accepted)."""
    resp = client.post("/api/docker/arch-builder/build")
    assert resp.status_code == 202
    assert resp.json()["status"] == "building"
