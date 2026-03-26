"""core/modules/settings/ui.py – Flask-Blueprint für Settings UI-Routen."""
import subprocess
from pathlib import Path
from flask import Blueprint, render_template, current_app

KEY = "settings"
bp  = Blueprint(f"{KEY}_ui", __name__)

_SSH_DIR      = Path.home() / ".ssh"
_KEY_TYPES    = ["id_ed25519", "id_ecdsa", "id_rsa"]


def _find_key() -> tuple[Path | None, Path | None]:
    """Gibt (private_key_path, public_key_path) des ersten gefundenen Keys zurück."""
    for name in _KEY_TYPES:
        priv = _SSH_DIR / name
        pub  = _SSH_DIR / f"{name}.pub"
        if priv.exists():
            return priv, pub
    return None, None


def _read_pubkey() -> str | None:
    _, pub = _find_key()
    if pub and pub.exists():
        return pub.read_text().strip()
    return None


def _generate_key() -> tuple[bool, str]:
    """Erzeugt ein neues ed25519-Schlüsselpaar. Gibt (ok, message) zurück."""
    _SSH_DIR.mkdir(mode=0o700, exist_ok=True)
    key_path = _SSH_DIR / "id_ed25519"
    try:
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key_path)],
            check=True, capture_output=True,
        )
        return True, "Neues Schlüsselpaar erfolgreich erzeugt."
    except FileNotFoundError:
        return False, "ssh-keygen nicht gefunden."
    except subprocess.CalledProcessError as e:
        return False, e.stderr.decode().strip() or "Fehler beim Erzeugen des Schlüssels."


def _ctx(flash: str = "") -> dict:
    from astrapi.core.ui.settings_registry import all_settings
    from astrapi.core.ui.module_registry import list_available_core_modules
    return {
        "settings":         all_settings(),
        "modules":          current_app.config.get("LOADED_MODULES", []),
        "flash_message":    flash,
        "core_module_list": list_available_core_modules(),
    }


def _ssh_ctx(flash: str = "", flash_ok: bool = True) -> dict:
    return {
        "pubkey":    _read_pubkey(),
        "flash":     flash,
        "flash_ok":  flash_ok,
    }


@bp.route(f"/ui/{KEY}/content")
def settings_content():
    return render_template("settings/partials/tab.html", **_ctx())


@bp.route(f"/ui/{KEY}/ssh-key")
def ssh_key():
    return render_template("settings/partials/ssh_key.html", **_ssh_ctx())


@bp.route(f"/ui/{KEY}/ssh-key/generate", methods=["POST"])
def ssh_key_generate():
    key_path = _SSH_DIR / "id_ed25519"
    if key_path.exists():
        # Sicherung anlegen
        backup = _SSH_DIR / "id_ed25519.bak"
        key_path.rename(backup)
        pub = _SSH_DIR / "id_ed25519.pub"
        if pub.exists():
            pub.rename(_SSH_DIR / "id_ed25519.pub.bak")
    ok, msg = _generate_key()
    return render_template("settings/partials/ssh_key.html", **_ssh_ctx(msg, ok))
