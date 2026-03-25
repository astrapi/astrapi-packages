# core/modules/sysinfo/engine.py
"""Systeminfo-Datensammlung für das Core-Sysinfo-Modul.

Projekte können optional projektspezifische Extras und Services konfigurieren:

    from core.modules.sysinfo.engine import configure

    configure(
        services=["myapp", "nginx"],
        extra_info_fn=lambda: {"Version": "1.2.3", "DB": "4 MB"},
    )
"""
import subprocess
import sys
import time
from datetime import datetime

_START_TIME: float = time.time()
_services: list[str] = []
_extra_info_fn = None

_cache: dict = {}
_cache_ts: float = 0.0
_CACHE_TTL: float = 2.0


def configure(
    services: list[str] = None,
    extra_info_fn=None,
) -> None:
    """Konfiguriert projektspezifische Erweiterungen.

    Args:
        services:      Liste von systemd-Service-Namen die angezeigt werden sollen.
        extra_info_fn: Callable () → dict[str, str] mit zusätzlichen Infozeilen.
    """
    global _services, _extra_info_fn
    _services = services or []
    _extra_info_fn = extra_info_fn


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _run(cmd: list, timeout: int = 5) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


from core.system.format import fmt_bytes as _fmt_size


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, _  = divmod(s, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    return " ".join(parts) or "< 1m"


def _disk_usage() -> list:
    try:
        import psutil
        disks = []
        for part in psutil.disk_partitions():
            if part.fstype in ("tmpfs", "devtmpfs", "squashfs", "overlay", "proc", "sysfs"):
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device":     part.device,
                    "mountpoint": part.mountpoint,
                    "fstype":     part.fstype,
                    "total_fmt":  _fmt_size(usage.total),
                    "used_fmt":   _fmt_size(usage.used),
                    "free_fmt":   _fmt_size(usage.free),
                    "percent":    usage.percent,
                })
            except (PermissionError, OSError):
                continue
        return disks
    except Exception:
        return []


def _net_interfaces() -> list:
    try:
        import psutil
        ifaces = []
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        for name, addr_list in addrs.items():
            if name == "lo":
                continue
            ipv4 = [a.address for a in addr_list if a.family.name == "AF_INET"]
            ipv6 = [a.address.split("%")[0] for a in addr_list if a.family.name == "AF_INET6"]
            st = stats.get(name)
            ifaces.append({
                "name":  name,
                "ipv4":  ipv4,
                "ipv6":  ipv6,
                "up":    st.isup if st else False,
                "speed": f"{st.speed} Mbit/s" if st and st.speed else "—",
            })
        return ifaces
    except Exception:
        return []


def _systemd_service(name: str) -> dict:
    status  = _run(["systemctl", "is-active", name])
    enabled = _run(["systemctl", "is-enabled", name])
    desc = ""
    out = _run(["systemctl", "show", name, "--property=Description"])
    if "=" in out:
        desc = out.split("=", 1)[1]
    return {
        "name":    name,
        "active":  status,
        "enabled": enabled,
        "desc":    desc,
        "ok":      status == "active",
    }


# ── Datensammlung ─────────────────────────────────────────────────────────────

def collect() -> dict:
    """Sammelt alle Systemdaten (ohne Cache)."""
    try:
        import psutil
    except ImportError:
        return {"ok": False, "error": "psutil nicht installiert (pip install psutil)"}

    try:
        cpu_pct   = psutil.cpu_percent(interval=0.3)
        cpu_count = psutil.cpu_count(logical=True)
        cpu_freq  = psutil.cpu_freq()
        cpu_model = ""
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        cpu_model = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass

        mem   = psutil.virtual_memory()
        swap  = psutil.swap_memory()
        boot  = psutil.boot_time()

        hostname = _run(["hostname", "-f"]) or _run(["hostname"]) or "?"
        kernel   = _run(["uname", "-r"])
        try:
            import platform
            os_name = platform.platform()
        except Exception:
            os_name = "?"

        import getpass, os as _os
        try:
            current_user = getpass.getuser()
        except Exception:
            current_user = "?"
        cwd = _os.getcwd()


        services   = [_systemd_service(s) for s in _services]
        extra_info = _extra_info_fn() if _extra_info_fn else {}

        procs = []
        for p in sorted(
            psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
            key=lambda p: p.info["cpu_percent"] or 0,
            reverse=True,
        )[:8]:
            procs.append(p.info)

        root_disk = None
        try:
            _rd = psutil.disk_usage("/")
            root_disk = {
                "mountpoint": "/",
                "total_fmt":  _fmt_size(_rd.total),
                "used_fmt":   _fmt_size(_rd.used),
                "free_fmt":   _fmt_size(_rd.free),
                "percent":    _rd.percent,
            }
        except Exception:
            pass

        return {
            "ok":          True,
            "collected_at": datetime.now().strftime("%H:%M:%S"),
            "cpu": {
                "percent": cpu_pct,
                "cores":   cpu_count,
                "freq":    f"{cpu_freq.current:.0f} MHz" if cpu_freq else "—",
                "model":   cpu_model,
            },
            "mem": {
                "percent": mem.percent,
                "total":   _fmt_size(mem.total),
                "used":    _fmt_size(mem.used),
                "free":    _fmt_size(mem.available),
            },
            "swap": {
                "percent": swap.percent,
                "total":   _fmt_size(swap.total),
                "used":    _fmt_size(swap.used),
            },
            "system": {
                "hostname":   hostname,
                "kernel":     kernel,
                "os_name":    os_name,
                "sys_uptime": _fmt_uptime(time.time() - boot),
                "app_uptime": _fmt_uptime(time.time() - _START_TIME),
                "user":       current_user,
                "cwd":        cwd,
            },
            "software": {
                "python":  f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "psutil":  psutil.__version__,
                **extra_info,
            },
            "root_disk":  root_disk,
            "disks":      _disk_usage(),
            "interfaces": _net_interfaces(),
            "services":   services,
            "processes":  procs,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def collect_cached() -> dict:
    global _cache, _cache_ts
    if time.monotonic() - _cache_ts >= _CACHE_TTL:
        _cache = collect()
        _cache_ts = time.monotonic()
    return _cache
