"""B 站扫码登录——网页版（解决 SSH 终端二维码显示不了的问题）

用法（服务器上）：
  python3 tools/bili_login.py
然后在本机浏览器打开打印出来的地址（Tailscale IP），用手机 B 站 App 扫码。
登录成功后 cookie 存 sources/cookies/bilibili.txt，服务自动退出。
二维码 3 分钟过期会自动换新码，页面无需手动刷新。
"""
from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
COOKIE_FILE = ROOT / "sources" / "cookies" / "bilibili.txt"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TIMEOUT_MIN = 15

state = {"code": "init", "msg": "正在生成二维码…", "svg": "", "cookie_count": 0}


def qr_svg(text: str, box: int = 4) -> str:
    """手写 SVG（不引入 PIL）：按模块矩阵画黑色方块"""
    import qrcode

    qr = qrcode.QRCode(border=2, box_size=box)
    qr.add_data(text)
    qr.make(fit=True)
    m = qr.get_matrix()
    n = len(m)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" '
             f'shape-rendering="crispEdges" width="{n * box}" height="{n * box}">',
             f'<rect width="{n}" height="{n}" fill="white"/>']
    for y, row in enumerate(m):
        x = 0
        while x < n:
            if row[x]:
                run = 1
                while x + run < n and row[x + run]:
                    run += 1
                parts.append(f'<rect x="{x}" y="{y}" width="{run}" height="1"/>')
                x += run
            else:
                x += 1
    parts.append("</svg>")
    return "".join(parts)


def poller() -> None:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    deadline = time.time() + TIMEOUT_MIN * 60
    while time.time() < deadline:
        r = s.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                  timeout=15).json()
        qr_url, qrcode_key = r["data"]["url"], r["data"]["qrcode_key"]
        state.update(code="waiting", svg=qr_svg(qr_url),
                     msg="请用手机 B 站 App → 扫一扫（3 分钟内有效，过期自动换新码）")
        for _ in range(90):
            resp = s.get("https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                         params={"qrcode_key": qrcode_key}, timeout=15)
            p = resp.json()
            code = p["data"]["code"]
            if code == 86038:  # 过期 → 换新码
                state["msg"] = "二维码已过期，正在换新码…"
                break
            if code in (86090, 86091):
                state["msg"] = "已扫码——请在手机上点「确认登录」"
            elif code == 0:
                # 登录 cookie 在"确认登录"这次响应的 Set-Cookie 里；
                # 只依赖 session 罐会漏（实测只拿到匿名 cookie），这里两处合并
                cookies = dict(resp.cookies)
                cookies.update({k: v for k, v in s.cookies.get_dict().items()
                                if k not in cookies})
                if "SESSDATA" not in cookies:
                    state.update(code="error",
                                 msg="❌ 登录响应里没有 SESSDATA（异常），服务退出")
                    return
                # 落盘前当场验证登录态
                nav = s.get("https://api.bilibili.com/x/web-interface/nav", timeout=15,
                            cookies={"SESSDATA": cookies["SESSDATA"]}).json()
                d = nav.get("data") or {}
                if not d.get("isLogin"):
                    state.update(code="error", msg="❌ cookie 验证未通过（nav 未登录），服务退出")
                    return
                COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
                exp = str(int(time.time() + 180 * 86400))  # 180 天，避免写成"立即过期"
                lines = ["# Netscape HTTP Cookie File（tools/bili_login.py 生成）"]
                for k, v in cookies.items():
                    lines.append(f".bilibili.com\tTRUE\t/\tTRUE\t{exp}\t{k}\t{v}")
                COOKIE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
                name = d.get("uname", "?")
                state.update(code="ok", cookie_count=len(cookies),
                             msg=f"✅ 已验证登录：{name}（{len(cookies)} 条 cookie），"
                                 f"已存 {COOKIE_FILE.name}，服务即将退出")
                threading.Timer(4, server.shutdown).start()
                return
            time.sleep(2)
    state.update(code="timeout",
                 msg="15 分钟未扫码，服务退出。重跑 python3 tools/bili_login.py 再试。")


PAGE = """<!doctype html><meta charset="utf-8"><title>B站扫码登录</title>
<body style="font-family:sans-serif;text-align:center;background:#f6f7f8">
<h2>健身教练 Agent · B 站登录</h2>
<div id="msg" style="font-size:16px;color:#444;margin:12px"></div>
<div id="qr"></div>
<script>
async function tick() {
  try {
    const r = await fetch('/status'); const s = await r.json();
    document.getElementById('msg').textContent = s.msg;
    if (s.svg && document.getElementById('qr').dataset.svg !== s.svg) {
      document.getElementById('qr').dataset.svg = s.svg;
      document.getElementById('qr').innerHTML = s.svg;
    }
  } catch (e) { document.getElementById('msg').textContent = '（服务已结束，可关闭页面）'; }
}
setInterval(tick, 1500); tick();
</script></body>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/status":
            self._send(200, json.dumps(state, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
        elif self.path == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")


def main() -> int:
    threading.Thread(target=poller, daemon=True).start()
    server = HTTPServer(("0.0.0.0", 8720), Handler)
    print("登录页：http://100.64.87.121:8720  （Windows 浏览器打开，手机 B 站 App 扫码）")
    print("       http://127.0.0.1:8720    （仅服务器本机可开）")
    print("登录成功或超时后本服务自动退出。Ctrl+C 可手动中止。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 130
    code = state.get("code")
    print(state["msg"], flush=True)
    return 0 if code == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
