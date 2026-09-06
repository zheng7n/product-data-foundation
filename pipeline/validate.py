# -*- coding: utf-8 -*-
"""阶段 3：异常校验 —— 每条规则独立检查，拦截行带原因标记。

设计原则：宁可拦下人工复核，也不让脏数据污染数据底座。
"""
import re

import pandas as pd

PRICE_MIN, PRICE_MAX = 0.0, 10000.0


def _check_url(url) -> bool:
    if not url:
        return False
    return bool(re.match(r"^https?://[^\s]+\.[^\s]+$", url))


def validate(df: pd.DataFrame):
    """逐行校验，返回 (通过表, 拦截表)。

    拦截表比原表多一列 rule_hit，说明触发的规则。
    """
    rules = []

    def rule(name):
        def deco(fn):
            rules.append((name, fn))
            return fn
        return deco

    @rule("必填字段缺失(商品ID/标题)")
    def missing_required(row):
        return not row["product_id"] or not row["title"]

    @rule("价格异常(缺失/越界)")
    def bad_price(row):
        p = row["price"]
        return p is None or pd.isna(p) or not (PRICE_MIN < p <= PRICE_MAX)

    @rule("库存异常(缺失/负数)")
    def bad_stock(row):
        s = row["stock"]
        return s is None or pd.isna(s) or s < 0

    @rule("日期非法(有值但无法解析)")
    def bad_date(row):
        d = row["listed_date"]
        if d in (None, ""):  # 缺失放行，入库为 NULL
            return False
        return not re.match(r"^\d{4}-\d{2}-\d{2}$", str(d))

    @rule("商品链接格式非法")
    def bad_url(row):
        return not _check_url(row["url"])

    def first_hit(row):
        for name, fn in rules:
            try:
                if fn(row):
                    return name
            except Exception:
                return "校验器内部错误"
        return None

    hits = df.apply(first_hit, axis=1)
    passed = df[hits.isna()].copy()
    quarantined = df[hits.notna()].copy()
    quarantined["rule_hit"] = hits[hits.notna()]

    print(f"[校验] 通过 {len(passed)} 行，拦截 {len(quarantined)} 行")
    for name, _ in rules:
        n = (quarantined["rule_hit"] == name).sum()
        if n:
            print(f"        - {name}: {n} 行")
    return passed, quarantined
