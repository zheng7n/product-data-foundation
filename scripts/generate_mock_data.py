# -*- coding: utf-8 -*-
"""模拟生成 3 个来源的"脏"商品数据 Excel。

场景设定（对应真实电商公司现状）：
1. 天猫后台导出表 —— 系统导出，格式相对规范但有缺失值
2. 运营手工维护表 —— 人工维护，列名随意、格式混乱
3. 竞品采集表 —— 外部采集，英文字段名、日期格式不同

三个来源描述同一批商品，列名、日期格式、类目命名互不一致，
用于模拟"多源异构数据 → 统一数据底座"的真实痛点。
"""
import random
from pathlib import Path

import pandas as pd

random.seed(42)

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"

CATEGORIES = ["女装", "数码电子", "家居日用", "美妆护肤", "母婴育儿", "食品生鲜"]

BRAND_WORDS = ["优选", "旗舰店", "轻奢", "严选", "畅销", "经典", "新款", "爆款"]
ITEM_WORDS = {
    "女装": ["连衣裙", "针织衫", "牛仔裤", "风衣", "短袖T恤"],
    "数码电子": ["蓝牙耳机", "充电宝", "机械键盘", "智能手环", "数据线"],
    "家居日用": ["收纳盒", "保温杯", "香薰灯", "洗衣液", "垃圾袋"],
    "美妆护肤": ["面膜", "精华液", "防晒霜", "卸妆水", "口红"],
    "母婴育儿": ["纸尿裤", "婴儿湿巾", "儿童水杯", "安抚玩具", "辅食碗"],
    "食品生鲜": ["坚果礼盒", "牛排", "龙井茶", "苹果", "鸡蛋"],
}


def make_title(cate: str) -> str:
    return f"{random.choice(BRAND_WORDS)}{random.choice(ITEM_WORDS[cate])}{random.choice(['', ' 2025', ' 春夏款', ' 礼盒装'])}"


def fullwidth(s: str) -> str:
    """把字符串里的数字和字母转成全角，模拟中文输入法事故。"""
    return "".join(
        chr(ord(c) + 0xFEE0) if c.isdigit() or c.isalpha() else c for c in s
    )


def messy_text(s: str, rng: random.Random) -> str:
    """随机加脏：全角空格 / 首尾空格 / 全角字符。"""
    r = rng.random()
    if r < 0.10:
        return "\u3000" + s + "\u3000"
    if r < 0.20:
        return "  " + s + " "
    if r < 0.25:
        return fullwidth(s)
    return s


def dirty_price(price: float, rng: random.Random):
    """按概率把正常价格弄脏。"""
    r = rng.random()
    if r < 0.03:
        return 0
    if r < 0.05:
        return -price
    if r < 0.08:
        return 99999
    if r < 0.13:
        return f"￥{price:.1f}"
    if r < 0.16:
        return f"{price:.2f}元"
    return round(price, 1)


def dirty_stock(stock: int, rng: random.Random):
    r = rng.random()
    if r < 0.03:
        return None
    if r < 0.05:
        return -5
    if r < 0.10:
        return f"{stock}件"
    return stock


def dirty_date(d: pd.Timestamp, rng: random.Random) -> str:
    r = rng.random()
    if r < 0.3:
        return d.strftime("%Y/%m/%d")
    if r < 0.55:
        return d.strftime("%Y-%m-%d")
    if r < 0.75:
        return f"{d.year}年{d.month}月{d.day}日"
    if r < 0.85:
        return d.strftime("%Y.%m.%d")
    return ""  # 缺失


def dirty_url(url: str, rng: random.Random) -> str:
    r = rng.random()
    if r < 0.06:
        return url.replace("https://", "")
    if r < 0.08:
        return "www.invalid-shop-demo.com/item/999"
    return url


def dirty_category(cate: str, rng: random.Random) -> str:
    variants = {
        "女装": ["女装", "女裝", "女装 ", " Women"],
        "数码电子": ["数码电子", "电子数码", "3C", "數碼電子"],
        "家居日用": ["家居日用", "日用家居", "家居"],
        "美妆护肤": ["美妆护肤", "护肤美妆", "美妆"],
        "母婴育儿": ["母婴育儿", "育儿母婴", "母婴"],
        "食品生鲜": ["食品生鲜", "生鲜食品", "食品"],
    }
    pool = variants[cate]
    if rng.random() < 0.35:
        return rng.choice(pool)
    return cate


def gen_records(n: int) -> list:
    rng = random.Random(42)
    records = []
    for i in range(n):
        cate = rng.choice(CATEGORIES)
        pid = f"P{600000 + i * 3}"
        price = round(rng.uniform(19.9, 899.0), 1)
        rec = {
            "id": pid,
            "title": make_title(cate),
            "category": dirty_category(cate, rng),
            "price": dirty_price(price, rng),
            "stock": dirty_stock(rng.randint(0, 5000), rng),
            "rating": round(rng.uniform(3.8, 5.0), 1),
            "listed_date": dirty_date(
                pd.Timestamp("2024-01-01") + pd.Timedelta(days=rng.randint(0, 500)), rng
            ),
            "url": dirty_url(f"https://item.tmall.com/item.htm?id={pid}", rng),
        }
        records.append(rec)
    # 植入脏行：缺 ID / 缺标题
    for j in range(4):
        records[j]["id"] = None if j % 2 == 0 else records[j]["id"]
        records[j]["title"] = "" if j % 2 else records[j]["title"]
    return records


def main():
    records = gen_records(240)
    df = pd.DataFrame(records)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # 来源 1：天猫后台导出（相对规范，但缺值多）
    tmall = df.sample(frac=0.7, random_state=1).rename(
        columns={
            "id": "商品ID",
            "title": "商品标题",
            "category": "叶子类目",
            "price": "销售价(元)",
            "stock": "可售库存",
            "rating": "店铺评分",
            "listed_date": "上架时间",
            "url": "商品链接",
        }
    )
    tmall.to_excel(RAW_DIR / "天猫后台_商品导出.xlsx", index=False)

    # 来源 2：运营手工维护表（列名随意 + 内部重复 6 行）
    ops = (
        df.sample(frac=0.5, random_state=2)
        .rename(
            columns={
                "id": "产品id ",
                "title": " 标题",
                "category": "分类",
                "price": "价格",
                "stock": "库存量",
                "rating": "评分",
                "listed_date": "上架日期",
                "url": "链接",
            }
        )
    )
    ops = pd.concat([ops, ops.head(6)], ignore_index=True)  # 手工表常见：重复粘贴
    ops.to_excel(RAW_DIR / "运营手工维护表.xlsx", index=False)

    # 来源 3：竞品采集表（英文字段名）
    comp = df.sample(frac=0.45, random_state=3).rename(
        columns={
            "id": "item_id",
            "title": "title",
            "category": "cate",
            "price": "price",
            "stock": "stock",
            "rating": "rate",
            "listed_date": "list_date",
            "url": "url",
        }
    )
    comp.to_excel(RAW_DIR / "竞品采集表.xlsx", index=False)

    print(f"已生成 3 个原始文件到 {RAW_DIR}")
    print(f"  天猫后台: {len(tmall)} 行 | 运营手工: {len(ops)} 行 | 竞品采集: {len(comp)} 行")


if __name__ == "__main__":
    main()
