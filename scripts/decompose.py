#!/usr/bin/env python3
"""Decompose combo meals into their default components and sum nutrition.

A combo (三件套 / 双人餐 / 随心选 / ...) has no nutrition row of its own:
``list-nutrition-foods`` only carries single items. But ``query-meal-detail``
returns the combo's structure as ``rounds`` (slots: main / side / drink), and
each slot's ``choices`` marks the default pick with ``isDefault=1``. So the
*correct* combo nutrition is the sum of its default components' rows — not a
fuzzy guess against the combo name.

    export MCD_MCP_TOKEN=...
    python scripts/decompose.py --store 1450713

Reads ``data/menu-snapshot.json`` + ``data/nutrition-snapshot.json``, calls
``query-meal-detail`` once per combo, and writes ``data/combo-nutrition.json``
plus an updated coverage line. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_client import McpClient, McpError  # noqa: E402
from normalize import NameMatcher, _COMBO, adapt_nutrition_row  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def unwrap(response: dict) -> dict:
    structured = response.get("structuredContent")
    if not isinstance(structured, dict):
        raise McpError("no structuredContent")
    if structured.get("code") not in (None, 200):
        raise McpError(f"upstream error {structured.get('code')}: {structured.get('message')}")
    return structured.get("data")


def default_components(detail: dict) -> list[dict]:
    """Pull the default (isDefault=1) choice out of every round."""
    components: list[dict] = []
    for round_ in detail.get("rounds") or []:
        picks = [choice for choice in round_.get("choices") or [] if choice.get("isDefault") == 1]
        # Fall back to the only included choice if isDefault is missing.
        if not picks:
            picks = [choice for choice in round_.get("choices") or [] if choice.get("quantity", 0) >= 1]
        for choice in picks:
            components.append({"code": choice.get("code"), "name": choice.get("name")})
    return components


def build_nutrition_index(nutrition_rows: list[dict], aliases: dict | None) -> tuple[NameMatcher, dict]:
    matcher = NameMatcher(aliases=aliases)
    values: dict[str, dict] = {}
    for row in nutrition_rows:
        adapted = adapt_nutrition_row(row)
        if not adapted["name"]:
            continue
        matcher.add(adapted["name"], adapted["name"])
        values[adapted["name"]] = adapted["nutrition"] or {}
    return matcher, values


def sum_components(components: list[dict], matcher: NameMatcher, values: dict) -> dict:
    fields = ("kcal", "protein_g", "fat_g", "carb_g", "sodium_mg", "calcium_mg")
    total = {field: 0.0 for field in fields}
    matched: list[dict] = []
    missing: list[dict] = []
    for component in components:
        result = matcher.match(component["name"] or "")
        if result.status == "matched" and result.key:
            row = values.get(result.key, {})
            for field in fields:
                value = row.get(field)
                if value is not None:
                    total[field] += float(value)
            matched.append({"name": component["name"], "key": result.key, "method": result.method})
        else:
            missing.append({"name": component["name"], "method": result.method})
    return {
        "totals": {field: round(total[field], 1) for field in fields},
        "matched": matched,
        "missing": missing,
        "complete": not missing,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Decompose combos and sum their nutrition")
    parser.add_argument("--store", required=True, help="storeCode")
    parser.add_argument("--be-type", type=int, default=1)
    args = parser.parse_args(argv)

    with open(os.path.join(DATA, "menu-snapshot.json"), encoding="utf-8") as handle:
        menu = json.load(handle)
    with open(os.path.join(DATA, "nutrition-snapshot.json"), encoding="utf-8") as handle:
        nutrition = json.load(handle)
    aliases_path = os.path.join(DATA, "aliases.json")
    aliases = json.load(open(aliases_path, encoding="utf-8")) if os.path.exists(aliases_path) else None

    matcher, values = build_nutrition_index(nutrition, aliases)

    combos = [
        item for item in menu["items"] if _COMBO.search(item["name"] or "")
    ]
    print(f"combo 候选: {len(combos)} 个")

    client = McpClient()
    client.initialize()
    order_type = 1 if args.be_type in (1, 5) else 2

    results: list[dict] = []
    complete = 0
    for index, item in enumerate(combos, 1):
        detail = unwrap(
            client.call_tool(
                "query-meal-detail",
                {"storeCode": args.store, "orderType": order_type, "beType": args.be_type, "code": item["code"]},
            )
        )
        components = default_components(detail)
        summed = sum_components(components, matcher, values)
        if summed["complete"]:
            complete += 1
        results.append(
            {
                "code": item["code"],
                "name": item["name"],
                "components": components,
                "nutrition": summed["totals"] if summed["complete"] else None,
                "matched": summed["matched"],
                "missing": summed["missing"],
                "complete": summed["complete"],
            }
        )
        print(f"  [{index}/{len(combos)}] {item['name']}: {'完整' if summed['complete'] else '缺 ' + '、'.join(m['name'] for m in summed['missing'])}")

    with open(os.path.join(DATA, "combo-nutrition.json"), "w", encoding="utf-8") as handle:
        json.dump({"store": args.store, "results": results}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(f"\n套餐可完整拆解: {complete}/{len(combos)}  | api calls: {client.call_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
