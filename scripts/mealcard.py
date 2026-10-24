#!/usr/bin/env python3
"""Meal card: turn McDonald's six nutrition numbers into something readable.

Design intent
-------------
The target user is a student with no nutrition background. Percentages of a
reference intake mean nothing to them, and "set a sodium budget" is homework.
So the default output is a *card*, not a ledger:

    totals  ->  everyday comparisons (bowls of rice, eggs, grams of salt)
            ->  neutral descriptive tags (protein lead / carb mainstay / ...)
            ->  exactly one constructive tip

No targets are required. ``--solve`` adds the optional constrained mode for the
minority who do want "give me something under 600 kcal".

Honesty rules baked into the code
---------------------------------
* A missing field is reported, never imputed. ``None`` does not join a sum and
  always lands in ``coverage.missing_fields``.
* If a row's serving basis is unknown, the whole card refuses to total
  (``computable=False``, exit code 2) instead of producing a plausible lie.
* Comparison values are *this project's conventions*, not McDonald's data, and
  are exported with the card so any reader can check the arithmetic.
* Tags describe composition. They never grade a meal as good or bad.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from typing import Any, Iterable

# --------------------------------------------------------------------------
# reference values -- project conventions, NOT official McDonald's data
# --------------------------------------------------------------------------

ANALOGY_BASIS: dict[str, float] = {
    # 1 bowl of cooked rice, ~150 g
    "rice_bowl_kcal": 200.0,
    # 1 hen egg, ~50 g edible portion
    "egg_protein_g": 6.0,
    # table salt is ~39% sodium by mass -> 1 g salt ~= 400 mg sodium
    "salt_g_per_sodium_mg": 1.0 / 400.0,
}

#: Daily reference used only to phrase "how much of a day is this".
#: Treated as a project convention and disclosed in references/analogy-basis.md.
DAILY_REFERENCE: dict[str, float] = {
    "kcal": 2000.0,
    "protein_g": 60.0,
    "fat_g": 60.0,
    "carb_g": 300.0,
    "sodium_mg": 2000.0,
    "calcium_mg": 800.0,
}

NUTRIENT_FIELDS = ("kcal", "protein_g", "fat_g", "carb_g", "sodium_mg", "calcium_mg")
NUTRIENT_LABELS = {
    "kcal": "热量",
    "protein_g": "蛋白质",
    "fat_g": "脂肪",
    "carb_g": "碳水化合物",
    "sodium_mg": "钠",
    "calcium_mg": "钙",
}
NUTRIENT_UNITS = {
    "kcal": "千卡",
    "protein_g": "克",
    "fat_g": "克",
    "carb_g": "克",
    "sodium_mg": "毫克",
    "calcium_mg": "毫克",
}

DISCLAIMER = (
    "以上为麦当劳官方营养标注值；生活类比为本项目约定的参照换算，"
    "不构成营养或医疗建议。"
)


# --------------------------------------------------------------------------
# aggregation
# --------------------------------------------------------------------------


def compute_totals(items: Iterable[dict]) -> dict:
    """Sum the six nutrients across items, tracking every missing value.

    ``items`` entries use the normalised shape produced by ``normalize.py``:
    ``{"name": str, "nutrition": {..} | None, "basis": "per_serving" | ...}``.
    """
    totals = {field: 0.0 for field in NUTRIENT_FIELDS}
    seen = {field: 0 for field in NUTRIENT_FIELDS}
    missing: list[dict] = []
    unknown_basis: list[str] = []
    item_count = 0

    for item in items:
        item_count += 1
        name = item.get("name") or "(未命名)"
        nutrition = item.get("nutrition")
        basis = item.get("basis", "per_serving")

        if not nutrition:
            missing.append({"name": name, "reason": "no_nutrition_row"})
            continue
        if basis != "per_serving":
            unknown_basis.append(name)
            continue

        for field in NUTRIENT_FIELDS:
            value = nutrition.get(field)
            if value is None:
                missing.append({"name": name, "field": field, "reason": "field_absent"})
                continue
            totals[field] += float(value)
            seen[field] += 1

    matched = item_count - len({m["name"] for m in missing if m.get("reason") == "no_nutrition_row"})
    coverage = {
        "items_total": item_count,
        "items_with_nutrition": matched,
        "rate": round(matched / item_count, 4) if item_count else 0.0,
        "missing_fields": missing,
        "unknown_basis": unknown_basis,
    }
    return {
        "totals": {field: round(value, 2) if seen[field] else None for field, value in totals.items()},
        "counted_fields": seen,
        "coverage": coverage,
    }


# --------------------------------------------------------------------------
# everyday comparisons
# --------------------------------------------------------------------------


def to_analogy(totals: dict) -> dict:
    """Express totals in units a student can picture without any training."""
    analogies: dict[str, Any] = {}

    kcal = totals.get("kcal")
    if kcal is not None:
        bowls = kcal / ANALOGY_BASIS["rice_bowl_kcal"]
        analogies["rice_bowls"] = {
            "value": round(bowls, 1),
            "text": _range_text(bowls, "碗米饭"),
        }

    protein = totals.get("protein_g")
    if protein is not None:
        eggs = protein / ANALOGY_BASIS["egg_protein_g"]
        analogies["eggs"] = {
            "value": round(eggs, 1),
            "text": _range_text(eggs, "个鸡蛋的蛋白质"),
        }

    sodium = totals.get("sodium_mg")
    if sodium is not None:
        salt = sodium * ANALOGY_BASIS["salt_g_per_sodium_mg"]
        analogies["salt_grams"] = {
            "value": round(salt, 1),
            "text": f"约 {_round_half(salt)} 克盐",
        }

    return analogies


def _range_text(value: float, unit: str) -> str:
    """Round to a friendly band instead of faking precision."""
    if value < 1:
        return f"不到 1 {unit}" if not unit.startswith("碗") else f"不到 1 碗米饭"
    if value < 10:
        return f"约 {_round_half(value)} {unit}"
    return f"约 {int(round(value))} {unit}"


def _round_half(value: float) -> str:
    """Round to the nearest 0.5 and drop a trailing .0 -- reads like a person."""
    rounded = round(value * 2) / 2
    return f"{rounded:g}"


def share_of_day(totals: dict) -> dict:
    """Share of the project's daily reference, given as a fraction word."""
    shares: dict[str, Any] = {}
    for field, reference in DAILY_REFERENCE.items():
        value = totals.get(field)
        if value is None or not reference:
            continue
        ratio = value / reference
        shares[field] = {"ratio": round(ratio, 3), "text": _ratio_text(ratio)}
    return shares


def _ratio_text(ratio: float) -> str:
    if ratio < 0.15:
        return "不到一天的两成"
    if ratio < 0.3:
        return "约占一天两成"
    if ratio < 0.4:
        return "约占一天三成"
    if ratio < 0.55:
        return "约占一天一半"
    if ratio < 0.75:
        return "约占一天六成"
    if ratio < 0.9:
        return "约占一天八成"
    return "接近一天的量"


# --------------------------------------------------------------------------
# neutral tags
# --------------------------------------------------------------------------


def describe_tags(totals: dict, price_cny: float | None = None) -> list[dict]:
    """Return neutral composition labels.

    A tag states *what the meal is made of*, never whether it is a good or bad
    choice. This keeps the output compliant and keeps the tone friendly.
    """
    tags: list[dict] = []
    kcal = totals.get("kcal")
    protein = totals.get("protein_g")
    carb = totals.get("carb_g")
    sodium = totals.get("sodium_mg")

    if kcal and protein is not None:
        density = protein / kcal * 100
        if density >= 6.0:
            tags.append({"label": "蛋白担当", "reason": f"每 100 千卡带 {density:.1f} 克蛋白"})

    if kcal and sodium is not None:
        sodium_density = sodium / kcal * 100
        if sodium_density >= 150:
            tags.append({"label": "钠值选手", "reason": f"每 100 千卡带 {sodium_density:.0f} 毫克钠"})

    if carb is not None and carb >= 50:
        tags.append({"label": "碳水主力", "reason": f"碳水 {carb:.0f} 克"})

    if kcal is not None and kcal >= 600:
        tags.append({"label": "顶饱型", "reason": f"热量 {kcal:.0f} 千卡"})

    if kcal is not None and kcal <= 300:
        tags.append({"label": "轻量选手", "reason": f"热量 {kcal:.0f} 千卡"})

    if price_cny is not None and price_cny <= 15:
        tags.append({"label": "钱包友好", "reason": f"约 ¥{price_cny:.1f}"})

    return tags


# --------------------------------------------------------------------------
# the single tip
# --------------------------------------------------------------------------


def one_tip(totals: dict, price_cny: float | None = None) -> str:
    """Return exactly one constructive sentence.

    Ordering is by how actionable the observation is, not by how alarming it
    sounds. Every branch points at a way to adjust, never at a verdict.
    """
    kcal = totals.get("kcal")
    protein = totals.get("protein_g")
    sodium = totals.get("sodium_mg")

    if sodium is not None and sodium >= 1200:
        return "钠这块占了今天不少，晚上挑清淡一点的就行。"
    if protein is not None and kcal and protein < 20 and kcal >= 500:
        return "想更耐饿的话，加一份带鸡肉或牛肉的单品，蛋白能明显提上去。"
    if kcal is not None and kcal >= 800:
        return "这顿份量不小，下一顿轻一点刚好平衡。"
    if protein is not None and kcal and protein / kcal * 100 >= 6:
        return "这单蛋白密度不错，值。"
    if protein is not None and protein < 15:
        return "蛋白偏少，配杯牛奶或加个蛋会更顶。"
    return "整体配得挺顺，不用特意调。"


# --------------------------------------------------------------------------
# constrained mode (optional)
# --------------------------------------------------------------------------


def solve(
    target: dict,
    consumed: Iterable[dict],
    candidates: Iterable[dict],
    *,
    max_items: int = 2,
    min_matched: int = 3,
) -> dict:
    """Enumerate combinations that fit the target. Deterministic, not clever.

    Candidates are small (a filtered menu), so exhaustive search is both fast
    and reproducible: ``C(25, 2) == 300``. No heuristics, no randomness.
    """
    consumed_totals = compute_totals(consumed)["totals"]
    usable = [
        item
        for item in candidates
        if item.get("nutrition") and item.get("basis", "per_serving") == "per_serving"
    ]

    if len(usable) < min_matched:
        return {
            "computable": False,
            "reason": "NOT_ENOUGH_MATCHED_ITEMS",
            "matched_candidates": len(usable),
            "required": min_matched,
            "consumed_totals": consumed_totals,
            "solutions": [],
            "flags": [
                {
                    "code": "LOW_COVERAGE",
                    "severity": "error",
                    "value": len(usable),
                    "limit": min_matched,
                }
            ],
        }

    solutions: list[dict] = []
    for size in range(1, max_items + 1):
        for combo in combinations(usable, size):
            result = _evaluate(combo, consumed_totals, target)
            if result is not None:
                solutions.append(result)

    solutions.sort(key=lambda item: (-item["score"]["protein_per_cny"], abs(item["score"]["kcal_gap"])))
    return {
        "computable": True,
        "matched_candidates": len(usable),
        "consumed_totals": consumed_totals,
        "solutions": solutions[:5],
        "evaluated": len(solutions),
        "flags": [],
    }


def _evaluate(combo: tuple, consumed_totals: dict, target: dict) -> dict | None:
    totals = {field: 0.0 for field in NUTRIENT_FIELDS}
    price = 0.0
    price_unknown = False

    for item in combo:
        for field in NUTRIENT_FIELDS:
            value = item["nutrition"].get(field)
            if value is not None:
                totals[field] += float(value)
        item_price = item.get("price_cny")
        if item_price is None:
            price_unknown = True
        else:
            price += float(item_price)

    violations: list[str] = []
    if target.get("kcal_max") is not None and totals["kcal"] > target["kcal_max"]:
        violations.append("KCAL_OVER")
    if target.get("protein_g_min") is not None and totals["protein_g"] < target["protein_g_min"]:
        violations.append("PROTEIN_SHORT")
    if target.get("sodium_mg_max") is not None and totals["sodium_mg"] > target["sodium_mg_max"]:
        violations.append("SODIUM_OVER")
    if target.get("carb_g_max") is not None and totals["carb_g"] > target["carb_g_max"]:
        violations.append("CARB_OVER")
    if target.get("budget_cny_max") is not None and not price_unknown and price > target["budget_cny_max"]:
        violations.append("BUDGET_OVER")

    if violations:
        return None

    kcal_target = target.get("kcal_max")
    gap = (kcal_target - totals["kcal"]) if kcal_target else 0.0
    protein_per_cny = (totals["protein_g"] / price) if price > 0 else 0.0

    return {
        "items": [
            {"name": item.get("name"), "meal_code": item.get("meal_code")} for item in combo
        ],
        "totals": {field: round(value, 1) for field, value in totals.items()},
        "price_cny": None if price_unknown else round(price, 2),
        "score": {
            "protein_per_cny": round(protein_per_cny, 3),
            "kcal_gap": round(gap, 1),
        },
        "violations": violations,
    }


# --------------------------------------------------------------------------
# card assembly
# --------------------------------------------------------------------------


def build_card(items: list[dict], price_cny: float | None = None) -> dict:
    if not items:
        return {
            "computable": False,
            "totals": {field: None for field in NUTRIENT_FIELDS},
            "analogies": {},
            "share_of_day": {},
            "tags": [],
            "tip": "",
            "coverage": {
                "items_total": 0,
                "items_with_nutrition": 0,
                "rate": 0.0,
                "missing_fields": [],
                "unknown_basis": [],
            },
            "flags": [
                {
                    "code": "NO_ITEMS",
                    "severity": "error",
                    "message": "还没有拿到餐品，先确认想吃哪几样。",
                }
            ],
            "basis": ANALOGY_BASIS,
            "daily_reference": DAILY_REFERENCE,
            "disclaimer_required": False,
            "disclaimer": DISCLAIMER,
        }

    aggregated = compute_totals(items)
    totals = aggregated["totals"]
    coverage = aggregated["coverage"]

    computable = not coverage["unknown_basis"]
    flags: list[dict] = []
    if not computable:
        flags.append(
            {
                "code": "UNIT_UNKNOWN",
                "severity": "error",
                "items": coverage["unknown_basis"],
                "message": "份量基准未确认，拒绝给出合计，避免算错。",
            }
        )
    if coverage["missing_fields"]:
        flags.append(
            {
                "code": "NUTRITION_UNMATCHED",
                "severity": "warn",
                "count": len(coverage["missing_fields"]),
                "items": sorted({item["name"] for item in coverage["missing_fields"]}),
            }
        )

    card = {
        "computable": computable,
        "totals": totals,
        "analogies": to_analogy(totals) if computable else {},
        "share_of_day": share_of_day(totals) if computable else {},
        "tags": describe_tags(totals, price_cny) if computable else [],
        "tip": one_tip(totals, price_cny) if computable else "",
        "coverage": coverage,
        "flags": flags,
        "basis": ANALOGY_BASIS,
        "daily_reference": DAILY_REFERENCE,
        "disclaimer_required": True,
        "disclaimer": DISCLAIMER,
    }
    return card


def render_markdown(card: dict, title: str = "这一单") -> str:
    """Render the card the way a person would actually read it."""
    if not card["computable"]:
        codes = {flag["code"] for flag in card.get("flags", [])}
        if "NO_ITEMS" in codes:
            return f"### {title}\n\n这一单还没落到具体餐品上。告诉我你想吃哪几样，我再翻成人话。\n"
        return "\n".join(
            [
                f"### {title}",
                "",
                "这几个餐品的份量基准还没确认，算合计会算错，所以先不给数字。",
                "可以换一个搭配，或者到门店确认份量后再来。",
            ]
        )

    totals = card["totals"]
    lines = [f"### {title}", ""]

    analogies = card["analogies"]
    pieces = [
        entry["text"] for entry in analogies.values() if entry.get("text")
    ]
    if pieces:
        lines.append("**换成你能感知的：** " + " ｜ ".join(pieces))
        lines.append("")

    lines.append("| 指标 | 数值 |")
    lines.append("| --- | --- |")
    for field in NUTRIENT_FIELDS:
        value = totals.get(field)
        if value is None:
            lines.append(f"| {NUTRIENT_LABELS[field]} | 未收录 |")
        else:
            label = NUTRIENT_LABELS[field]
            unit = NUTRIENT_UNITS[field]
            lines.append(f"| {label} | {value:g} {unit} |")
    lines.append("")

    tags = card.get("tags") or []
    if tags:
        lines.append("**这一单是：** " + " · ".join(f"`{tag['label']}`" for tag in tags))
        lines.append("")

    if card.get("tip"):
        lines.append(f"**一句提醒：** {card['tip']}")
        lines.append("")

    weak = [item for item in card["coverage"]["missing_fields"]]
    if weak:
        names = "、".join(sorted({item["name"] for item in weak}))
        lines.append(f"> 有餐品没在官方营养库里查到（{names}），这部分按「未收录」处理，没有估算。")
        lines.append("")

    if card.get("disclaimer_required"):
        lines.append(f"<sub>{card['disclaimer']}</sub>")
    return "\n".join(lines).rstrip() + "\n"


def render_solutions_markdown(outcome: dict, target: dict) -> str:
    """Render the optional constrained mode as a short, scannable list."""
    if not outcome.get("computable"):
        matched = outcome.get("matched_candidates", 0)
        return (
            "### 这个条件没凑出来\n\n"
            f"能对上营养数据的餐品只有 {matched} 个，不够凑。\n"
            "放宽一个条件我再试，或者换成「就想吃点啥」的模式，我先报数。\n"
        )

    conditions: list[str] = []
    if target.get("kcal_max") is not None:
        conditions.append(f"热量 ≤ {target['kcal_max']:g} 千卡")
    if target.get("protein_g_min") is not None:
        conditions.append(f"蛋白 ≥ {target['protein_g_min']:g} 克")
    if target.get("sodium_mg_max") is not None:
        conditions.append(f"钠 ≤ {target['sodium_mg_max']:g} 毫克")
    if target.get("budget_cny_max") is not None:
        conditions.append(f"价格 ≤ ¥{target['budget_cny_max']:g}")

    lines = ["### 按你的条件凑的", ""]
    if conditions:
        lines.append("**条件：** " + " · ".join(conditions))
        lines.append("")

    lines.append("| 组合 | 热量 | 蛋白 | 钠 | 价格 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for solution in outcome["solutions"]:
        names = " + ".join(item["name"] for item in solution["items"])
        totals = solution["totals"]
        price = f"¥{solution['price_cny']:g}" if solution["price_cny"] is not None else "未获取"
        lines.append(
            f"| {names} | {totals['kcal']:g} 千卡 | {totals['protein_g']:g} 克 "
            f"| {totals['sodium_mg']:g} 毫克 | {price} |"
        )
    lines.append("")

    if outcome["solutions"]:
        best = outcome["solutions"][0]
        best_names = " + ".join(item["name"] for item in best["items"])
        lines.append(f"**最划算的一单：** {best_names}，每块钱能换 {best['score']['protein_per_cny']:g} 克蛋白。")
        lines.append("")

    lines.append(f"<sub>{DISCLAIMER}</sub>")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a meal card from nutrition data")
    parser.add_argument("--input", required=True, help="JSON file with items and optional target")
    parser.add_argument("--format", choices=("json", "md"), default="json")
    parser.add_argument("--solve", action="store_true", help="run constrained mode")
    parser.add_argument("--title", default="这一单")
    args = parser.parse_args(argv)

    with open(args.input, encoding="utf-8") as handle:
        payload = json.load(handle)

    items = payload.get("items") or []
    price = payload.get("price_cny")
    card = build_card(items, price)

    if args.solve:
        target = payload.get("target") or {}
        outcome = solve(target, payload.get("consumed") or [], payload.get("candidates") or [])
        card["solve"] = outcome

    if args.format == "md":
        if args.solve and "solve" in card:
            sys.stdout.write(render_solutions_markdown(card["solve"], payload.get("target") or {}))
        else:
            sys.stdout.write(render_markdown(card, args.title))
    else:
        json.dump(card, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")

    if args.solve:
        return 3 if not card["solve"]["computable"] else 0
    return 0 if card["computable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
