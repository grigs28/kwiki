# KWiki 工程设计标准查询知识库实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 LLMBase 深度定制，搭建内网工程设计标准查询知识库

**Architecture:** LLMBase 核心引擎（知识合成 + 自愈）+ OpenGauss 分类元数据 + Docker 单容器部署。Web UI 和 Agent API 分开端口（5551/5552），通过 hook 机制在编译后自动写入数据库。

**Tech Stack:** Python 3.11+, Flask, LLMBase (llmwiki), psycopg2 (OpenGauss), Docker

---

## 文件结构

```
/opt/yz/kwiki/
├── Dockerfile                          # 定制 Dockerfile（前端构建 + 双端口暴露）
├── docker-compose.yaml                 # 单服务 Docker Compose
├── .env                                # 环境变量（LLM + DB 密码）
├── config.yaml                         # LLMBase 配置
├── startup.py                          # 启动脚本（加载 custom + 启动双服务）
├── kwiki/
│   ├── __init__.py
│   ├── db.py                           # OpenGauss 连接与表操作
│   ├── db_hooks.py                     # compile 后写入数据库
│   └── taxonomy.py                     # 专业/类型分类注册（SECTION_HEADERS）
├── custom/
│   └── patches.py                      # LLMBase 定制（单语中文、分类）
└── docs/superpowers/plans/
    └── 2026-04-16-kwiki-implementation.md
```

---

## Task 1: 初始化项目结构

**Files:**
- Create: `kwiki/__init__.py`
- Create: `kwiki/db.py`
- Create: `kwiki/db_hooks.py`
- Create: `kwiki/taxonomy.py`
- Create: `custom/patches.py`
- Create: `.env`

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p /opt/yz/kwiki/kwiki /opt/yz/kwiki/custom /opt/yz/kwiki/raw /opt/yz/kwiki/wiki/_meta /opt/yz/kwiki/wiki/concepts /opt/yz/kwiki/wiki/outputs /opt/yz/kwiki/docs/superpowers/plans
touch /opt/yz/kwiki/kwiki/__init__.py
```

- [ ] **Step 2: 创建 .env 文件**

```bash
cat > /opt/yz/kwiki/.env << 'EOF'
# LLM 配置（内网优先，外网兜底）
LLMBASE_API_KEY=sk-内网LLM密钥
LLMBASE_BASE_URL=http://192.168.0.x/v1
LLMBASE_MODEL=内网模型名
LLMBASE_FALLBACK_MODELS=deepseek-chat,glm-4-flash
LLMBASE_PRIMARY_RETRIES=3
LLMBASE_FALLBACK_RETRIES=1

# 安全密钥
LLMBASE_API_SECRET=kwiki-admin-secret-change-me

# OpenGauss 数据库
KWIKI_DB_HOST=192.168.0.98
KWIKI_DB_PORT=5432
KWIKI_DB_NAME=kwiki
KWIKI_DB_USER=grigs
KWIKI_DB_PASSWORD=Slnwg123$
EOF
```

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "init: 项目结构和基础文件"
```

---

## Task 2: 数据库初始化

**Files:**
- Create: `kwiki/db.py`

- [ ] **Step 1: 编写 db.py**

```python
"""kwiki/db.py — OpenGauss 数据库操作"""
import os
from contextlib import contextmanager
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values

POOL = None  # 简单连接池（按需创建）


def get_connection():
    return psycopg2.connect(
        host=os.getenv("KWIKI_DB_HOST", "192.168.0.98"),
        port=int(os.getenv("KWIKI_DB_PORT", "5432")),
        dbname=os.getenv("KWIKI_DB_NAME", "kwiki"),
        user=os.getenv("KWIKI_DB_USER", "grigs"),
        password=os.getenv("KWIKI_DB_PASSWORD", ""),
    )


@contextmanager
def get_cursor():
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def init_db():
    """初始化数据库表（专业、类型、标准文档、关联表）"""
    with get_cursor() as cur:
        # 专业分类表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS specialty (
                code VARCHAR(20) PRIMARY KEY,
                name VARCHAR(50) NOT NULL,
                icon VARCHAR(10),
                sort_order INT DEFAULT 0
            )
        """)
        # 类型分类表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS std_type (
                code VARCHAR(20) PRIMARY KEY,
                name VARCHAR(50) NOT NULL,
                icon VARCHAR(10),
                sort_order INT DEFAULT 0
            )
        """)
        # 标准文档元数据表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS standard (
                id SERIAL PRIMARY KEY,
                std_code VARCHAR(50) NOT NULL UNIQUE,
                title VARCHAR(200) NOT NULL,
                level VARCHAR(10),
                status VARCHAR(10) DEFAULT '现行',
                published DATE,
                effective DATE,
                wiki_slug VARCHAR(100),
                raw_path VARCHAR(200),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # 关联表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS standard_specialty (
                standard_id INT REFERENCES standard(id) ON DELETE CASCADE,
                specialty_code VARCHAR(20) REFERENCES specialty(code) ON DELETE CASCADE,
                PRIMARY KEY (standard_id, specialty_code)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS standard_type (
                standard_id INT REFERENCES standard(id) ON DELETE CASCADE,
                type_code VARCHAR(20) REFERENCES std_type(code) ON DELETE CASCADE,
                PRIMARY KEY (standard_id, type_code)
            )
        """)


def insert_or_update_standard(std_code: str, title: str, wiki_slug: str = "", raw_path: str = "",
                               level: str = "", status: str = "现行",
                               specialties: list = None, types: list = None):
    """插入或更新标准文档"""
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO standard (std_code, title, wiki_slug, raw_path, level, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (std_code) DO UPDATE SET
                title = EXCLUDED.title,
                wiki_slug = EXCLUDED.wiki_slug,
                raw_path = EXCLUDED.raw_path,
                level = EXCLUDED.level,
                status = EXCLUDED.status,
                updated_at = NOW()
            RETURNING id
        """, (std_code, title, wiki_slug, raw_path, level, status))
        std_id = cur.fetchone()[0]
        # 清理旧关联
        cur.execute("DELETE FROM standard_specialty WHERE standard_id = %s", (std_id,))
        cur.execute("DELETE FROM standard_type WHERE standard_id = %s", (std_id,))
        # 写入新关联
        if specialties:
            for sc in specialties:
                cur.execute("""
                    INSERT INTO standard_specialty (standard_id, specialty_code)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                """, (std_id, sc))
        if types:
            for tc in types:
                cur.execute("""
                    INSERT INTO standard_type (standard_id, type_code)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                """, (std_id, tc))
        return std_id


def list_specialties() -> list[dict]:
    with get_cursor() as cur:
        cur.execute("SELECT code, name, icon, sort_order FROM specialty ORDER BY sort_order")
        return [{"code": r[0], "name": r[1], "icon": r[2], "sort_order": r[3]} for r in cur.fetchall()]


def list_std_types() -> list[dict]:
    with get_cursor() as cur:
        cur.execute("SELECT code, name, icon, sort_order FROM std_type ORDER BY sort_order")
        return [{"code": r[0], "name": r[1], "icon": r[2], "sort_order": r[3]} for r in cur.fetchall()]


def upsert_specialty(code: str, name: str, icon: str = "", sort_order: int = 0):
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO specialty (code, name, icon, sort_order)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, icon=EXCLUDED.icon, sort_order=EXCLUDED.sort_order
        """, (code, name, icon, sort_order))


def upsert_std_type(code: str, name: str, icon: str = "", sort_order: int = 0):
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO std_type (code, name, icon, sort_order)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, icon=EXCLUDED.icon, sort_order=EXCLUDED.sort_order
        """, (code, name, icon, sort_order))


def search_standards(query: str = "", specialty: str = None, type: str = None, limit: int = 20) -> list[dict]:
    """按查询条件搜索标准"""
    with get_cursor() as cur:
        sql = """
            SELECT DISTINCT s.id, s.std_code, s.title, s.level, s.status, s.wiki_slug
            FROM standard s
            LEFT JOIN standard_specialty ss ON s.id = ss.standard_id
            LEFT JOIN standard_type st ON s.id = st.standard_id
            WHERE (%s = '' OR s.title ILIKE %s OR s.std_code ILIKE %s)
        """
        params = [query, f"%{query}%", f"%{query}%"]
        if specialty:
            sql += " AND ss.specialty_code = %s"
            params.append(specialty)
        if type:
            sql += " AND st.type_code = %s"
            params.append(type)
        sql += " ORDER BY s.std_code LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        return [{"id": r[0], "std_code": r[1], "title": r[2], "level": r[3], "status": r[4], "wiki_slug": r[5]}
                for r in cur.fetchall()]
```

- [ ] **Step 2: 初始化数据库**

```bash
cd /opt/yz/kwiki && python3 -c "
from kwiki.db import init_db
init_db()
print('数据库初始化完成')
"
```

- [ ] **Step 3: 插入初始分类数据**

```bash
python3 -c "
from kwiki.db import upsert_specialty, upsert_std_type

# 专业
for code, name in [('arch','建筑'),('struct','结构'),('mech','给排水'),('hvac','暖通'),('elec','电气')]:
    upsert_specialty(code, name)

# 类型
for code, name in [('green','绿色建筑'),('fire','防火'),('general','通用规范'),('seismic','抗震'),('energy','节能')]:
    upsert_std_type(code, name)

print('初始数据插入完成')
"
```

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "feat: OpenGauss 数据库初始化和 db.py"
```

---

## Task 3: LLMBase 定制层（custom/patches.py）

**Files:**
- Modify: `custom/patches.py`

- [ ] **Step 1: 编写 custom/patches.py**

```python
"""custom/patches.py — LLMBase 深度定制（工程标准场景）"""
import os, sys
from pathlib import Path

# 确保 kwiki 包可导入
sys.path.insert(0, str(Path(__file__).parent.parent))

import tools.compile as c
import tools.query as q
from tools.hooks import register
from kwiki.db_hooks import on_compiled, on_ingested

# ── 语言定制：单语中文 ──────────────────────────────
c.SECTION_HEADERS = [("zh", "## 中文")]

# ── 编译 prompt 定制 ────────────────────────────────
c.SYSTEM_PROMPT = """你是一个工程标准知识库编译专家。你的任务是将工程设计标准文档编译成结构化的维基百科条目。

规则：
- 用中文撰写所有内容
- 用 [[wiki-link]] 语法标记交叉引用
- 在文档顶部写出简要摘要
- 按条文号组织内容（如 3.2.1、5.1.3）
- 保持事实准确，不虚构信息
- 使用 YAML frontmatter 存储元数据（title, tags, summary, sources）
- 发现标准间的交叉引用时建立链接

输出格式示例：
---
title: GB 50016-2014 建筑设计防火规范
tags: [建筑, 防火, 结构]
summary: 本规范适用于新建、扩建和改建建筑的设计防火...
sources:
  - plugin: manual
    title: GB 50016-2014
---

## 章节号 章节标题

条文内容...
"""

c.COMPILE_ARTICLE_FORMAT = """## 中文

以中文撰写完整内容，包括：
- 规范简介和适用范围
- 核心术语定义
- 主要条文内容（按章节组织）
- 与其他标准的交叉引用
"""

c.COMPILE_USER_PROMPT = """我有一份原始标准文档，标题为 "{title}"。

已有概念列表：
{existing}

请编译成维基百科条目，使用以下格式：
{article_format}

内容摘要（前500字）：
{content}

请提取关键概念和条文，建立标准间的交叉引用链接。"""

# ── 语气定制 ──────────────────────────────────────
q.TONE_INSTRUCTIONS["default"] = ""
q.TONE_INSTRUCTIONS["scholar"] = "请以学术风格回答，引用标准条文号，逻辑严谨。"
q.TONE_INSTRUCTIONS["wenyan"] = "请以古文风格回答，使用典雅文言。"
q.TONE_INSTRUCTIONS["eli5"] = "请用最简单直白的语言解释，适合非专业人员理解。"

# 移除不需要的语气
for key in ["caveman"]:
    q.TONE_INSTRUCTIONS.pop(key, None)

# ── 注册 hook ──────────────────────────────────────
register("compiled", on_compiled)
register("ingested", on_ingested)
```

- [ ] **Step 2: 提交**

```bash
git add custom/patches.py
git commit -m "feat: LLMBase 定制层（单语中文、工程标准场景）"
```

---

## Task 4: 数据库 Hook（编译后写入 DB）

**Files:**
- Create: `kwiki/db_hooks.py`

- [ ] **Step 1: 编写 kwiki/db_hooks.py**

```python
"""kwiki/db_hooks.py — LLMBase 编译后自动写入 OpenGauss 数据库"""
import re
import logging
from pathlib import Path

from kwiki.db import insert_or_update_standard

logger = logging.getLogger("kwiki.db_hooks")

# 标准号提取正则（国标/行标/地标/团标）
STD_CODE_RE = re.compile(
    r'((?:GB|JGJ|DL|T\C|CJJ|QX|GBZ|CECS|JB|JG|JTJ|QB|WS)\s*\d+(?:[/\-\.]\d+)*)',
    re.IGNORECASE
)
LEVEL_MAP = {
    "GB": "国家标准", "GB/T": "国家标准", "GBZ": "国家标准",
    "JGJ": "行业标准", "DL": "电力行业标准", "T/C": "团体标准",
    "CJJ": "城建行业标准", "QB": "轻工行业标准",
    "JG": "建筑行业标准", "JB": "机械行业标准",
}
TYPE_TAGS = {
    "绿建": ["green"], "绿色建筑": ["green"], "节能": ["energy"],
    "防火": ["fire"], "消防": ["fire"], "抗震": ["seismic"],
    "抗震设计": ["seismic"], "通用": ["general"],
    "建筑": ["arch"], "结构": ["struct"], "给排水": ["mech"],
    "暖通": ["hvac"], "电气": ["elec"], "智能化": ["elec"],
    "设计": ["general"], "施工": ["general"], "验收": ["general"],
}


def parse_std_code(title: str) -> tuple[str, str]:
    """从标题解析标准号和级别"""
    match = STD_CODE_RE.search(title)
    if match:
        code = match.group(1).strip().replace(" ", "")
        code_upper = code.upper()
        for prefix, level in LEVEL_MAP.items():
            if code_upper.startswith(prefix.replace("/T", "/t").replace("GB", "GB")):
                return code, level
        return code, ""
    return "", ""


def infer_tags(title: str, content: str = "") -> tuple[list, list]:
    """从标题/内容推断专业和类型标签"""
    text = title + " " + (content[:2000] if content else "")
    specialties, types = set(), set()
    for keyword, tags in TYPE_TAGS.items():
        if keyword in text:
            if keyword in ("建筑", "建筑设计"): specialties.add("arch")
            elif keyword in ("结构", "钢结构", "混凝土"): specialties.add("struct")
            elif keyword in ("给排水", "消防给水"): specialties.add("mech")
            elif keyword in ("暖通", "空调", "通风"): specialties.add("hvac")
            elif keyword in ("电气", "供配电", "照明"): specialties.add("elec")
            elif keyword in ("绿建", "绿色建筑"): types.add("green")
            elif keyword in ("防火", "消防"): types.add("fire")
            elif keyword in ("节能", "能耗"): types.add("energy")
            elif keyword in ("抗震", "地震"): types.add("seismic")
            elif keyword in ("通用", "基本规定"): types.add("general")
    return sorted(specialties), sorted(types)


def on_compiled(source: str, title: str, work_id: str = "", raw_type: str = "", **kw):
    """编译完成后写入数据库"""
    try:
        std_code, level = parse_std_code(title)
        if not std_code:
            logger.warning(f"[db_hooks] 无法解析标准号 from title: {title}")
            return
        specials, types = infer_tags(title)
        slug = work_id or std_code.lower().replace(" ", "-").replace("/", "-")
        wiki_slug = f"wiki/concepts/{slug}"
        insert_or_update_standard(
            std_code=std_code,
            title=title,
            wiki_slug=wiki_slug,
            level=level,
            status="现行",
            specialties=specials,
            types=types,
        )
        logger.info(f"[db_hooks] 已写入: {std_code} {title} specials={specials} types={types}")
    except Exception as e:
        logger.error(f"[db_hooks] on_compiled failed: {e}")


def on_ingested(source: str, title: str, path: str = "", **kw):
    """文档摄入后记录原始路径"""
    logger.info(f"[db_hooks] ingested: {title} -> {path}")
```

- [ ] **Step 2: 提交**

```bash
git add kwiki/db_hooks.py kwiki/taxonomy.py 2>/dev/null || true
git commit -m "feat: 数据库 hook（编译后自动写入元数据）"
```

---

## Task 5: 启动脚本（startup.py）

**Files:**
- Create: `startup.py`

- [ ] **Step 1: 编写 startup.py**

```python
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

# ── 启动 Web UI (5551) ─────────────────────────────
from tools.web import create_web_app
from gunicorn.app.base import BaseApplication
from gunicorn.config import Config

base = Path(__file__).parent

def run_web():
    app = create_web_app(base)
    cfg = Config()
    cfg.set("bind", "0.0.0.0:5551")
    cfg.set("workers", 2)
    cfg.set("timeout", 300)
    cfg.set("chdir", str(base))
    cfg.set("accesslog", "-")
    cfg.set("errorlog", "-")
    BaseApplication(app, cfg).run()

# ── 启动 Agent API (5552) ─────────────────────────
def run_agent_api():
    from tools.agent_api import create_agent_server
    from gunicorn.app.base import BaseApplication
    from gunicorn.config import Config

    app = create_agent_server(base, port=5552)
    cfg = Config()
    cfg.set("bind", "0.0.0.0:5552")
    cfg.set("workers", 1)
    cfg.set("timeout", 300)
    cfg.set("chdir", str(base))
    cfg.set("accesslog", "-")
    cfg.set("errorlog", "-")
    BaseApplication(app, cfg).run()

# ── 启动 Worker ─────────────────────────────────────
def run_worker():
    from tools.worker import start_worker_thread
    start_worker_thread(base)

if __name__ == "__main__":
    print("[kwiki] 启动服务: Web=5551, AgentAPI=5552, Worker=enabled")

    t_worker = threading.Thread(target=run_worker, daemon=True)
    t_worker.start()

    t_web = threading.Thread(target=run_web, daemon=True)
    t_web.start()

    run_agent_api()  # 主线程跑 Agent API
```

- [ ] **Step 2: 提交**

```bash
git add startup.py
git commit -m "feat: 启动脚本（加载定制 + 启动双服务 + Worker）"
```

---

## Task 6: Docker 构建文件

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yaml`
- Create: `config.yaml`

- [ ] **Step 1: 编写 Dockerfile**

```dockerfile
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY --from=ghcr.io/hosuke/llmbase:latest /app/frontend/package.json /app/frontend/package-lock.json* ./
RUN npm ci || (cp package-lock.json* /tmp/ && npm ci --prefix /tmp/fallback)
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npx vite build

FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn psycopg2-binary

COPY tools/ ./tools/
COPY config.yaml pyproject.toml llmbase.py ./
COPY kwiki/ ./kwiki/
COPY custom/ ./custom/
COPY startup.py ./

RUN pip install --no-cache-dir -e .

COPY --from=frontend-build /app/static/dist ./static/dist

RUN mkdir -p raw wiki/_meta wiki/concepts wiki/outputs

# Web UI
EXPOSE 5551
# Agent API
EXPOSE 5552

CMD ["python", "startup.py"]
```

> 简化版 Dockerfile（克隆 LLMBase 源码构建）：

```dockerfile
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
RUN npm install -g pnpm
COPY --from=hosuke/llmbase:latest /app/frontend/package*.json ./
RUN pnpm install
COPY --from=hosuke/llmbase:latest /app/frontend/ ./
RUN pnpm build

FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn psycopg2-binary

# 克隆 LLMBase 源码
RUN git clone https://github.com/Hosuke/llmbase.git /tmp/llmbase \
    && cp -r /tmp/llmbase/tools /app/ \
    && cp /tmp/llmbase/{llmbase.py,config.yaml,pyproject.toml} /app/ \
    && rm -rf /tmp/llmbase

COPY kwiki/ ./kwiki/
COPY custom/ ./custom/
COPY startup.py .

RUN mkdir -p raw wiki/_meta wiki/concepts wiki/outputs
RUN mkdir -p /root/.config/llmbase
RUN echo 'LLMBASE_API_KEY=sk-placeholder\nLLMBASE_BASE_URL=http://localhost/v1\nLLMBASE_MODEL=gpt-4o' > /root/.config/llmbase/.env

EXPOSE 5551 5552

CMD ["python", "startup.py"]
```

- [ ] **Step 2: 编写 config.yaml**

```yaml
llm:
  max_tokens: 16384

paths:
  raw: "./raw"
  wiki: "./wiki"
  outputs: "./wiki/outputs"
  meta: "./wiki/_meta"
  concepts: "./wiki/concepts"

compile:
  batch_size: 5
  backlinks: true

worker:
  enabled: true
  learn_interval_hours: 0
  compile_interval_hours: 1
  taxonomy_interval_hours: 12
  health_check_interval_hours: 24
  learn_batch_size: 5
  learn_source: none

health:
  auto_fix_broken_links: true
  max_stubs_per_run: 10

lint:
  web_search: false
```

- [ ] **Step 3: 编写 docker-compose.yaml**

```yaml
services:
  kwiki:
    build: .
    container_name: kwiki
    ports:
      - "5551:5551"
      - "5552:5552"
    volumes:
      - ./raw:/app/raw
      - ./wiki:/app/wiki
      - ./config.yaml:/app/config.yaml
      - ./custom:/app/custom
    env_file:
      - .env
    environment:
      - KWIKI_DB_HOST=${KWIKI_DB_HOST}
      - KWIKI_DB_PORT=${KWIKI_DB_PORT}
      - KWIKI_DB_NAME=${KWIKI_DB_NAME}
      - KWIKI_DB_USER=${KWIKI_DB_USER}
      - KWIKI_DB_PASSWORD=${KWIKI_DB_PASSWORD}
    restart: unless-stopped
```

- [ ] **Step 4: 提交**

```bash
git add Dockerfile docker-compose.yaml config.yaml
git commit -m "feat: Docker 构建文件（双端口 5551/5552）"
```

---

## Task 7: 首次构建与验证

- [ ] **Step 1: 构建 Docker 镜像**

```bash
cd /opt/yz/kwiki && docker compose build
```

- [ ] **Step 2: 启动服务**

```bash
docker compose up -d && sleep 5 && docker compose logs -f
```

- [ ] **Step 3: 验证端口**

```bash
ss -tlnp | grep -E '5551|5552'
```

期望输出：
```
LISTEN 0  4096  0.0.0.0:5551  ...
LISTEN 0  4096  0.0.0.0:5552  ...
```

- [ ] **Step 4: 验证 Web UI**

```bash
curl -s http://localhost:5551/api/healthz
```

期望输出：`{"status":"ok"}`

- [ ] **Step 5: 验证 Agent API**

```bash
curl -s http://localhost:5552/api/articles
```

期望输出：`{"articles":[]}`

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "feat: 首次构建验证通过"
git push origin master
```

---

## Task 8: 提交 GitHub

- [ ] **Step 1: Push 到 GitHub**

```bash
git branch -M main
git push -u origin main
```

---

## 实施顺序

1. **Task 1** → 初始化项目结构
2. **Task 2** → 数据库初始化
3. **Task 3** → LLMBase 定制层
4. **Task 4** → 数据库 Hook
5. **Task 5** → 启动脚本
6. **Task 6** → Docker 构建文件
7. **Task 7** → 首次构建与验证
8. **Task 8** → 提交 GitHub