# -*- coding: utf-8 -*-
"""商品数据管理台 —— Streamlit 界面。

把管道从"开发者跑脚本"升级为"运营可用的工具"：
一键执行管道、商品数据查询导出（筛选状态同步到 URL，可分享链接）、
统计概览、异常明细人工复核。

用法：python -m streamlit run pipeline/app.py
"""
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from extract import extract_all, RAW_DIR
from transform import transform, dedup, VALID_CATEGORIES
from validate import validate
from load import load, DB_PATH

OUTPUT_DIR = Path(__file__).parent.parent / "output"
REPORT_PATH = OUTPUT_DIR / "校验报告.xlsx"

st.set_page_config(page_title="商品数据管理台", page_icon="📦", layout="wide")
st.title("商品数据管理台")
st.caption("多来源商品数据 → 字段统一 → 异常校验 → 自动入库")


# ---------------- 数据与缓存 ----------------
@st.cache_data
def read_source_infos():
    """侧边栏展示：数据源文件名 + 行数。"""
    infos = []
    for f in sorted(RAW_DIR.glob("*.xlsx")):
        try:
            rows = len(pd.read_excel(f, usecols=[0]))
        except Exception:
            rows = None
        infos.append((f.name, rows))
    return infos


@st.cache_data(ttl=30)
def read_report_quarantined():
    if REPORT_PATH.exists():
        try:
            return pd.read_excel(REPORT_PATH, sheet_name="异常明细", dtype=str)
        except Exception:
            return None
    return None


@st.cache_data(ttl=60)
def read_products() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        """SELECT p.product_id AS 商品ID, p.title AS 标题, c.category_name AS 类目,
                  p.price AS 价格, p.stock AS 库存, p.rating AS 评分,
                  p.listed_date AS 上架日期, p.source AS 来源, p.url AS 链接
           FROM product p LEFT JOIN category c ON p.category_id = c.category_id""",
        conn,
    )
    conn.close()
    return df


def run_pipeline():
    """顺序执行管道各阶段。"""
    with st.status("管道执行中…", expanded=True) as status:
        st.write("① 读取数据源")
        frames = extract_all()
        st.write("② 字段统一与清洗")
        combined = transform(frames)
        combined, dup_count = dedup(combined)
        st.write("③ 异常校验")
        passed, quarantined = validate(combined)
        st.write("④ 建表入库")
        load(passed, VALID_CATEGORIES)
        status.update(label="管道执行完成", state="complete", expanded=False)
    return passed, quarantined, dup_count


# ---------------- 侧边栏：数据源 + 管道执行 ----------------
with st.sidebar:
    st.subheader("数据源文件")
    for name, rows in read_source_infos():
        st.markdown(f"- `{name}`（{rows} 行）" if rows else f"- `{name}`")

    st.divider()
    run_btn = st.button("执行管道", type="primary", use_container_width=True)
    st.caption("执行流程：读取 → 统一清洗 → 校验 → 入库 → 报告")

if run_btn:
    if not read_source_infos():
        st.error("缺少数据源文件。请先运行 scripts/generate_mock_data.py 生成模拟数据。")
    else:
        _, quarantined, dup_count = run_pipeline()
        st.session_state["quarantined"] = quarantined
        st.cache_data.clear()
        st.toast("管道执行完成")

# ---------------- 异常明细数据（会话优先，其次读报告文件） ----------------
quarantined = st.session_state.get("quarantined")
if quarantined is None:
    quarantined = read_report_quarantined()
n_quarantined = 0 if quarantined is None else len(quarantined)

@st.cache_data(ttl=30)
def read_runs() -> pd.DataFrame:
    """管道运行历史（pipeline_run 表）。"""
    if not DB_PATH.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        """SELECT ran_at AS 执行时间, source_rows AS 原始行数,
                  dedup_removed AS 去重移除, quarantined AS 异常拦截,
                  passed_rows AS 入库行数, loaded_total AS 商品总数快照,
                  duration_ms AS 耗时ms, status AS 状态
           FROM pipeline_run ORDER BY ran_at DESC LIMIT 50""",
        conn,
    )
    conn.close()
    return df


products = read_products()
if products.empty:
    st.info("数据库还没有数据。点击左侧「执行管道」开始，完成后商品数据会展示在这里。")
    st.stop()

# ---------------- 指标卡 ----------------
m1, m2, m3, m4 = st.columns(4)
m1.metric("入库商品数", f"{len(products):,}")
m2.metric("类目数", f"{products['类目'].nunique():,}")
m3.metric("平均价格", f"¥{products['价格'].mean():,.1f}")
m4.metric("库存总量", f"{int(products['库存'].sum()):,}")

tab_labels = ["商品数据", "统计概览", f"异常明细 ({n_quarantined})" if n_quarantined else "异常明细", "运行历史"]
tab_data, tab_stats, tab_quarantine, tab_runs = st.tabs(tab_labels)

# ---------------- Tab 1：商品数据查询导出 ----------------
with tab_data:
    # 筛选状态同步到 URL，筛选后的页面链接可直接分享
    qp = st.query_params
    cate_options = ["全部"] + sorted(products["类目"].dropna().unique().tolist())
    url_cate = qp.get("cate", "全部")
    if url_cate not in cate_options:
        url_cate = "全部"
    url_keyword = qp.get("q", "")

    c1, c2 = st.columns([1, 3])
    cate = c1.selectbox("按类目筛选", cate_options, index=cate_options.index(url_cate))
    keyword = c2.text_input("按标题搜索", value=url_keyword, placeholder="输入商品关键词，如：蓝牙耳机…")

    if qp.get("cate", "全部") != cate:
        qp["cate"] = cate
    if keyword:
        if qp.get("q", "") != keyword:
            qp["q"] = keyword
    elif "q" in qp:
        del qp["q"]

    view = products
    if cate != "全部":
        view = view[view["类目"] == cate]
    if keyword:
        view = view[view["标题"].str.contains(keyword, na=False)]

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "价格": st.column_config.NumberColumn(format="¥%.2f"),
            "库存": st.column_config.NumberColumn(format="%d"),
            "链接": st.column_config.LinkColumn(display_text="打开商品页"),
        },
    )
    st.caption(f"共 {len(view):,} 条（入库总数 {len(products):,} 条）")
    st.download_button(
        "导出当前筛选结果 (CSV)",
        view.to_csv(index=False).encode("utf-8-sig"),
        file_name="商品数据.csv",
        mime="text/csv",
    )

# ---------------- Tab 2：统计概览 ----------------
with tab_stats:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("类目分布")
        st.bar_chart(products["类目"].value_counts())
    with c2:
        st.subheader("数据来源分布")
        st.bar_chart(products["来源"].value_counts())

# ---------------- Tab 3：异常明细复核 ----------------
with tab_quarantine:
    if n_quarantined == 0:
        st.success("当前没有异常拦截记录。执行一次管道后，被拦截的数据会显示在这里供人工复核。")
    else:
        rule_options = ["全部"] + sorted(quarantined["rule_hit"].dropna().unique().tolist())
        rule = st.selectbox("按拦截原因筛选", rule_options)
        view = quarantined if rule == "全部" else quarantined[quarantined["rule_hit"] == rule]
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.caption(f"共 {len(view):,} 条被拦截，入库时已剔除。可人工确认后修正源数据并重新执行管道。")

# ---------------- Tab 4：运行历史 ----------------
with tab_runs:
    runs = read_runs()
    if runs.empty:
        st.info("还没有运行记录。每次执行管道（含定时调度）都会在这里留档。")
    else:
        st.dataframe(runs, use_container_width=True, hide_index=True)
        last = runs.iloc[0]
        st.caption(
            f"最近一次：{last['执行时间']}，原始 {last['原始行数']:,} 行 → 入库 "
            f"{last['入库行数']:,} 行，耗时 {last['耗时ms']} ms。"
            "配合 scheduler.py 定时执行，即可无人值守维护数据底座。"
        )
