# -*- coding: utf-8 -*-
"""阶段 0（可选）：真实网页数据采集 —— books.toscrape.com。

该站点是公开的爬虫练习站（合法、稳定、无反爬限制）。采集图书详情页的
UPC / 标题 / 类目 / 价格 / 库存 / 评分，输出与其它数据源同构的 Excel
（data/raw/网页采集表.xlsx），随后由管道统一处理。

这样新增一个数据源只需两处注册：
1. extract.SOURCES 加一行来源映射
2. transform.COLUMN_MAPPING 加一张列名映射表
采集模块本身不侵入管道。

用法：python pipeline/scrape.py [--limit 15]
"""
import argparse
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "http://books.toscrape.com/"
RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; product-pipeline-demo/1.0)"}
RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


def scrape_book(url: str) -> dict:
    """采集单个图书详情页，映射为管道统一 schema 的字段。"""
    soup = fetch_soup(url)

    def text(selector: str) -> str:
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else ""

    # 详情页表格首行是 UPC，作为业务主键
    upc = text("table.table-striped tr td")
    title = text(".product_main h1")
    price = text(".price_color")  # 形如 £51.77，清洗阶段统一解析
    availability = text(".availability")
    m = re.search(r"\((\d+)\s*available\)", availability)
    stock = m.group(1) if m else ""

    rating = ""
    star = soup.select_one(".star-rating")
    if star:
        for cls in star.get("class", []):
            if cls in RATING_MAP:
                rating = str(RATING_MAP[cls])
                break

    # 面包屑最后一个链接是图书类目
    crumbs = soup.select(".breadcrumb a")
    category = crumbs[-1].get_text(strip=True) if crumbs else ""

    return {
        "item_id": upc,
        "title": title,
        "cate": category,  # 英文类目不在别名表内，清洗后归入"其他"
        "price": price,
        "stock": stock,
        "rate": rating,
        "list_date": "",  # 页面无上架日期，走"缺失放行"路径
        "url": url,
    }


def main(limit: int = 15):
    print(f"[采集] 列表页 {BASE_URL}")
    soup = fetch_soup(BASE_URL)
    links = [
        urljoin(BASE_URL, a["href"])
        for a in soup.select("article.product_pod h3 a")
    ][:limit]

    rows, failed = [], 0
    for i, url in enumerate(links, 1):
        try:
            rows.append(scrape_book(url))
            print(f"[采集] ({i}/{len(links)}) {url.rsplit('/', 2)[-2]}")
        except Exception as exc:
            failed += 1
            print(f"[采集] 失败跳过: {url} ({exc})")
        time.sleep(0.3)  # 控制请求节奏

    if not rows:
        print("[采集] 未采到任何数据，跳过写出")
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "网页采集表.xlsx"
    pd.DataFrame(rows).to_excel(out, index=False)
    print(f"[采集] 完成：成功 {len(rows)} 条 / 失败 {failed} 条 -> {out.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="采集网页商品数据")
    parser.add_argument("--limit", type=int, default=15, help="采集条数")
    args = parser.parse_args()
    main(args.limit)
