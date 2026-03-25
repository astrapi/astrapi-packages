# core/ui/fastapi_templates.py
#
# Hält die konfigurierte Jinja2Templates-Instanz für FastAPI-HTML-Responses.
# Die App konfiguriert die Instanz einmalig beim Start via configure().
# Core-Module rufen get_templates() auf.

_templates = None


def configure(templates_instance) -> None:
    """Registriert die Jinja2Templates-Instanz. Von app/api/templates.py aufzurufen."""
    global _templates
    _templates = templates_instance


def get_templates():
    if _templates is None:
        raise RuntimeError(
            "core.ui.fastapi_templates nicht konfiguriert – configure() aufrufen!"
        )
    return _templates
