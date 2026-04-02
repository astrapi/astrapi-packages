"""astrapi_packages._cli – Console-Script-Einstiegspunkt.

Start:
    astrapi-packages --work-dir /opt/astrapi-packages --port 9999
    astrapi-packages --work-dir /opt/astrapi-packages --port 9998 --reload   # Entwicklung
"""
import argparse

from astrapi.core.system.paths import add_work_dir_argument, apply_work_dir_argument


def main() -> None:
    parser = argparse.ArgumentParser(prog="astrapi-packages")
    parser.add_argument("--port",   type=int, default=5001)
    parser.add_argument("--host",   default="0.0.0.0")
    parser.add_argument("--reload", action="store_true", default=False)
    add_work_dir_argument(parser)
    args = parser.parse_args()
    apply_work_dir_argument(args, "astrapi-packages")

    import uvicorn
    uvicorn.run(
        "astrapi_packages._app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
