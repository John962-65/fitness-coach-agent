"""`python3 -m backend` 启动本地服务（默认 127.0.0.1:8000）。"""
from __future__ import annotations

import os

import uvicorn

from .app import create_app


def main() -> None:
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
