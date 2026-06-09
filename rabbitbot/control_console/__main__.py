from __future__ import annotations

import uvicorn

from .app import create_app
from .config import ConsoleConfig


def run() -> None:
    config = ConsoleConfig.from_env()
    uvicorn.run(create_app(config), host=config.host, port=config.port)


if __name__ == "__main__":
    run()
