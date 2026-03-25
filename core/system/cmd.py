# core/system/cmd.py
import logging
import socket
import subprocess
from functools import lru_cache

_logger = logging.getLogger(__name__)

# Timeouts für Subprocess-Aufrufe.
# Backup-Jobs können stundenlang laufen → kein globaler Timeout.
# Aber: Info-Abfragen (borg info, borg list) und SSH-Verbindungstests
# sollen nicht ewig hängen.
TIMEOUT_INFO    = 60    # borg info, borg list, rsync --dry-run
TIMEOUT_CONNECT = 15    # SSH-Verbindungstest
TIMEOUT_BACKUP  = None  # Backup selbst: kein Timeout (kann Stunden dauern)


@lru_cache(maxsize=1)
def _local_hostnames() -> frozenset:
    names = set()
    hostname = socket.gethostname()
    fqdn = socket.getfqdn()
    names.add(hostname)
    names.add(fqdn)
    names.add(hostname.split('.')[0])   # Kurzname ohne Domain
    names.add(fqdn.split('.')[0])       # Kurzname ohne Domain
    try:
        names.add(socket.gethostbyname(hostname))
    except OSError:
        pass
    return frozenset(names)


def is_local(host: str) -> bool:
    if not host or host == "local":
        return True
    local = _local_hostnames()
    if host in local:
        return True
    # Kurzname des übergebenen Hosts prüfen ("bart.simpsons.lan" → "bart")
    if host.split('.')[0] in local:
        return True
    return False


def build_connection_string(host: str, ssh_user: str = "backupadm") -> str:
    if is_local(host):
        return "local"
    return f"{ssh_user or 'backupadm'}@{host}"


def run_cmd(cmd, connection: str, env=None, timeout=TIMEOUT_BACKUP, ssh_connect_timeout=10):
    if isinstance(cmd, list):
        cmd = " ".join(cmd)
    if connection == "local":
        return run_cmd_local(cmd, env, timeout=timeout)
    else:
        return run_cmd_remote(cmd, connection, env, timeout=timeout, ssh_connect_timeout=ssh_connect_timeout)


def _log_output(result) -> None:
    """Loggt stdout und stderr eines abgeschlossenen Prozesses."""
    for line in (result.stdout or "").splitlines():
        if line.strip():
            _logger.info(line)
    for line in (result.stderr or "").splitlines():
        if line.strip():
            _logger.info(line)


def run_cmd_local(cmd, env=None, timeout=TIMEOUT_BACKUP):
    final_cmd = ["bash", "-c", cmd]
    try:
        result = subprocess.run(
            final_cmd, check=True, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout,
        )
        _log_output(result)
        return result
    except subprocess.TimeoutExpired:
        _logger.error(f"Timeout ({timeout}s) beim lokalen Befehl: {cmd[:120]}")
        raise


def run_cmd_remote(cmd, connection, env=None, timeout=TIMEOUT_BACKUP, ssh_connect_timeout=10):
    final_cmd = ["ssh", "-o", "BatchMode=yes",
                 "-o", f"ConnectTimeout={ssh_connect_timeout}",
                 connection, cmd]
    try:
        result = subprocess.run(
            final_cmd, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout,
        )
        _log_output(result)
        return result
    except subprocess.TimeoutExpired:
        _logger.error(f"Timeout ({timeout}s) beim Remote-Befehl auf {connection}: {cmd[:120]}")
        raise
