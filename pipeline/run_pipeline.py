# -*- coding: utf-8 -*-
"""商品数据自动化管道 —— 主入口。

流程：批量读取(extract) -> 字段统一/清洗/去重(transform) -> 异常校验(validate)
      -> 建表入库(load) -> 运行日志/校验报告(report)

用法：
    python pipeline/run_pipeline.py          # 单次执行
    python pipeline/scheduler.py --interval 60  # 定时调度（无人值守）

run_all() 返回本次执行的统计 dict，供调度器和管理台复用。
"""
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from extract import extract_all
from transform import transform, dedup, VALID_CATEGORIES
from validate import validate
from load import load, log_run

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def write_report(quarantined: pd.DataFrame, total: int, passed_n: int, dup_count: int):
    """生成 Excel 校验报告：入库汇总 + 异常明细。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / "校验报告.xlsx"

    summary = pd.DataFrame(
        [
            ("来源原始总行数", total),
            ("重复移除行数", dup_count),
            ("异常拦截行数", len(quarantined)),
            ("最终入库行数", passed_n),
        ],
        columns=["指标", "数量"],
    )
    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="入库汇总", index=False)
        if len(quarantined):
            quarantined.to_excel(writer, sheet_name="异常明细", index=False)
    print(f"[报告] 校验报告已写入 {report_path}")


def run_all(log: bool = True) -> dict:
    """执行完整管道，返回统计。log=False 时不写运行历史（如调试）。"""
    started = time.time()
    frames = extract_all()
    combined = transform(frames)
    combined, dup_count = dedup(combined)
    passed, quarantined = validate(combined)
    totals = load(passed, VALID_CATEGORIES)

    stats = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "source_rows": len(combined) + dup_count,
        "dedup_removed": dup_count,
        "passed_rows": len(passed),
        "quarantined": len(quarantined),
        "loaded_total": totals["products"],
        "duration_ms": int((time.time() - started) * 1000),
        "status": "success",
    }
    write_report(quarantined, stats["source_rows"], len(passed), dup_count)
    if log:
        log_run(stats)
    print(
        f"[完成] 原始 {stats['source_rows']} 行 -> 去重 {stats['dedup_removed']} -> "
        f"拦截 {stats['quarantined']} -> 入库 {stats['passed_rows']} 行，"
        f"耗时 {stats['duration_ms']} ms"
    )
    return stats


def main():
    run_all()


if __name__ == "__main__":
    main()
