"""astrapi-packages-spezifische Konfiguration des Core-Sysinfo-Moduls."""
from astrapi.core.modules.sysinfo import module  # noqa: F401  – wird von der Registry erwartet
from astrapi.core.modules.sysinfo.engine import configure

from astrapi_packages._paths import package_dir as _package_dir, db_path as _db_path


def _db_size() -> str:
    from astrapi.core.system.format import fmt_bytes
    p = _db_path()
    if p.exists():
        return fmt_bytes(p.stat().st_size)
    return "—"


def _extra_info() -> dict:
    return {
        "DB": _db_size(),
    }


def _update_packages():
    from astrapi.core.modules.updater.engine import get_packages_with_versions
    return get_packages_with_versions()


def _discover_services() -> list[str]:
    try:
        import yaml as _yaml
        app_yaml = _package_dir() / "app.yaml"
        name = str((_yaml.safe_load(app_yaml.read_text()) or {}).get("name", ""))
        if not name:
            return []
        import subprocess
        out = subprocess.run(
            ["systemctl", "list-units", "--all", "--no-legend", "--plain",
             "--type=service", f"{name}*"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return [line.split()[0].removesuffix(".service")
                for line in out.splitlines() if line.strip()]
    except Exception:
        return []


configure(
    services=_discover_services(),
    extra_info_fn=_extra_info,
    extra_disks=["/storage"],
    update_packages_fn=_update_packages,
)
