"""
CIOSH 情报雷达 · 数据库模块
提供建表函数和连接函数，不做任何业务逻辑。
"""

import sqlite3
from pathlib import Path

from config import get_config


def get_db() -> sqlite3.Connection:
    """返回带 Row 工厂的数据库连接（调用方负责关闭）。"""
    cfg = get_config()
    cfg.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cfg.DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """建表（幂等，已存在则跳过）。"""
    conn = get_db()
    conn.executescript("""
        -- 情报条目（核心表）
        CREATE TABLE IF NOT EXISTS intel_items (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            title            TEXT    NOT NULL,
            url              TEXT    UNIQUE,
            snippet          TEXT,
            source_name      TEXT,
            pub_date         TEXT,
            collected_at     TEXT    NOT NULL,
            source_keyword   TEXT,
            source_channel   TEXT    DEFAULT 'tavily',
            layer2_score     REAL    DEFAULT 0,
            is_analyzed      INTEGER DEFAULT 0,
            is_duplicate     INTEGER DEFAULT 0,
            category         TEXT,
            priority         TEXT,
            ciosh_relevance  TEXT,
            ciosh_action     TEXT,
            summary_zh       TEXT,
            keywords_json    TEXT,
            analyzed_at      TEXT,
            source_type      TEXT    DEFAULT 'daily'
        );

        -- URL 指纹表（Layer1 去重）
        CREATE TABLE IF NOT EXISTS seen_urls (
            url_hash   TEXT PRIMARY KEY,
            url        TEXT,
            first_seen TEXT NOT NULL
        );

        -- 日报 / 周报记录
        CREATE TABLE IF NOT EXISTS reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT    NOT NULL,
            report_type TEXT    DEFAULT 'daily',
            title_zh    TEXT,
            html_body   TEXT,
            sent_at     TEXT,
            item_count  INTEGER DEFAULT 0
        );

        -- 关键词周快照（便于回溯进化历史）
        CREATE TABLE IF NOT EXISTS keyword_snapshots (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            week_label    TEXT    NOT NULL,
            snapshot_json TEXT    NOT NULL,
            created_at    TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_intel_collected_at  ON intel_items(collected_at);
        CREATE INDEX IF NOT EXISTS idx_intel_priority      ON intel_items(priority);
        CREATE INDEX IF NOT EXISTS idx_intel_category      ON intel_items(category);
        CREATE INDEX IF NOT EXISTS idx_intel_source_kw     ON intel_items(source_keyword);
        CREATE INDEX IF NOT EXISTS idx_reports_date        ON reports(report_date);
    """)
    # Migration: add source_channel to existing tables that predate this column
    try:
        conn.execute("ALTER TABLE intel_items ADD COLUMN source_channel TEXT DEFAULT 'tavily'")
        conn.commit()
    except Exception:
        pass  # column already exists
    conn.close()


if __name__ == "__main__":
    init_db()
    print("数据库初始化完成：", get_config().DB_PATH)
