"""WSGI entry for Web UI (5551)"""
import custom.patches  # noqa: F401 — 加载 KWiki 定制
from tools.web import create_web_app
from pathlib import Path

base = Path(__file__).parent
app = create_web_app(base)