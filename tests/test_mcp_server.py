# -*- coding: utf-8 -*-
"""MCP Server 协议层与工具层的单元测试（直接调用 handle / handler）。"""
import json

import pytest

from mcp_server import handle, TOOLS, HANDLERS


def rpc(method, rid=1, params=None):
    return handle({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})


def test_initialize_handshake():
    resp = rpc("initialize", params={"protocolVersion": "2024-11-05"})
    assert resp["result"]["protocolVersion"] == "2024-11-05"
    assert resp["result"]["serverInfo"]["name"] == "product-data-foundation"
    assert "tools" in resp["result"]["capabilities"]


def test_initialize_echoes_client_protocol_version():
    resp = rpc("initialize", params={"protocolVersion": "2099-01-01"})
    assert resp["result"]["protocolVersion"] == "2099-01-01"


def test_tools_list_registered():
    resp = rpc("tools/list")
    names = [t["name"] for t in resp["result"]["tools"]]
    assert names == ["query_products", "get_categories", "get_stats", "get_pipeline_runs"]
    for tool in resp["result"]["tools"]:
        assert tool["inputSchema"]["type"] == "object"  # 合法 JSON Schema


def test_every_tool_has_handler():
    assert set(HANDLERS) == {t["name"] for t in TOOLS}


def test_tools_call_query_products():
    resp = rpc("tools/call", params={"name": "query_products", "arguments": {"limit": 3}})
    assert "isError" not in resp["result"]
    data = json.loads(resp["result"]["content"][0]["text"])
    assert data["count"] == 3 and len(data["products"]) == 3
    assert set(data["products"][0]) == {
        "product_id", "title", "category", "price",
        "stock", "rating", "listed_date", "source",
    }


def test_tools_call_query_by_category_and_keyword():
    resp = rpc("tools/call", params={
        "name": "query_products",
        "arguments": {"category": "数码电子", "keyword": "耳机"},
    })
    data = json.loads(resp["result"]["content"][0]["text"])
    assert all(p["category"] == "数码电子" for p in data["products"])


def test_tools_call_stats_and_categories():
    stats = json.loads(rpc("tools/call", params={"name": "get_stats"})["result"]["content"][0]["text"])
    assert stats["total_products"] > 0 and "by_source" in stats
    cats = json.loads(rpc("tools/call", params={"name": "get_categories"})["result"]["content"][0]["text"])
    assert cats["categories"] and cats["categories"][0]["count"] >= cats["categories"][-1]["count"]


def test_tools_call_runs_history():
    runs = json.loads(rpc("tools/call", params={"name": "get_pipeline_runs"})["result"]["content"][0]["text"])
    assert runs["runs"] and runs["runs"][0]["status"] == "success"


def test_unknown_tool_is_protocol_error():
    resp = rpc("tools/call", params={"name": "no_such_tool"})
    assert resp["error"]["code"] == -32602


def test_unknown_method_is_protocol_error():
    resp = rpc("resources/list")
    assert resp["error"]["code"] == -32601


def test_notification_gets_no_response():
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_ping():
    assert rpc("ping")["result"] == {}


def test_tool_error_returns_is_error_not_protocol_error():
    resp = rpc("tools/call", params={"name": "query_products", "arguments": {"limit": "abc"}})
    assert resp["result"].get("isError") is True  # 参数异常按工具错误处理，不炸协议层
