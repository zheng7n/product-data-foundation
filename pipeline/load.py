# -*- coding: utf-8 -*-
"""阶段 4：建表入库 —— 商品基础数据表（SQLite 演示，DDL 兼容 MySQL 习惯）。

表设计对应"商品基础数据底座"：
- category 维度表：类目统一后单独建表，商品表只存外键
- product 主表：业务主键 = 平台商品ID，带 CHECK 约束兜底，管道可重复执行（幂等）

MySQL 迁移说明：INTEGER PRIMARY KEY AUTOINCREMENT -> INT AUTO_INCREMENT PRIMARY KEY，
TEXT -> VARCHAR(n)，REAL -> DECIMAL(10,2)，并加 ENGINE=InnoDB DEFAULT CHARSET=utf8mb4。
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent.parent / "output" / "product_db.sqlite"

DDL = """
CREATE TABLE IF NOT EXISTS category (
    category_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS product (
    product_id  TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES category(category_id),
    price       REAL    NOT NULL CHECK (price > 0 AND price <= 10000),
    stock       INTEGER NOT NULL CHECK (stock >= 0),
    rating      REAL,
    listed_date TEXT,
    url         TEXT,
    source      TEXT,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_product_category    ON product(category_id);
CREATE INDEX IF NOT EXISTS idx_product_listed_date ON product(listed_date);

CREATE TABLE IF NOT EXISTS pipeline_run (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at        TEXT NOT NULL,
    source_rows   INTEGER,
    dedup_removed INTEGER,
    passed_rows   INTEGER,
    quarantined   INTEGER,
    loaded_total  INTEGER,
    duration_ms   INTEGER,
    status        TEXT NOT NULL DEFAULT 'success'
);
"""


def load(passed: pd.DataFrame, categories: list, db_path: Path = DB_PATH) -> dict:
    """建表并把校验通过的商品写入数据库。全量 REPLACE，管道可幂等重跑。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    try:
        conn.executescript(DDL)

        # 维度表：INSERT OR IGNORE 保证幂等
        conn.executemany(
            "INSERT OR IGNORE INTO category (category_name) VALUES (?)",
            [(c,) for c in categories],
        )
        cate_ids = dict(
            conn.execute("SELECT category_name, category_id FROM category").fetchall()
        )

        # itertuples 会改名下划线开头的列，先统一重命名
        records_df = passed.rename(columns={"_source": "source"})
        rows = [
            (
                r.product_id, r.title, cate_ids.get(r.category), r.price, r.stock,
                None if pd.isna(r.rating) else float(r.rating),
                r.listed_date or None,  # 缺失日期入库为 NULL，仅非法格式会在校验层拦截
                r.url, r.source, now,
            )
            for r in records_df.itertuples()
        ]
        conn.executemany(
            """INSERT OR REPLACE INTO product
               (product_id, title, category_id, price, stock,
                rating, listed_date, url, source, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        n_cate = conn.execute("SELECT COUNT(*) FROM category").fetchone()[0]
        n_prod = conn.execute("SELECT COUNT(*) FROM product").fetchone()[0]
        print(f"[入库] 商品主表 {n_prod} 行，类目维度表 {n_cate} 行 -> {db_path.name}")
        return {"products": n_prod, "categories": n_cate}
    finally:
        conn.close()


def log_run(stats: dict, db_path: Path = DB_PATH):
    """把一次管道执行的统计写入 pipeline_run 表（可观测性）。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO pipeline_run
               (ran_at, source_rows, dedup_removed, passed_rows,
                quarantined, loaded_total, duration_ms, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                stats.get("ran_at"), stats.get("source_rows"),
                stats.get("dedup_removed"), stats.get("passed_rows"),
                stats.get("quarantined"), stats.get("loaded_total"),
                stats.get("duration_ms"), stats.get("status", "success"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
