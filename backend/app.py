"""FastAPI 应用工厂（2.0 B4/B6 + M1.1 访问模式）。

用法：
- 本机开发：`python3 -m backend`（默认 127.0.0.1:8000，读写 data/coach.db；
  若存在 frontend/dist 则同进程托管前端 SPA，单进程即可用）。
- 手机/局域网访问（M1.1 P0-3）：必须设置 `API_ACCESS_TOKEN` 环境变量；
  非回环主机且未设令牌时启动直接拒绝。客户端请求带 `X-Access-Token` 头
  （前端在「我的 → 数据与设置」里配置）。
- 测试：`create_app(db_path=tmp_path / "test.db")` + fastapi.testclient.TestClient
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from coach.db import Database

from .routes import register_routes

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def create_app(db_path=None, frontend_dist: Path | None = None,
               access_token: str | None = None) -> FastAPI:
    app = FastAPI(
        title="fitness-coach-agent",
        version="2.0-m1.1",
        description="Fitness Coach 2.0 后端服务层与前端托管（TASKBOOK_2.0 B4/B6/M1.1）",
    )
    app.state.db_path = Path(db_path) if db_path is not None else None
    app.state.db = Database(app.state.db_path) if db_path is not None else Database()
    app.state.agents: dict[str, object] = {}
    token = access_token if access_token is not None else (os.getenv("API_ACCESS_TOKEN") or "")
    app.state.access_token = token

    if token:

        @app.middleware("http")
        async def _require_token(request: Request, call_next):
            # /api/health 保持开放，供前端探测"服务需要令牌"并引导配置
            if request.url.path.startswith("/api") and request.url.path != "/api/health":
                if request.headers.get("X-Access-Token") != token:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": {"error": "需要访问令牌（在「我的 → 数据与设置」配置）"}})
            return await call_next(request)

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
