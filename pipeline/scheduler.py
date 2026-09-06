# -*- coding: utf-8 -*-
"""定时调度 —— 无人值守自动执行管道。

用法：
    python pipeline/scheduler.py --interval 60           # 每 60 分钟执行一次，无限循环
    python pipeline/scheduler.py --interval 30 --times 5 # 每 30 分钟一次，共 5 次

注册为 Windows 任务计划（开机后每小时自动执行，日志写入 output/scheduler.log）：
    schtasks /Create /TN "ProductDataPipeline" /SC HOURLY /TR ^
      "python E:\jianli\projects\product-data-pipeline\pipeline\scheduler.py --times 1"

失败不退出：单次执行异常只记录，下个周期重试。
"""
import argparse
import time

from run_pipeline import run_all


def main():
    parser = argparse.ArgumentParser(description="商品数据管道定时调度")
    parser.add_argument("--interval", type=int, default=60, help="执行间隔（分钟），默认 60")
    parser.add_argument("--times", type=int, default=0, help="执行次数，0 表示无限循环")
    args = parser.parse_args()

    print(f"[调度] 启动：每 {args.interval} 分钟执行一次"
          + (f"，共 {args.times} 次" if args.times else "，无限循环"))
    n = 0
    while True:
        n += 1
        try:
            stats = run_all()
            print(f"[调度] 第 {n} 次执行成功：入库 {stats['loaded_total']} 条")
        except Exception as exc:  # 单次失败不终止调度
            print(f"[调度] 第 {n} 次执行失败：{exc}（下个周期自动重试）")
        if args.times and n >= args.times:
            print("[调度] 达到设定次数，退出")
            break
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
