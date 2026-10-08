"""跨客户端/进程共享的实际请求预算。失败也计数，账本不记录提示词或密钥。"""
from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class BudgetExceeded(RuntimeError):
    pass


class RequestBudget:
    def __init__(self, path: Path, limit: int):
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("请求上限必须为正整数")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.limit = limit
        with self._locked() as data:
            if not data:
                data.update(limit=limit, requests=[])
            elif data.get("limit") != limit:
                raise ValueError("不能通过重跑更改现有账本的授权上限")

    @contextmanager
    def _locked(self):
        with self.path.open("a+", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                stream.seek(0)
                raw = stream.read()
                data = json.loads(raw) if raw else {}
                yield data
                stream.seek(0)
                stream.truncate()
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def reserve(self) -> int:
        with self._locked() as data:
            if len(data["requests"]) >= data["limit"]:
                raise BudgetExceeded("真实调用预算已耗尽，本次验收不完整")
            ticket = len(data["requests"]) + 1
            data["requests"].append({"id": ticket, "status": "reserved",
                                     "at": datetime.now(timezone.utc).isoformat()})
            return ticket

    def finish(self, ticket: int, *, usage: dict | None = None, failed: bool = False):
        with self._locked() as data:
            entry = data["requests"][ticket - 1]
            entry["status"] = "failed" if failed else "completed"
            entry["usage"] = {key: usage[key] for key in
                              ("prompt_tokens", "completion_tokens", "total_tokens")
                              if usage and isinstance(usage.get(key), (int, float))}

    def snapshot(self) -> dict:
        with self._locked() as data:
            return {"limit": data["limit"], "used": len(data["requests"]),
                    "remaining": data["limit"] - len(data["requests"]),
                    "failed": sum(r["status"] == "failed" for r in data["requests"]),
                    "total_tokens": sum(r.get("usage", {}).get("total_tokens", 0)
                                        for r in data["requests"])}
