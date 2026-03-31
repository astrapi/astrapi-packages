"""packagectl-spezifische Konfiguration des Core-Sysinfo-Moduls."""
from pathlib import Path

from astrapi.core.modules.sysinfo import module  # noqa: F401  – wird von der Registry erwartet
from astrapi.core.modules.sysinfo.engine import configure

from packagectl._paths import package_dir as _package_dir, db_path as _db_path


def _read_version_yaml(path: Path) -> str:
    try:
        import yaml as _yaml
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return str((_yaml.safe_load(f) or {}).get("version", "?"))
    except Exception:
        pass
    return "?"


def _app_version() -> str:
    try:
        from importlib.metadata import version
        from astrapi.core.system.version import _clean_version
        return _clean_version(version("packagectl"))
    except Exception:
        return _read_version_yaml(_package_dir() / "app.yaml")


def _core_version() -> str:
    try:
        from importlib.metadata import version
        from astrapi.core.system.version import _clean_version
        return _clean_version(version("astrapi-core"))
    except Exception:
        return "?"


def _db_size() -> str:
    from astrapi.core.system.format import fmt_bytes
    p = _db_path()
    if p.exists():
        return fmt_bytes(p.stat().st_size)
    return "—"


def _extra_info() -> dict:
    return {
        "PackageCtl": _app_version(),
        "Core":       _core_version(),
        "DB":         _db_size(),
    }


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
)
