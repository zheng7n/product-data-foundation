# -*- coding: utf-8 -*-
"""阶段 1：批量读取 —— 扫描 data/raw/ 下所有 Excel 并读入内存。

真实场景里这一步对应：影刀 RPA 定时导出的运营表、后台导出、
竞品采集脚本输出等散落各处的文件，统一收口到管道入口。
"""
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"

# 文件名 -> 来源标签（来源同时是去重优先级依据，越靠前越可信）
SOURCES = {
    "天猫后台_商品导出.xlsx": "tmall",
    "运营手工维护表.xlsx": "ops",
    "竞品采集表.xlsx": "competitor",
    "网页采集表.xlsx": "scrape",
}


def extract_all() -> dict:
    """读取全部来源文件，返回 {来源标签: DataFrame}。"""
    frames = {}
    for filename, source in SOURCES.items():
        path = RAW_DIR / filename
        if not path.exists():
            print(f"[警告] 缺少来源文件，跳过: {filename}")
            continue
        df = pd.read_excel(path, dtype=str)  # 全部按字符串读入，避免 pandas 自动推断吃掉脏数据
        df["_source"] = source
        frames[source] = df
        print(f"[读取] {filename}: {len(df)} 行, {len(df.columns) - 1} 列")
    if not frames:
        raise FileNotFoundError(f"未找到任何来源文件，请先运行 scripts/generate_mock_data.py")
    return frames
