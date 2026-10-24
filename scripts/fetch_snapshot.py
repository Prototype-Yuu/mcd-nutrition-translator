#!/usr/bin/env python3
"""Fetch and snapshot the three data sources this skill depends on.

Writes plain JSON into ``data/`` so that later steps (alignment, meal cards,
tests) never need the network or a token.

    export MCD_MCP_TOKEN=...
    python scripts/fetch_snapshot.py --city 上海 --keyword 人民广场

Nothing about the token is written to disk. Only the API payloads are kept.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_client import McpClient, McpError  # noqa: E402
from normalize import parse_compact_table  # noqa: E402

CST = timezone(timedelta(hours=8))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def unwrap(response: dict) -> dict:
    """Pull the API payload out of the MCP envelope.

    Every tool answers with ``structuredContent`` carrying the upstream API's
    ``{success, code, message, datetime, traceId, data}``. The ``data`` field
    is sometimes a dict/list and sometimes a compact-table string.
    """
    structured = response.get("structuredContent")
    if not isinstance(structured, dict):
        raise McpError("response has no structuredContent")

    code = structured.get("code")
    if code not in (None, 200):
        raise McpError(f"upstream error {code}: {structured.get('message')}")

    data = structured.get("data")
    if isinstance(data, str) and data.lstrip().startswith("["):
        return {"rows": parse_compact_table(data)}
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot McDonald's MCP data")
    parser.add_argument("--city", default="上海")
    parser.add_argument("--keyword", default="人民广场")
    parser.add_argument("--be-type", type=int, default=1, help="1=到店自取, 5=得来速")
    args = parser.parse_args(argv)

    os.makedirs(DATA, exist_ok=True)
    fetched_at = datetime.now(CST).isoformat(timespec="seconds")
    client = McpClient()
    client.initialize()

    print("1/4 now-time-info")
    clock = unwrap(client.call_tool("now-time-info"))
    print(f"    server time: {clock.get('formatted')}")

    print("2/4 list-nutrition-foods")
    nutrition = unwrap(client.call_tool("list-nutrition-foods"))["rows"]
    print(f"    {len(nutrition)} rows")

    print(f"3/4 query-nearby-stores ({args.city} / {args.keyword})")
    stores = unwrap(
        client.call_tool(
            "query-nearby-stores",
            {
                "beType": args.be_type,
                "searchType": 2,
                "city": args.city,
                "keyword": args.keyword,
            },
        )
    )
    open_stores = [store for store in stores if store.get("businessStatus")]
    if not open_stores:
        print("    no open store returned", file=sys.stderr)
        return 4
    store = open_stores[0]
    print(f"    {store['storeCode']} {store['storeName']} ({store.get('distance')}m)")

    order_type = 1 if args.be_type in (1, 5) else 2
    print("4/4 query-meals")
    menu = unwrap(
        client.call_tool(
            "query-meals",
            {"storeCode": store["storeCode"], "orderType": order_type, "beType": args.be_type},
        )
    )
    meal_map = menu.get("meals") or {}
    rows = [
        {
            "code": code,
            "name": payload.get("name"),
            "currentPrice": payload.get("currentPrice"),
            "originalPrice": payload.get("originalPrice"),
        }
        for code, payload in meal_map.items()
        if payload.get("name")
    ]
    print(f"    {len(rows)} named items in {len(menu.get('categories') or [])} categories")

    meta = {"fetched_at": fetched_at, "city": args.city, "keyword": args.keyword, "beType": args.be_type}

    def dump(name: str, payload: object) -> None:
        path = os.path.join(DATA, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(f"    -> data/{name}")

    dump("nutrition-snapshot.json", nutrition)
    dump("menu-snapshot.json", {"store": store, "meta": meta, "items": rows})
    dump("store-snapshot.json", {"meta": meta, "stores": stores})

    print(f"\ndone at {fetched_at} | api calls: {client.call_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
