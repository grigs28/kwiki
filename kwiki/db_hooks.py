"""kwiki/db_hooks.py — LLMBase 编译后自动写入 OpenGauss 数据库"""
import re
import logging
from pathlib import Path

from kwiki.db import insert_or_update_standard

logger = logging.getLogger("kwiki.db_hooks")

# 标准号提取正则（国标/行标/地标/团标，支持 /T 变体）
STD_CODE_RE = re.compile(
    r'((?:GB/Z?|JGJ|DL(?:/T)?|T/C|CJJ(?:/T)?|QX|CECS|JB|JG|JTJ|QB|WS)\s*\d+(?:[/\-\.]\d+)*)',
    re.IGNORECASE
)
LEVEL_MAP = {
    "GB/T": "国家标准", "GBZ": "国家标准", "GB": "国家标准",
    "JGJ": "行业标准", "DL/T": "电力行业标准", "DL": "电力行业标准",
    "T/C": "团体标准", "CJJ/T": "城建行业标准", "CJJ": "城建行业标准",
    "QB": "轻工行业标准", "JG": "建筑行业标准", "JB": "机械行业标准",
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
            if code_upper.startswith(prefix.upper()):
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
            specialties=specialties,
            types=types,
        )
        logger.info(f"[db_hooks] 已写入: {std_code} {title} specials={specials} types={types}")
    except Exception as e:
        logger.error(f"[db_hooks] on_compiled failed: {e}")


def on_ingested(source: str, title: str, path: str = "", **kw):
    """文档摄入后记录原始路径"""
    logger.info(f"[db_hooks] ingested: {title} -> {path}")