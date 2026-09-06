# -*- coding: utf-8 -*-
"""阶段 2：字段统一与清洗 —— 把三个来源的不同列名/格式归一到统一 schema。

核心思想：所有"脏"只处理一次，后续校验和入库看到的都是干净、统一的字段。
"""
import re
from datetime import datetime

import pandas as pd

# ---- 各来源的列名 -> 统一字段名 -------------------------------------------------
COLUMN_MAPPING = {
    "tmall": {
        "商品ID": "product_id", "商品标题": "title", "叶子类目": "category",
        "销售价(元)": "price", "可售库存": "stock", "店铺评分": "rating",
        "上架时间": "listed_date", "商品链接": "url",
    },
    "ops": {
        "产品id ": "product_id", " 标题": "title", "分类": "category",
        "价格": "price", "库存量": "stock", "评分": "rating",
        "上架日期": "listed_date", "链接": "url",
    },
    "competitor": {
        "item_id": "product_id", "title": "title", "cate": "category",
        "price": "price", "stock": "stock", "rate": "rating",
        "list_date": "listed_date", "url": "url",
    },
    "scrape": {
        "item_id": "product_id", "title": "title", "cate": "category",
        "price": "price", "stock": "stock", "rate": "rating",
        "list_date": "listed_date", "url": "url",
    },
}

UNIFIED_COLUMNS = [
    "product_id", "title", "category", "price",
    "stock", "rating", "listed_date", "url", "_source",
]

# ---- 类目别名归一表（先做基础清洗再查表）----------------------------------------
CATEGORY_ALIAS = {
    "女装": "女装", "女裝": "女装",
    "数码电子": "数码电子", "电子数码": "数码电子", "數碼電子": "数码电子", "3c": "数码电子",
    "家居日用": "家居日用", "日用家居": "家居日用", "家居": "家居日用",
    "美妆护肤": "美妆护肤", "护肤美妆": "美妆护肤", "美妆": "美妆护肤",
    "母婴育儿": "母婴育儿", "育儿母婴": "母婴育儿", "母婴": "母婴育儿",
    "食品生鲜": "食品生鲜", "生鲜食品": "食品生鲜", "食品": "食品生鲜",
}

UNKNOWN_CATEGORY = "其他"

DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%Y.%m.%d"]

# 统一后的类目清单（维度表依据）
VALID_CATEGORIES = sorted(set(CATEGORY_ALIAS.values()) - {UNKNOWN_CATEGORY}) + [UNKNOWN_CATEGORY]


def normalize_text(s):
    """全角空格/首尾空白清理。"""
    if pd.isna(s):
        return None
    return re.sub(r"[\s\u3000]+", "", str(s))


def normalize_category(s):
    """类目归一：清理空白 -> 小写（兼容 3C）-> 查别名表。"""
    s = normalize_text(s)
    if not s:
        return UNKNOWN_CATEGORY
    return CATEGORY_ALIAS.get(s.lower(), UNKNOWN_CATEGORY)


FULLWIDTH_TABLE = {c: chr(c - 0xFEE0) for c in range(0xFF01, 0xFF5F)}


def parse_price(s):
    """价格解析：容忍 ￥ 前缀、'xx元' 后缀、全角数字。返回 float 或 None。"""
    if pd.isna(s):
        return None
    # 全角转半角，并去掉千分位逗号
    s = str(s).translate(FULLWIDTH_TABLE).replace(",", "")
    m = re.search(r"(-?\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None


def parse_stock(s):
    """库存解析：容忍 '1200件' 之类的单位后缀。返回 int 或 None。"""
    if pd.isna(s):
        return None
    s = str(s).translate(FULLWIDTH_TABLE)
    m = re.search(r"(-?\d+)", s)
    return int(m.group(1)) if m else None


def parse_date(s):
    """多格式日期解析。缺失返回 ""（允许为空），有值但无法解析返回 None（校验拦截）。"""
    s = normalize_text(s)
    if not s:
        return ""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def transform(frames: dict) -> pd.DataFrame:
    """把多个来源的原始表统一成一张标准化长表。"""
    standardized = []
    for source, df in frames.items():
        mapping = COLUMN_MAPPING[source]
        df = df.rename(columns=mapping)
        # 统一字段做清洗
        df["product_id"] = df["product_id"].map(normalize_text)
        df["title"] = df["title"].map(normalize_text)
        df["category"] = df["category"].map(normalize_category)
        df["price"] = df["price"].map(parse_price)
        df["stock"] = df["stock"].map(parse_stock)
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
        df["listed_date"] = df["listed_date"].map(parse_date)
        df["url"] = df["url"].map(lambda s: normalize_text(s) if pd.notna(s) else None)
        standardized.append(df)

    combined = pd.concat(standardized, ignore_index=True)
    combined = combined[[c for c in UNIFIED_COLUMNS if c in combined.columns]]
    print(f"[统一] 三来源合并: {len(combined)} 行，统一为 {len(UNIFIED_COLUMNS)} 个标准字段")
    return combined


def dedup(df: pd.DataFrame):
    """按来源优先级去重：tmall > ops > competitor。返回 (去重后表, 重复行数)。"""
    priority = {"tmall": 0, "ops": 1, "competitor": 2}
    df = df.copy()
    df["_prio"] = df["_source"].map(priority)
    before = len(df)
    df = (
        df.sort_values("_prio")
        .drop_duplicates(subset="product_id", keep="first")
        .drop(columns="_prio")
    )
    dup_count = before - len(df)
    print(f"[去重] 移除重复商品 {dup_count} 行（保留来源优先级最高的一条）")
    return df, dup_count
