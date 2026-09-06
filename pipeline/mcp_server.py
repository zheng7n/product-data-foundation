# -*- coding: utf-8 -*-
"""MCP Server —— 把商品数据底座暴露为 AI 客户端可直接调用的工具。

协议：MCP（Model Context Protocol）over stdio，JSON-RPC 2.0、按行分隔。
官方 MCP Python SDK 要求 Python 3.10+，本机为 3.8，故按协议规范以标准库实现
（握手 / 工具列表 / 工具调用 / 错误码），接口兼容官方客户端，可平滑替换为 FastMCP。

注册方式（如在 Claude Code / ZCode 等 MCP 客户端中）：
    command: python
    args:    [绝对路径/pipeline/mcp_server.py]

安全设计：数据库以只读模式打开（SQLite mode=ro），AI 只能查询、不能写入生产数据。

用法（手动冒烟测试）：
    echo {"jsonrpc":"2.0","id":1,"method":"tools/list"} | python pipeline/mcp_server.py
"""
import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "output" / "product_db.sqlite"

SERVER_INFO = {"name": "product-data-foundation", "version": "1.0.0"}


def db_connect():
    """只读连接：AI 侧无写入权限，避免无保护地操作生产数据。"""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"数据库不存在: {DB_PATH}，请先运行管道")
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


# ---------------- 工具实现 ----------------
def tool_query_products(args: dict):
    sql = """SELECT p.product_id, p.title, c.category_name, p.price,
                    p.stock, p.rating, p.listed_date, p.source
             FROM product p LEFT JOIN category c ON p.category_id = c.category_id
             WHERE 1=1"""
    params = []
    if args.get("category"):
        sql += " AND c.category_name = ?"
        params.append(args["category"])
    if args.get("keyword"):
        sql += " AND p.title LIKE ?"
        params.append(f"%{args['keyword']}%")
    limit = min(int(args.get("limit", 10)), 50)
    sql += " ORDER BY p.product_id LIMIT ?"
    params.append(limit)
    conn = db_connect()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    keys = ["product_id", "title", "category", "price", "stock", "rating", "listed_date", "source"]
    return {"count": len(rows), "products": [dict(zip(keys, r)) for r in rows]}


def tool_get_categories(args: dict):
    conn = db_connect()
    try:
        rows = conn.execute(
            """SELECT c.category_name, COUNT(*) AS n, ROUND(AVG(p.price), 1) AS avg_price
               FROM product p JOIN category c ON p.category_id = c.category_id
               GROUP BY 1 ORDER BY n DESC"""
        ).fetchall()
    finally:
        conn.close()
    return {"categories": [{"category": r[0], "count": r[1], "avg_price": r[2]} for r in rows]}


def tool_get_stats(args: dict):
    conn = db_connect()
    try:
        total = conn.execute("SELECT COUNT(*) FROM product").fetchone()[0]
        cate = conn.execute("SELECT COUNT(*) FROM category").fetchone()[0]
        avg = conn.execute("SELECT ROUND(AVG(price), 1) FROM product").fetchone()[0]
        by_source = dict(conn.execute("SELECT source, COUNT(*) FROM product GROUP BY source").fetchall())
    finally:
        conn.close()
    return {"total_products": total, "total_categories": cate, "avg_price": avg, "by_source": by_source}


def tool_get_pipeline_runs(args: dict):
    limit = min(int(args.get("limit", 5)), 20)
    conn = db_connect()
    try:
        rows = conn.execute(
            """SELECT ran_at, source_rows, dedup_removed, quarantined,
                      passed_rows, duration_ms, status
               FROM pipeline_run ORDER BY ran_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    keys = ["ran_at", "source_rows", "dedup_removed", "quarantined", "passed_rows", "duration_ms", "status"]
    return {"runs": [dict(zip(keys, r)) for r in rows]}


TOOLS = [
    {
        "name": "query_products",
        "description": "按类目和标题关键词查询商品数据底座中的商品列表",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "类目名，如：数码电子"},
                "keyword": {"type": "string", "description": "标题关键词，如：耳机"},
                "limit": {"type": "integer", "description": "返回条数，默认 10，最大 50"},
            },
        },
    },
    {
        "name": "get_categories",
        "description": "查询类目维度表：每个类目的商品数与平均价格",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_stats",
        "description": "查询数据底座总览：商品总数、类目数、平均价格、来源分布",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_pipeline_runs",
        "description": "查询管道运行历史：每次执行的行数、拦截数、耗时与状态",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "返回条数，默认 5"}},
        },
    },
]

HANDLERS = {
    "query_products": tool_query_products,
    "get_categories": tool_get_categories,
    "get_stats": tool_get_stats,
    "get_pipeline_runs": tool_get_pipeline_runs,
}


# ---------------- JSON-RPC 调度 ----------------
def rpc_error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def handle(req: dict):
    """处理单条 JSON-RPC 请求；通知（无 id）返回 None。"""
    method = req.get("method", "")
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name", "")
        handler = HANDLERS.get(name)
        if handler is None:
            return rpc_error(rid, -32602, f"unknown tool: {name}")
        try:
            data = handler(params.get("arguments") or {})
        except FileNotFoundError as exc:
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": str(exc)}], "isError": True}}
        except Exception as exc:  # 工具内部错误按 MCP 规范回 isError，而非协议错误
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": f"tool error: {exc}"}], "isError": True}}
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}]},
        }
    if rid is not None:
        return rpc_error(rid, -32601, f"method not found: {method}")
    return None  # 通知类消息（如 notifications/initialized）不回复


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
