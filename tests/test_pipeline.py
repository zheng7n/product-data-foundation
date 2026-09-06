# -*- coding: utf-8 -*-
"""清洗函数与校验规则的单元测试。"""
import pandas as pd
import pytest

from transform import (
    dedup,
    normalize_category,
    normalize_text,
    parse_date,
    parse_price,
    parse_stock,
)
from validate import validate


# ---------------- 容错解析 ----------------
@pytest.mark.parametrize(
    "raw,expect",
    [
        ("￥89.9", 89.9),        # 人民币符号前缀
        ("89.90元", 89.9),       # 元后缀
        ("１００", 100.0),       # 全角数字
        ("1,299.00", 1299.0),    # 千分位
        (-89.9, -89.9),          # 负数必须保留符号（由校验层拦截）
        ("abc", None),
        (None, None),
    ],
)
def test_parse_price(raw, expect):
    assert parse_price(raw) == expect


@pytest.mark.parametrize(
    "raw,expect",
    [("1200件", 1200), ("１０", 10), (-5, -5), ("", None), (None, None)],
)
def test_parse_stock(raw, expect):
    assert parse_stock(raw) == expect


@pytest.mark.parametrize(
    "raw,expect",
    [
        ("2025-03-01", "2025-03-01"),
        ("2025/3/1", "2025-03-01"),
        ("2025年3月1日", "2025-03-01"),
        ("2025.03.01", "2025-03-01"),
        ("", ""),          # 缺失放行
        (None, ""),
        ("2025/13/01", None),  # 非法拦截
        ("not a date", None),
    ],
)
def test_parse_date(raw, expect):
    assert parse_date(raw) == expect


# ---------------- 文本与类目归一 ----------------
@pytest.mark.parametrize(
    "raw,expect",
    [
        ("\u3000商品名\u3000", "商品名"),  # 全角空格
        ("  标题  ", "标题"),
        (None, None),
    ],
)
def test_normalize_text(raw, expect):
    assert normalize_text(raw) == expect


@pytest.mark.parametrize(
    "raw,expect",
    [
        ("數碼電子", "数码电子"),  # 繁体
        ("3C", "数码电子"),        # 简称
        (" 电子数码 ", "数码电子"),  # 别名 + 空白
        ("图书", "其他"),           # 未登记类目兜底
        (None, "其他"),
    ],
)
def test_normalize_category(raw, expect):
    assert normalize_category(raw) == expect


# ---------------- 去重优先级 ----------------
def test_dedup_keeps_highest_priority_source():
    df = pd.DataFrame(
        [
            {"product_id": "P1", "title": "竞品版", "_source": "competitor"},
            {"product_id": "P1", "title": "后台版", "_source": "tmall"},
            {"product_id": "P2", "title": "手工版", "_source": "ops"},
        ]
    )
    result, dup_count = dedup(df)
    assert dup_count == 1
    row = result[result["product_id"] == "P1"].iloc[0]
    assert row["title"] == "后台版"  # 来源可信度：tmall > competitor


# ---------------- 校验规则 ----------------
def base_row(**overrides):
    row = {
        "product_id": "P900",
        "title": "正常商品",
        "category": "数码电子",
        "price": 99.0,
        "stock": 10,
        "rating": 4.5,
        "listed_date": "2025-01-01",
        "url": "https://item.tmall.com/item.htm?id=P900",
        "_source": "tmall",
    }
    row.update(overrides)
    return row


def _quarantine_rules(rows):
    _, quarantined = validate(pd.DataFrame(rows))
    return dict(zip(quarantined["product_id"], quarantined["rule_hit"])) if len(quarantined) else {}


def test_validate_passes_clean_row():
    assert _quarantine_rules([base_row()]) == {}


@pytest.mark.parametrize(
    "field,value,rule_frag",
    [
        ("price", 0, "价格"),        # 越界下界
        ("price", 10001, "价格"),    # 越界上界
        ("price", None, "价格"),     # 缺失
        ("price", -50, "价格"),      # 负数（依赖符号保留修复）
        ("stock", -1, "库存"),
        ("stock", None, "库存"),
        ("url", "item.tmall.com/x", "链接"),
        ("listed_date", "01/03/2025", "日期"),  # 非法格式拦截
    ],
)
def test_validate_quarantines_dirty_rows(field, value, rule_frag):
    hits = _quarantine_rules([base_row(**{field: value})])
    assert "P900" in hits and rule_frag in hits["P900"]


def test_validate_allows_missing_date():
    # 缺失日期（None 或空串）都应放行，入库为 NULL
    assert _quarantine_rules([base_row(listed_date=None)]) == {}
    assert _quarantine_rules([base_row(listed_date="")]) == {}


def test_validate_requires_id_and_title():
    hits = _quarantine_rules(
        [base_row(product_id=None), base_row(title="")]
    )
    assert len(hits) == 2
    assert all("必填" in rule for rule in hits.values())
