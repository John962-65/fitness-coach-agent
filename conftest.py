"""离线 pytest：收集阶段即隔离模型、数据库和日志，禁止网络。"""
import logging
import os
import socket
import sqlite3
import sys
import tempfile
from pathlib import Path

import dotenv
import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
_guard = pytest.MonkeyPatch()
_sandbox = tempfile.TemporaryDirectory(prefix="coach-pytest-")
_guard.setenv("FAKE_LLM", "1")
_guard.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
_logger = logging.getLogger("coach")
_handler = logging.NullHandler()
_logger.addHandler(_handler)

_connect = sqlite3.connect


def _temp_connect(database, *args, **kwargs):
    if str(database) != ":memory:":
        path = Path(database).resolve()
        if str(database).startswith("file:") or not path.is_relative_to(
                Path(tempfile.gettempdir()).resolve()):
            raise RuntimeError("离线测试禁止打开非临时数据库")
    return _connect(database, *args, **kwargs)


def _no_network(*args, **kwargs):
    raise RuntimeError("离线测试禁止联网")


_guard.setattr(sqlite3, "connect", _temp_connect)
_guard.setattr(socket.socket, "connect", _no_network)
_guard.setattr(socket.socket, "connect_ex", _no_network)
_guard.setattr(socket, "create_connection", _no_network)

from coach.db import Database

_init = Database.__init__


def _temporary_database(self, path=None):
    _init(self, Path(path) if path is not None else Path(_sandbox.name) / "default.db")


_guard.setattr(Database, "__init__", _temporary_database)
collect_ignore = ["real_test.py"]


def pytest_unconfigure(config):
    _guard.undo()
    _logger.removeHandler(_handler)
    _sandbox.cleanup()
