# core/modules/scheduler/engine.py
"""Multi-Job Scheduler mit Action Registry.

Module registrieren Aktionen einmalig beim Start:

    from astrapi.core.modules.scheduler.engine import register_action
    register_action("hosts.check", "Hosts prüfen", check_hosts)

Jobs werden in YamlStorage("scheduler_jobs") gespeichert und können
über die UI erstellt, bearbeitet und gelöscht werden.
"""
import logging
import threading
import time
from datetime import datetime
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)

TIMEZONE = "Europe/Berlin"  # Fallback; wird zur Laufzeit aus settings_registry gelesen


def _get_timezone() -> str:
    """Liest die Zeitzone aus der Settings-Registry (mit Fallback)."""
    try:
        from astrapi.core.ui.settings_registry import get as _srget
        return _srget("TIMEZONE", TIMEZONE) or TIMEZONE
    except Exception:
        return TIMEZONE


# ── Storage (lazy) ─────────────────────────────────────────────────────────────

def _jobs_store():
    from astrapi.core.ui.storage import YamlStorage
    return YamlStorage("scheduler_jobs")


def _status_store():
    from astrapi.core.ui.storage import YamlStorage
    return YamlStorage("scheduler_status")


class Scheduler:
    """Kapselt APScheduler-Instanz, Action-Registry und Lock.

    Kann mit reset() in den Ausgangszustand zurückversetzt werden
    (nützlich für Test-Isolation).
    """

    def __init__(self):
        self._sch: BackgroundScheduler | None = None
        self._actions: dict[str, dict] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        """Stoppt den Scheduler und setzt den internen Zustand zurück."""
        with self._lock:
            if self._sch is not None and self._sch.running:
                try:
                    self._sch.shutdown(wait=False)
                except Exception:
                    pass
            self._sch = None
            self._actions = {}

    def _get_sch(self) -> BackgroundScheduler:
        if self._sch is None:
            self._sch = BackgroundScheduler(timezone=_get_timezone())
        return self._sch

    # ── Action Registry ────────────────────────────────────────────────────────

    def register_action(
        self,
        key:          str,
        label:        str,
        fn:           Callable,
        source:       str | None = None,
        source_label: str | None = None,
    ) -> None:
        """Registriert eine Scheduler-Aktion.

        Registriert das Modul gleichzeitig als Benachrichtigungsquelle in der
        Notify-Engine, wenn ``source`` angegeben wird.

        Args:
            key:          Eindeutiger Schlüssel, z.B. "hosts.check".
            label:        Anzeigename der Aktion in der UI, z.B. "Hosts prüfen".
            fn:           Callable ohne Argumente.
            source:       Quellen-Key für das Notify-System, z.B. "hosts".
                          Wenn angegeben, wird ``register_source`` automatisch aufgerufen.
            source_label: Anzeigename der Quelle in der Kanal-Konfiguration.
                          Fehlt er, wird ``source`` mit großem Anfangsbuchstaben genutzt.
        """
        self._actions[key] = {"label": label, "fn": fn}
        if source:
            try:
                from astrapi.core.modules.notify.engine import register_source as _rs
                _rs(source, source_label or source.capitalize())
            except Exception as e:
                log.debug("register_action: Notify-Quelle '%s' nicht registriert: %s", source, e)

    def get_registered_actions(self) -> dict[str, str]:
        """Gibt {key: label} aller registrierten Aktionen zurück."""
        return {k: v["label"] for k, v in self._actions.items()}

    # ── Notify helpers ─────────────────────────────────────────────────────────

    def _register_job_notify_source(self, job_id: str, label: str) -> None:
        """Registriert einen Scheduler-Job als Notify-Quelle."""
        try:
            from astrapi.core.modules.notify.engine import register_source as _rs
            _rs(job_id, label)
        except Exception as e:
            log.debug("scheduler: Notify-Quelle '%s' nicht registriert: %s", job_id, e)

    def _unregister_job_notify_source(self, job_id: str) -> None:
        """Entfernt einen Scheduler-Job als Notify-Quelle."""
        try:
            from astrapi.core.modules.notify.engine import unregister_source as _us
            _us(job_id)
        except Exception as e:
            log.debug("scheduler: Notify-Quelle '%s' nicht abgemeldet: %s", job_id, e)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def init(self) -> None:
        """Startet den APScheduler und registriert alle konfigurierten Jobs."""
        sch = self._get_sch()
        if sch.running:
            return
        # Alle gespeicherten Jobs als Notify-Quellen registrieren
        try:
            for job_id, cfg in _jobs_store().list().items():
                self._register_job_notify_source(job_id, cfg.get("label", job_id))
        except Exception as e:
            log.debug("scheduler: Notify-Quellen beim Start nicht geladen: %s", e)
        self._sync_jobs()
        sch.start()

    def _sync_jobs(self) -> None:
        """Synchronisiert APScheduler-Jobs mit der Job-Storage."""
        sch = self._get_sch()
        for apjob in sch.get_jobs():
            sch.remove_job(apjob.id)

        try:
            jobs = _jobs_store().list()
        except Exception as e:
            log.warning("scheduler_jobs Storage nicht verfügbar: %s", e)
            return

        for job_id, cfg in jobs.items():
            if not cfg.get("enabled", False):
                continue
            cron = cfg.get("cron", "").strip()
            if not cron:
                continue
            try:
                sch.add_job(
                    func=self._run_job,
                    trigger=CronTrigger.from_crontab(cron, timezone=_get_timezone()),
                    id=job_id,
                    name=cfg.get("label", job_id),
                    kwargs={"job_id": job_id},
                    replace_existing=True,
                    misfire_grace_time=300,
                )
            except Exception as e:
                log.error("Fehler beim Registrieren von Job '%s': %s", job_id, e)

    # ── Job Execution ──────────────────────────────────────────────────────────

    def _run_job(self, job_id: str) -> None:
        """Führt alle Steps eines Jobs sequenziell aus."""
        cfg = _jobs_store().get(job_id)
        if not cfg:
            log.warning("Job '%s' nicht gefunden", job_id)
            return

        label  = cfg.get("label", job_id)
        steps  = cfg.get("steps", [])
        start  = time.time()
        errors: list[str] = []

        # ── Activity-Log: Start ────────────────────────────────────────────────
        activity_id = None
        try:
            from astrapi.core.system.activity_log import log_activity
            activity_id = log_activity(
                log_type='scheduler',
                module='scheduler',
                item_id=job_id,
                description=f"Scheduler: {label}",
                status='running',
                scheduler_job_id=job_id,
            )
        except Exception as _e:
            log.debug("activity_log nicht verfügbar: %s", _e)

        # ── Start-Benachrichtigung ─────────────────────────────────────────────
        try:
            from astrapi.core.modules.notify import engine as _notify
            _notify.send(
                title   = f"Job gestartet: {label}",
                message = f"{len(steps)} Schritt(e) werden ausgeführt.",
                event   = _notify.INFO,
                source  = job_id,
                tags    = ["scheduler"],
            )
        except Exception as _e:
            log.debug("Notify nicht verfügbar: %s", _e)

        # ── DB-Logging für Steps aktivieren ───────────────────────────────────
        try:
            from astrapi.core.system.logger import set_active_log_id as _set_log_id, log as _hlog
            if activity_id is not None:
                _set_log_id(activity_id)
        except Exception:
            pass

        for step_key in steps:
            action = self._actions.get(step_key)
            if action is None:
                errors.append(f"Unbekannte Aktion: {step_key}")
                log.warning("Unbekannte Aktion '%s' in Job '%s'", step_key, job_id)
                continue
            try:
                log.info("Job '%s': Schritt '%s' startet", job_id, step_key)
                action["fn"]()
                log.info("Job '%s': Schritt '%s' abgeschlossen", job_id, step_key)
            except Exception as e:
                errors.append(f"{step_key}: {e}")
                log.error("Job '%s': Schritt '%s' fehlgeschlagen: %s", job_id, step_key, e)

        try:
            from astrapi.core.system.logger import clear_active_log_id as _clear_log_id
            _clear_log_id()
        except Exception:
            pass

        duration_s   = int(time.time() - start)
        duration     = f"{duration_s}s"
        status_label = "OK" if not errors else ("Fehler: " + "; ".join(errors))

        _status_store().upsert(job_id, {
            "last_run":      datetime.now().strftime("%d.%m.%Y %H:%M"),
            "last_status":   status_label,
            "last_duration": duration,
        })

        # ── Activity-Log: Ende ─────────────────────────────────────────────────
        if activity_id is not None:
            try:
                from astrapi.core.system.activity_log import update_activity_log
                update_activity_log(
                    log_id=activity_id,
                    status='ok' if not errors else 'error',
                    duration_s=duration_s,
                    error_message='; '.join(errors) if errors else None,
                )
            except Exception as _e:
                log.debug("activity_log update fehlgeschlagen: %s", _e)

        # ── Ende-Benachrichtigung ──────────────────────────────────────────────
        try:
            from astrapi.core.modules.notify import engine as _notify
            if errors:
                _notify.send(
                    title   = f"Job fehlgeschlagen: {label}",
                    message = f"Dauer: {duration}\n" + "\n".join(errors),
                    event   = _notify.ERROR,
                    source  = job_id,
                    tags    = ["scheduler"],
                )
            else:
                _notify.send(
                    title   = f"Job abgeschlossen: {label}",
                    message = f"Alle Schritte erfolgreich. Dauer: {duration}",
                    event   = _notify.SUCCESS,
                    source  = job_id,
                    tags    = ["scheduler"],
                )
        except Exception as _e:
            log.debug("Notify nicht verfügbar: %s", _e)

    def trigger_job(self, job_id: str) -> None:
        """Führt einen Job sofort in einem Hintergrundthread aus."""
        threading.Thread(target=self._run_job, kwargs={"job_id": job_id}, daemon=True).start()

    # ── Job CRUD ───────────────────────────────────────────────────────────────

    def _enrich(self, job_id: str, cfg: dict) -> dict:
        """Reichert Job-Config mit APScheduler-Status und letztem Laufstatus an."""
        sch = self._get_sch()
        apjob = sch.get_job(job_id) if sch.running else None
        next_run = (
            apjob.next_run_time.strftime("%d.%m.%Y %H:%M")
            if apjob and apjob.next_run_time else None
        )
        try:
            status = _status_store().get(job_id) or {}
        except Exception:
            status = {}
        return {
            "id":            job_id,
            "label":         cfg.get("label", job_id),
            "cron":          cfg.get("cron", ""),
            "enabled":       cfg.get("enabled", False),
            "steps":         cfg.get("steps", []),
            "notify_start":  cfg.get("notify_start", True),
            "notify_end":    cfg.get("notify_end",   True),
            "next_run":      next_run,
            "last_run":      status.get("last_run", ""),
            "last_status":   status.get("last_status", ""),
            "last_duration": status.get("last_duration", ""),
        }

    def list_jobs(self) -> list[dict]:
        """Gibt alle Jobs mit Status zurück."""
        try:
            return [self._enrich(jid, cfg) for jid, cfg in _jobs_store().list().items()]
        except Exception:
            return []

    def get_job(self, job_id: str) -> dict | None:
        cfg = _jobs_store().get(job_id)
        return self._enrich(job_id, cfg) if cfg else None

    def create_job(self, job_id: str, label: str, cron: str, enabled: bool, steps: list[str],
                   notify_start: bool = True, notify_end: bool = True) -> dict:
        _jobs_store().create(job_id, {
            "label":        label,
            "cron":         cron,
            "enabled":      enabled,
            "steps":        steps,
            "notify_start": notify_start,
            "notify_end":   notify_end,
        })
        self._register_job_notify_source(job_id, label)
        if self._get_sch().running:
            self._sync_jobs()
        return self._enrich(job_id, _jobs_store().get(job_id))

    def update_job(self, job_id: str, label: str, cron: str, enabled: bool, steps: list[str],
                   notify_start: bool = True, notify_end: bool = True) -> dict:
        _jobs_store().update(job_id, {
            "label":        label,
            "cron":         cron,
            "enabled":      enabled,
            "steps":        steps,
            "notify_start": notify_start,
            "notify_end":   notify_end,
        })
        self._register_job_notify_source(job_id, label)  # Label ggf. aktualisiert
        if self._get_sch().running:
            self._sync_jobs()
        return self._enrich(job_id, _jobs_store().get(job_id))

    def delete_job(self, job_id: str) -> None:
        _jobs_store().delete(job_id)
        self._unregister_job_notify_source(job_id)
        try:
            _status_store().delete(job_id)
        except KeyError:
            pass
        sch = self._get_sch()
        if sch.running and sch.get_job(job_id):
            sch.remove_job(job_id)

    def toggle_job(self, job_id: str) -> None:
        current = _jobs_store().get(job_id) or {}
        _jobs_store().update(job_id, {"enabled": not current.get("enabled", False)})
        if self._get_sch().running:
            self._sync_jobs()


# Modul-level Singleton
_scheduler = Scheduler()


def __getattr__(name: str):
    return getattr(_scheduler, name)
