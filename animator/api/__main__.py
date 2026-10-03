"""Run the API server: python -m animator.api [--host HOST] [--port PORT]"""

import argparse

import uvicorn

from ..cli import load_env_file


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m animator.api")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="restart on code changes")
    args = parser.parse_args()

    load_env_file()
    uvicorn.run("animator.api.app:create_app", factory=True, host=args.host, port=args.port, reload=args.reload)


main()
