"""WSGI entry for Agent API (5552)"""
import custom.patches  # noqa: F401 — 加载 KWiki 定制
from tools.agent_api import create_agent_server
from pathlib import Path

base = Path(__file__).parent
app = create_agent_server(base, port=5552)