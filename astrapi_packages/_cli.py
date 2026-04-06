"""astrapi_packages._cli – Console-Script-Einstiegspunkt.

Start:
    astrapi-packages --work-dir /opt/astrapi-packages --port 5001
    astrapi-packages --work-dir /opt/astrapi-packages --port 5001 --debug    # Debug-Modus (inkl. reload)
"""
from astrapi.core.system.paths import run_app


def main() -> None:
    run_app("astrapi_packages._app:app", "astrapi-packages", default_port=5001)


if __name__ == "__main__":
    main()
