# core/system/reachability.py
import subprocess
from core.system.logger import log
from core.system.cmd import is_local


def check_ssh(host: str, user: str = "backupadm", timeout: int = 5) -> bool:
    result = subprocess.run(
        ["ssh",
         "-o", "BatchMode=yes",
         "-o", f"ConnectTimeout={timeout}",
         "-o", "StrictHostKeyChecking=no",
         f"{user}@{host}",
         "echo ok"],
        capture_output=True, text=True
    )
    return result.returncode == 0 and "ok" in result.stdout


def require_hosts(hosts: list, user: str = None) -> bool:
    """
    hosts: list of str oder list of (host, user) Tupel.
    user: Fallback-User wenn hosts eine str-Liste ist.
    """
    all_ok = True
    for entry in hosts:
        if isinstance(entry, tuple):
            host, host_user = entry
        else:
            host, host_user = entry, user
        if is_local(host):
            continue
        if not check_ssh(host, host_user):
            log("WARNING", f"Host nicht erreichbar: {host}")
            log("ERROR", f"SSH-Verbindung zu '{host}' fehlgeschlagen – Ausführung abgebrochen")
            all_ok = False
    return all_ok
