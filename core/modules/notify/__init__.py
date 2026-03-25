"""core/modules/notify – Benachrichtigungs-Modul für AstrapiFlaskUi.

Mehrere Kanäle (je Backend unterschiedliche Felder) können über die UI
angelegt und verwaltet werden.

Nutzung in anderen Modulen:

    from core.modules.notify import engine as notify

    notify.send("Backup fertig",         "web-01 gesichert",          event=notify.SUCCESS)
    notify.send("Verbindungsfehler",     "host-db nicht erreichbar",  event=notify.ERROR)
    notify.send("Festplatte fast voll",  "< 5 GB frei auf /data",     event=notify.WARNING)
    notify.send("Job gestartet",         "nightly_sync läuft",        event=notify.INFO)
"""

from core.ui import Module
from .api import router
from .ui import bp

module = Module(
    key          = "notify",
    label        = "Benachrichtigungen",
    icon         = "bell",
    nav_group    = "System",
    api_router   = router,
    ui_blueprint = bp,
)
