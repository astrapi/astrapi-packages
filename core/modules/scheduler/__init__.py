"""core/modules/scheduler – Cron-Scheduler-Modul für AstrapiFlaskUi.

Projekte konfigurieren den Scheduler vor dem App-Start:

    from core.modules.scheduler.engine import configure, init

    configure(job_fn=my_job, get_setting=..., set_setting=..., job_name="Sync")
    init()
"""
from core.ui import Module
from .api import router
from .ui import bp

module = Module(
    key          = "scheduler",
    label        = "Scheduler",
    icon         = "clock",
    api_router   = router,
    ui_blueprint = bp,
    nav_group    = "System",
)
