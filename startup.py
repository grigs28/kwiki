#!/usr/bin/env python3
"""KWiki 启动脚本：加载定制代码 + 启动 Web UI (5551) + Agent API (5552)"""
import sys, os, threading, logging, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("startup")

# ── 加载定制 ────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
try:
    import custom.patches
    print("[startup] custom.patches 加载成功")
except Exception as e:
    print(f"[startup] custom.patches 加载失败: {e}")
    import traceback; traceback.print_exc()

# ── 初始化数据库 ────────────────────────────────────
from kwiki.db import init_db
try:
    init_db()
    print("[startup] 数据库初始化成功")
except Exception as e:
    print(f"[startup] 数据库初始化失败（可能已存在）: {e}")

# ── 启动 Worker ─────────────────────────────────────
def run_worker():
    from tools.worker import start_worker_thread
    base = Path(__file__).parent
    t = start_worker_thread(base)
    if t:
        print("[startup] Worker 线程已启动")
    else:
        print("[startup] Worker 已禁用")

# ── 启动 Web UI (5551) ─────────────────────────────
def run_web():
    from werkzeug.serving import run_simple
    from tools.web import create_web_app

    base = Path(__file__).parent
    app = create_web_app(base)
    print("[startup] 启动 Web UI: 0.0.0.0:5551")
    run_simple("0.0.0.0", 5551, app, threaded=True, use_debugger=False, use_reloader=False)

# ── 启动 Agent API (5552) ─────────────────────────
def run_agent():
    from werkzeug.serving import run_simple
    from tools.agent_api import create_agent_server

    base = Path(__file__).parent
    app = create_agent_server(base, port=5552)
    print("[startup] 启动 Agent API: 0.0.0.0:5552")
    run_simple("0.0.0.0", 5552, app, threaded=True, use_debugger=False, use_reloader=False)

if __name__ == "__main__":
    # 先启动 Worker
    run_worker()

    # 同时启动两个服务
    t_web = threading.Thread(target=run_web, name="web-ui", daemon=True)
    t_web.start()
    print("[startup] Web UI 线程已启动")

    t_agent = threading.Thread(target=run_agent, name="agent-api", daemon=True)
    t_agent.start()
    print("[startup] Agent API 线程已启动")

    # 等待两个服务
    while t_web.is_alive() and t_agent.is_alive():
        time.sleep(10)