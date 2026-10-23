"""llm.py 环境防护回归：无效代理变量不得让真实客户端构造崩溃。

背景：代理软件常导出 ALL_PROXY=socks://…，httpx2 对未知 scheme 在
OpenAI 客户端构造时即抛 ValueError（见 PROGRESS §18.2 同源问题）。
"""
import os

import pytest

from coach.llm import LLMClient, _drop_unusable_proxy_env


def test_socks_scheme_dropped_http_kept(monkeypatch):
    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:7897/")
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:7897/")
    removed = _drop_unusable_proxy_env()
    assert "ALL_PROXY" in removed
    assert "https_proxy" not in removed
    assert os.environ["https_proxy"] == "http://127.0.0.1:7897/"


def test_socks5_dropped_without_socksio(monkeypatch):
    try:
        import socksio  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("socksio 已安装，socks5 代理可用")
    monkeypatch.setenv("all_proxy", "socks5://127.0.0.1:1080")
    assert "all_proxy" in _drop_unusable_proxy_env()
    assert "all_proxy" not in os.environ


def test_no_scheme_value_dropped(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "127.0.0.1:7897")
    assert "HTTP_PROXY" in _drop_unusable_proxy_env()


def test_client_constructs_with_invalid_proxy(monkeypatch):
    """修复前：ValueError: Unknown scheme for proxy URL（构造即崩）。"""
    monkeypatch.setenv("FAKE_LLM", "0")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-offline")
    monkeypatch.setenv("LLM_BASE_URL", "https://offline.invalid/v1")
    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:7897/")
    client = LLMClient()  # 只构造客户端，不发请求
    assert client.model
