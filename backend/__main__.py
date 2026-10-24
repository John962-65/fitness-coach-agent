"""`python3 -m backend` 启动本地服务（默认 127.0.0.1:8000）。

M1.1 P0-3 访问模式守卫：绑定非回环主机（手机/局域网访问）时必须设置
API_ACCESS_TOKEN，否则拒绝启动——Web API 按 uid 读写数据，没有令牌就
开放到局域网等于任何人可以读写任何用户档案。
"""
from __future__ import annotations

import os
import sys

import uvicorn

from .app import LOOPBACK_HOSTS, create_app


def main() -> None:
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    if host not in LOOPBACK_HOSTS and not os.getenv("API_ACCESS_TOKEN"):
        sys.exit(
            f"拒绝启动：API_HOST={host} 为非回环地址，手机/局域网访问必须先设置 "
            "API_ACCESS_TOKEN 环境变量（客户端在「我的 → 数据与设置」配置同一令牌）。"
            "仅本机使用请保持 API_HOST=127.0.0.1。")
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
