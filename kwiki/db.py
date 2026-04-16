"""kwiki/db.py — OpenGauss 数据库操作"""
import os
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

from dotenv import load_dotenv

# 加载 .env（查找项目根目录）
_load_done = False
for _p in [Path(__file__).parent.parent, Path.cwd()]:
    _env = _p / ".env"
    if _env.exists():
        load_dotenv(_env, override=True)
        _load_done = True
        break

import psycopg2

POOL = None  # 简单连接池（按需创建）


def get_connection():
    return psycopg2.connect(
        host=os.getenv("KWIKI_DB_HOST", "192.168.0.98"),
        port=int(os.getenv("KWIKI_DB_PORT", "5432")),
        dbname=os.getenv("KWIKI_DB_NAME", "kwiki"),
        user=os.getenv("KWIKI_DB_USER", "grigs"),
        password=os.getenv("KWIKI_DB_PASSWORD", ""),
        connect_timeout=5,
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
            MERGE INTO standard AS target
            USING (VALUES (%s, %s, %s, %s, %s, %s)) AS source(std_code, title, wiki_slug, raw_path, level, status)
            ON target.std_code = source.std_code
            WHEN MATCHED THEN UPDATE SET
                title = source.title, wiki_slug = source.wiki_slug, raw_path = source.raw_path,
                level = source.level, status = source.status, updated_at = NOW()
            WHEN NOT MATCHED THEN INSERT (std_code, title, wiki_slug, raw_path, level, status)
                VALUES (source.std_code, source.title, source.wiki_slug, source.raw_path, source.level, source.status)
        """, (std_code, title, wiki_slug, raw_path, level, status))
        cur.execute("SELECT id FROM standard WHERE std_code = %s", (std_code,))
        std_id = cur.fetchone()[0]
        # 清理旧关联
        cur.execute("DELETE FROM standard_specialty WHERE standard_id = %s", (std_id,))
        cur.execute("DELETE FROM standard_type WHERE standard_id = %s", (std_id,))
        # 写入新关联
        if specialties:
            for sc in specialties:
                cur.execute("""
                    MERGE INTO standard_specialty AS target
                    USING (VALUES (%s, %s)) AS source(standard_id, specialty_code)
                    ON target.standard_id = source.standard_id AND target.specialty_code = source.specialty_code
                    WHEN NOT MATCHED THEN INSERT (standard_id, specialty_code) VALUES (source.standard_id, source.specialty_code)
                """, (std_id, sc))
        if types:
            for tc in types:
                cur.execute("""
                    MERGE INTO standard_type AS target
                    USING (VALUES (%s, %s)) AS source(standard_id, type_code)
                    ON target.standard_id = source.standard_id AND target.type_code = source.type_code
                    WHEN NOT MATCHED THEN INSERT (standard_id, type_code) VALUES (source.standard_id, source.type_code)
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
            MERGE INTO specialty AS target
            USING (VALUES (%s, %s, %s, %s)) AS source(code, name, icon, sort_order)
            ON target.code = source.code
            WHEN MATCHED THEN UPDATE SET name=source.name, icon=source.icon, sort_order=source.sort_order
            WHEN NOT MATCHED THEN INSERT (code, name, icon, sort_order) VALUES (source.code, source.name, source.icon, source.sort_order)
        """, (code, name, icon, sort_order))


def upsert_std_type(code: str, name: str, icon: str = "", sort_order: int = 0):
    with get_cursor() as cur:
        cur.execute("""
            MERGE INTO std_type AS target
            USING (VALUES (%s, %s, %s, %s)) AS source(code, name, icon, sort_order)
            ON target.code = source.code
            WHEN MATCHED THEN UPDATE SET name=source.name, icon=source.icon, sort_order=source.sort_order
            WHEN NOT MATCHED THEN INSERT (code, name, icon, sort_order) VALUES (source.code, source.name, source.icon, source.sort_order)
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