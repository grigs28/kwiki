#!/usr/bin/env python3
"""KWiki 启动脚本：加载定制代码 + 启动 Web UI (5551) + Agent API (5552)"""
import sys, os, threading
from pathlib import Path

# ── 加载定制 ────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
import custom.patches  # noqa: F401 — 触发 hook 注册

# ── 初始化数据库 ────────────────────────────────────
from kwiki.db import init_db
try:
    init_db()
except Exception as e:
    print(f"[startup] 数据库初始化失败（可能已存在）: {e}")

# ── 启动 Worker ─────────────────────────────────────
def run_worker():
    from tools.worker import start_worker_thread
    base = Path(__file__).parent
    start_worker_thread(base)

# ── 启动 Web UI (5551) ─────────────────────────────
def run_web():
    from tools.web import create_web_app
    from gunicorn.app.base import BaseApplication
    from gunicorn.config import Config

    base = Path(__file__).parent
    app = create_web_app(base)
    cfg = Config()
    cfg.set("bind", "0.0.0.0:5551")
    cfg.set("workers", 2)
    cfg.set("timeout", 300)
    cfg.set("chdir", str(base))
    cfg.set("errorlog", "-")
    BaseApplication(app, cfg).run()

# ── 启动 Agent API (5552) ─────────────────────────
def run_agent_api():
    from tools.agent_api import create_agent_server
    from gunicorn.app.base import BaseApplication
    from gunicorn.config import Config

    base = Path(__file__).parent
    app = create_agent_server(base, port=5552)
    cfg = Config()
    cfg.set("bind", "0.0.0.0:5552")
    cfg.set("workers", 1)
    cfg.set("timeout", 300)
    cfg.set("chdir", str(base))
    cfg.set("errorlog", "-")
    BaseApplication(app, cfg).run()

if __name__ == "__main__":
    print("[kwiki] 启动服务: Web=5551, AgentAPI=5552, Worker=enabled")

    t_worker = threading.Thread(target=run_worker, daemon=True)
    t_worker.start()

    t_web = threading.Thread(target=run_web, daemon=True)
    t_web.start()

    run_agent_api()  # 主线程跑 Agent API