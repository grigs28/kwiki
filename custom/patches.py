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