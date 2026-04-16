# KWiki - 工程设计标准查询知识库设计文档

> 日期：2026-04-16
> 状态：已确认

## 1. 项目概述

基于 LLMBase (llmwiki) 深度定制，搭建内网工程设计标准查询知识库。涵盖国标 GB、行业标准（JGJ、DL/T 等）、设计规范条文的智能查询。

### 目标用户

- **查阅用户**：通过 Web / API / AI Agent 查询标准条文
- **管理员**：负责文档导入、分类管理、系统维护

### 核心价值

- LLM 合成知识（非简单向量存储），自动发现标准条文间交叉引用
- 双层召回：编译后概念给概要，原文兜底查精确条款
- 自愈机制：自动修复断链、合并重复、整理分类

## 2. 系统架构

```
┌─────────────────────────────────────────────────┐
│                    客户端层                       │
│   Web UI (5551)  │  HTTP API (5552)  │   MCP     │
└────────┬─────────┴────────┬──────────┴────┬─────┘
         │                  │               │
┌────────▼──────────────────▼───────────────▼─────┐
│              LLMBase 核心引擎                     │
│  tools/operations.py (统一操作注册表)              │
│  ├─ ingest    — 导入 PDF/Word/MD 标准文档          │
│  ├─ compile   — LLM 合成结构化 Wiki 条目           │
│  ├─ query     — 标准条文智能查询                    │
│  ├─ lint      — 自愈：断链/重复/分类修复            │
│  └─ export    — 标准文档导出                        │
└────────┬────────────────────────────────────────┘
         │                           │
┌────────▼──────────┐   ┌───────────▼──────────────┐
│     文件存储       │   │    OpenGauss 数据库        │
│ raw/  — 原始文档   │   │ 192.168.0.98:5432         │
│ wiki/ — 编译文章   │   │ 专业/类型分类元数据        │
└───────────────────┘   └──────────────────────────┘
         │
┌────────▼─────────────────────────────────────────┐
│                LLM 服务                            │
│  内网 LLM (优先) ──→ 外网 API (自动降级)            │
└──────────────────────────────────────────────────┘
```

## 3. 部署方案

### 端口分配

| 端口 | 用途 |
|------|------|
| 5551 | Web UI |
| 5552 | Agent API (HTTP + MCP) |

### 目录结构

```
/opt/yz/kwiki/
├── docker-compose.yaml
├── Dockerfile
├── .env                          # LLM 密钥、数据库密码等
├── config.yaml                   # LLMBase 站点配置
├── custom/                       # 定制代码（挂载进容器）
│   ├── hooks.py                  # 编译后回调：写入数据库
│   └── taxonomy.py               # 分类体系定制
├── raw/                          # 原始标准文档（持久化）
├── wiki/                         # 编译后 Wiki（持久化）
└── docs/
    └── superpowers/specs/        # 设计文档
```

### Docker Compose

```yaml
services:
  kwiki:
    build: .
    container_name: kwiki
    ports:
      - "5551:5551"     # Web UI
      - "5552:5552"     # Agent API
    volumes:
      - ./raw:/app/raw
      - ./wiki:/app/wiki
      - ./config.yaml:/app/config.yaml
      - ./custom:/app/custom
    environment:
      - LLMBASE_API_KEY=${LLM_API_KEY}
      - LLMBASE_BASE_URL=${LLM_BASE_URL}
      - LLMBASE_MODEL=${LLM_MODEL}
      - LLMBASE_FALLBACK_MODELS=${LLM_FALLBACK_MODELS}
      - KWIKI_DB_HOST=192.168.0.98
      - KWIKI_DB_PORT=5432
      - KWIKI_DB_NAME=kwiki
      - KWIKI_DB_USER=grigs
      - KWIKI_DB_PASSWORD=${DB_PASSWORD}
    restart: unless-stopped
```

- OpenGauss 不进容器，直连 `192.168.0.98:5432` 已有实例
- raw/ 和 wiki/ 挂载宿主机，容器重建不丢数据
- custom/ 挂载定制代码，改了重启即生效
- gunicorn 生产入口，Worker 自动启动

## 4. 数据库设计

连接：OpenGauss `192.168.0.98:5432`，用户 `grigs`，库 `kwiki`。

### 专业分类表

```sql
CREATE TABLE specialty (
    code        VARCHAR(20) PRIMARY KEY,
    name        VARCHAR(50) NOT NULL,
    icon        VARCHAR(10),
    sort_order  INT DEFAULT 0
);
```

### 类型分类表

```sql
CREATE TABLE std_type (
    code        VARCHAR(20) PRIMARY KEY,
    name        VARCHAR(50) NOT NULL,
    icon        VARCHAR(10),
    sort_order  INT DEFAULT 0
);
```

### 标准文档元数据表

```sql
CREATE TABLE standard (
    id          SERIAL PRIMARY KEY,
    std_code    VARCHAR(50) NOT NULL UNIQUE,
    title       VARCHAR(200) NOT NULL,
    level       VARCHAR(10),               -- 国标/行标/地标/团标
    status      VARCHAR(10) DEFAULT '现行',
    published   DATE,
    effective   DATE,
    wiki_slug   VARCHAR(100),
    raw_path    VARCHAR(200),
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);
```

### 关联表（多对多）

```sql
CREATE TABLE standard_specialty (
    standard_id    INT REFERENCES standard(id),
    specialty_code VARCHAR(20) REFERENCES specialty(code),
    PRIMARY KEY (standard_id, specialty_code)
);

CREATE TABLE standard_type (
    standard_id INT REFERENCES standard(id),
    type_code   VARCHAR(20) REFERENCES std_type(code),
    PRIMARY KEY (standard_id, type_code)
);
```

### 初始数据

| specialty.code | name |
|---|---|
| arch | 建筑 |
| struct | 结构 |
| mech | 给排水 |
| hvac | 暖通 |
| elec | 电气 |

| std_type.code | name |
|---|---|
| green | 绿色建筑 |
| fire | 防火 |
| general | 通用规范 |
| seismic | 抗震 |
| energy | 节能 |

管理员可通过 Web 界面增删改分类。

## 5. 定制层

### 语言：单语中文

```python
# custom/taxonomy.py
import tools.compile as c
c.SECTION_HEADERS = [("zh", "## 中文")]
```

### 编译后写入数据库

```python
# custom/hooks.py
from tools.hooks import register

@register("compiled")
def on_compiled(source, title, **kw):
    # 1. 解析标准编号（如 GB 50016-2014）
    # 2. LLM 建议专业/类型标签
    # 3. 写入 OpenGauss standard 表 + 关联表
```

### LLM 降级链

```yaml
# config.yaml
llm:
  primary:
    base_url: "http://内网LLM地址/v1"
    model: "内网模型名"
  fallback:
    base_url: "https://外网API地址/v1"
    model: "外网模型名"
```

内网不可用时自动切外网。

## 6. 管理员工作流

```
上传文档 → LLM 编译 → 分类标注 → 写入数据库 → 用户可查阅
                ↑                           │
                └── 自愈 Worker 定期维护 ←───┘
```

1. **导入**：Web 上传或 CLI `llmbase ingest pdf ./标准.pdf`
2. **编译**：LLM 自动提取条文、生成 Wiki 文章
3. **分类**：LLM 建议标签，管理员确认或修正
4. **维护**：`llmbase lint heal` 自动修复断链、合并重复

## 7. 查询接口

```
GET /api/search?q=防火分区面积&specialty=arch&type=fire
→ 数据库按专业/类型筛选标准范围
→ TF-IDF 检索 + LLM 问答
→ 返回条文摘要 + 原文出处
```

MCP 工具：`kb_search`、`kb_search_raw`、`kb_ask`、`kb_get`、`kb_list`、`kb_taxonomy`、`kb_stats`。

## 8. 边界与限制

- 不做用户权限系统，利用 LLMBase 自带 `API_SECRET` 区分读写
- 不做全文在线阅读器，重点在智能查询
- 不做标准自动更新抓取，管理员手动导入
- 不部署向量数据库，LLMBase 使用 TF-IDF + Markdown 存储
