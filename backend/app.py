"""FastAPI 应用工厂（2.0 B4/B6）。

用法：
- 服务：`python3 -m backend`（默认 127.0.0.1:8000，读写 data/coach.db；
  若存在 frontend/dist 则同进程托管前端 SPA，单进程即可用）
- 测试：`create_app(db_path=tmp_path / "test.db")` + fastapi.testclient.TestClient
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from coach.db import Database

from .routes import register_routes

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app(db_path=None, frontend_dist: Path | None = None) -> FastAPI:
    app = FastAPI(
        title="fitness-coach-agent",
        version="2.0-b6",
        description="Fitness Coach 2.0 后端服务层与前端托管（TASKBOOK_2.0 B4/B6）",
    )
    app.state.db_path = Path(db_path) if db_path is not None else None
    app.state.db = Database(app.state.db_path) if db_path is not None else Database()
    app.state.agents: dict[str, object] = {}
    register_routes(app)

    dist = Path(frontend_dist) if frontend_dist else FRONTEND_DIST
    if (dist / "index.html").exists():
        # API 路由已注册在前，/api/* 优先；其余路径回退到 SPA 的 index.html
        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):  # noqa: ANN202
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and str(candidate).startswith(str(dist.resolve())):
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")
    return app
