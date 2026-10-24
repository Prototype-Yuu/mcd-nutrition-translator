#!/usr/bin/env python3
"""Name normalization and nutrition <-> menu alignment.

The McDonald's China MCP server exposes two data sources that share **no join
key**: ``list-nutrition-foods`` returns nutrition rows keyed by food *name*,
while ``query-meals`` returns menu items keyed by a meal *code* and no name
(the name requires a second ``query-meal-detail`` call). Any attempt to build a
nutrition ledger has to bridge that gap by name, and the two vocabularies do not
agree: menu names carry size/quantity qualifiers and price suffixes, nutrition
rows carry their own serving descriptions.

This module makes the bridge explicit and *auditable*:

* every match records the tier that produced it (``method``) and a score;
* ambiguous matches are reported as ambiguous instead of picking one;
* nothing is guessed — an unmatched item stays unmatched.

Standard library only.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

# --------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------

_PAREN = re.compile(r"[（(][^（）()]{0,24}[)）]")
_PUNCT = re.compile(r"[\s\-_·•・,，.。、:：;；!！?？“”\"'‘’《》\[\]【】/+＋]")
# Trailing qualifiers that describe packaging or portion, not identity.
_QUALIFIERS = (
    "单点",
    "套餐",
    "中号",
    "大号",
    "小号",
    "中杯",
    "大杯",
    "小杯",
    "中份",
    "大份",
    "小份",
    "中薯",
    "大薯",
    "小薯",
    "1块",
    "1份",
    "1个",
    "2块",
    "2份",
    "2个",
    "块",
    "份",
    "个",
    "杯",
)
#: Single-leading size characters. Only one is removed, and only when the
#: remainder keeps at least two characters (see ``strip_qualifiers``).
_PREFIX_QUALIFIERS = ("中", "大", "小")


def normalize_name(value: Any) -> str:
    """Fold a display name into a comparison key.

    NFKC collapses full-width forms, lowercasing removes case noise, and the
    punctuation pass removes the spacing variants that differ between the
    nutrition table and the menu.
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = _PAREN.sub("", text)
    text = _PUNCT.sub("", text)
    return text


def strip_qualifiers(normalized: str) -> str:
    """Remove size / quantity / packaging tokens, longest match first.

    Prefix stripping is limited to a single size character and requires the
    remainder to stay at least two characters long, so that a real word is
    never reduced to a single character ("小食" must not become "食").
    """
    out = normalized
    changed = True
    while changed and out:
        changed = False
        for qualifier in _QUALIFIERS:
            if out.endswith(qualifier) and len(out) > len(qualifier):
                out = out[: -len(qualifier)]
                changed = True
                break
        if changed:
            continue
        for prefix in _PREFIX_QUALIFIERS:
            if out.startswith(prefix) and len(out) - len(prefix) >= 2:
                out = out[len(prefix) :]
                changed = True
                break
    return out


def _bigrams(text: str) -> set[str]:
    if len(text) <= 2:
        return {text} if text else set()
    return {text[i : i + 2] for i in range(len(text) - 1)}


def _similarity(left: str, right: str) -> float:
    """Dice coefficient over character bigrams; cheap and order-sensitive."""
    a, b = _bigrams(left), _bigrams(right)
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------


@dataclass
class MatchResult:
    status: str  # "matched" | "ambiguous" | "unmatched"
    method: str = ""
    score: float = 0.0
    key: str | None = None
    candidates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = {
            "status": self.status,
            "method": self.method,
            "score": round(self.score, 3),
        }
        if self.key is not None:
            payload["key"] = self.key
        if self.candidates:
            payload["candidates"] = self.candidates
        return payload


class NameMatcher:
    """Index nutrition rows by name and match menu names against them.

    Tiers are tried in order and the first tier that yields a hit wins, so a
    weak fuzzy hit never overrides an exact one. Ties inside a tier are
    reported as ``ambiguous`` — the caller decides, the matcher does not.
    """

    TIERS = ("exact", "stripped", "alias", "containment", "fuzzy")

    def __init__(self, aliases: dict[str, str] | None = None, fuzzy_threshold: float = 0.82):
        self._exact: dict[str, list[str]] = {}
        self._stripped: dict[str, list[str]] = {}
        self._display: dict[str, str] = {}
        self._aliases = {normalize_name(k): normalize_name(v) for k, v in (aliases or {}).items()}
        self.fuzzy_threshold = fuzzy_threshold

    # -- index -------------------------------------------------------------

    def add(self, key: str, display_name: str | None = None) -> None:
        normalized = normalize_name(display_name or key)
        if not normalized:
            return
        self._exact.setdefault(normalized, []).append(key)
        self._stripped.setdefault(strip_qualifiers(normalized), []).append(key)
        self._display.setdefault(key, display_name or key)

    def extend(self, rows: Iterable[tuple[str, str | None]]) -> None:
        for key, display in rows:
            self.add(key, display)

    def __len__(self) -> int:
        return len(self._display)

    # -- match -------------------------------------------------------------

    def match(self, name: str) -> MatchResult:
        normalized = normalize_name(name)
        if not normalized:
            return MatchResult("unmatched", "empty")

        exact = self._resolve(self._exact.get(normalized), "exact", 1.0)
        if exact:
            return exact

        stripped = self._resolve(self._stripped.get(strip_qualifiers(normalized)), "stripped", 0.95)
        if stripped:
            return stripped

        alias_target = self._aliases.get(normalized)
        if alias_target:
            # An alias may point at a display name, so try the exact index and
            # then the qualifier-stripped index before giving up.
            aliased = self._resolve(self._exact.get(alias_target), "alias", 0.92)
            if aliased:
                return aliased
            aliased = self._resolve(
                self._stripped.get(strip_qualifiers(alias_target)), "alias", 0.9
            )
            if aliased:
                return aliased

        contained = self._containment(normalized)
        if contained:
            return contained

        return self._fuzzy(normalized)

    def _resolve(self, keys: list[str] | None, method: str, score: float) -> MatchResult | None:
        if not keys:
            return None
        unique = sorted(set(keys))
        if len(unique) == 1:
            return MatchResult("matched", method, score, key=unique[0])
        return MatchResult("ambiguous", method, score, candidates=unique)

    def _containment(self, normalized: str) -> MatchResult | None:
        needle = strip_qualifiers(normalized)
        # A 3-character name such as "鸡腿堡" is a category, not an identity.
        # Requiring length >= 4 keeps containment from swallowing the real
        # product ("麦辣鸡腿堡") and from inventing a match for a generic word.
        if len(needle) < 4:
            return None
        hits: list[tuple[str, int]] = []
        for indexed, keys in self._stripped.items():
            probe = strip_qualifiers(indexed)
            if not probe or probe == needle:
                continue
            if probe in needle or needle in probe:
                if abs(len(probe) - len(needle)) <= 2:
                    hits.extend((key, abs(len(probe) - len(needle))) for key in keys)
        if not hits:
            return None
        best_gap = min(gap for _, gap in hits)
        best = sorted({key for key, gap in hits if gap == best_gap})
        score = 0.9 - 0.05 * best_gap
        if len(best) == 1:
            return MatchResult("matched", "containment", score, key=best[0])
        return MatchResult("ambiguous", "containment", score, candidates=best)

    def _fuzzy(self, normalized: str) -> MatchResult:
        needle = strip_qualifiers(normalized)
        if len(needle) < 3:
            return MatchResult("unmatched", "fuzzy")
        scored: list[tuple[float, str]] = []
        for indexed, keys in self._stripped.items():
            probe = strip_qualifiers(indexed)
            if not probe:
                continue
            score = _similarity(needle, probe)
            if score >= self.fuzzy_threshold:
                scored.extend((score, key) for key in keys)
        if not scored:
            return MatchResult("unmatched", "fuzzy")
        top = max(score for score, _ in scored)
        best = sorted({key for score, key in scored if abs(score - top) < 1e-9})
        if len(best) == 1:
            return MatchResult("matched", "fuzzy", top, key=best[0])
        return MatchResult("ambiguous", "fuzzy", top, candidates=best)


# --------------------------------------------------------------------------
# adapters
# --------------------------------------------------------------------------

#: Field-name candidates for nutrition rows. The real key names are confirmed
#: against ``list-nutrition-foods`` at run time; aliases are kept so that a
#: server-side rename degrades into an unmapped-field report instead of a
#: silently wrong number.
NUTRITION_FIELDS: dict[str, tuple[str, ...]] = {
    "kcal": ("kcal", "calorie", "calories", "energyKcal", "energy_kcal", "energy"),
    "protein_g": ("protein", "proteinG", "protein_g", "proteinContent"),
    "fat_g": ("fat", "fatG", "fat_g", "fatContent"),
    "carb_g": ("carbohydrate", "carbohydrateG", "carb", "carbs", "carb_g", "carbohydrateContent"),
    "sodium_mg": ("sodium", "sodiumMg", "sodium_mg", "sodiumContent"),
    "calcium_mg": ("calcium", "calciumMg", "calcium_mg", "calciumContent"),
}
NUTRITION_ENERGY_KJ = ("energyKj", "energy_kj", "kj", "energyKJ")

NAME_FIELDS = ("name", "foodName", "mealName", "productName", "title", "cnName")
CODE_FIELDS = ("code", "mealCode", "productCode", "id", "sku", "itemCode")


def _first_key(row: dict, candidates: tuple[str, ...]) -> tuple[str | None, Any]:
    for key in candidates:
        if key in row and row[key] is not None:
            return key, row[key]
    return None, None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(match.group()) if match else None


def adapt_nutrition_row(row: dict) -> dict:
    """Map one raw nutrition row into the normalised record shape.

    Unmapped fields are reported, never filled in. ``unit_hint`` keeps whatever
    serving description the server returned so that a later step can refuse to
    sum rows whose basis is unknown.
    """
    name_key, name = _first_key(row, NAME_FIELDS)
    nutrition: dict[str, float] = {}
    unmapped: list[str] = []
    for field_name, candidates in NUTRITION_FIELDS.items():
        _, raw_value = _first_key(row, candidates)
        number = _to_float(raw_value)
        if number is None:
            unmapped.append(field_name)
        else:
            nutrition[field_name] = number

    _, energy_kj = _first_key(row, NUTRITION_ENERGY_KJ)
    unit_hint = None
    for key in ("description", "nutritionDescription", "serving", "unit", "spec"):
        if row.get(key):
            unit_hint = str(row[key])
            break

    return {
        "name": str(name) if name is not None else "",
        "name_key": name_key,
        "nutrition": nutrition or None,
        "energy_kj": _to_float(energy_kj),
        "unit_hint": unit_hint,
        "unmapped_fields": unmapped,
        "raw_keys": sorted(row.keys()),
    }


def adapt_menu_row(row: dict) -> dict:
    _, name = _first_key(row, NAME_FIELDS)
    _, code = _first_key(row, CODE_FIELDS)
    return {
        "meal_code": str(code) if code is not None else None,
        "name": str(name) if name is not None else "",
        "raw_keys": sorted(row.keys()),
    }


# --------------------------------------------------------------------------
# coverage report
# --------------------------------------------------------------------------


def align(nutrition_rows: list[dict], menu_rows: list[dict], aliases: dict[str, str] | None = None) -> dict:
    """Align a menu against a nutrition table and report the hit rate."""
    matcher = NameMatcher(aliases=aliases)
    for row in nutrition_rows:
        key = row.get("name") or ""
        if key:
            matcher.add(key, key)

    results: list[dict] = []
    for row in menu_rows:
        result = matcher.match(row.get("name") or "")
        results.append(
            {
                "meal_code": row.get("meal_code"),
                "name": row.get("name"),
                **result.to_dict(),
            }
        )

    counts = {"matched": 0, "ambiguous": 0, "unmatched": 0}
    by_method: dict[str, int] = {}
    for item in results:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
        if item["status"] == "matched":
            by_method[item["method"]] = by_method.get(item["method"], 0) + 1

    total = len(menu_rows)
    return {
        "nutrition_total": len(nutrition_rows),
        "menu_total": total,
        "matched": counts["matched"],
        "ambiguous": counts["ambiguous"],
        "unmatched": counts["unmatched"],
        "rate": round(counts["matched"] / total, 4) if total else 0.0,
        "by_method": by_method,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Align nutrition rows to menu rows by name")
    parser.add_argument("--nutrition", required=True, help="JSON file: list of nutrition rows")
    parser.add_argument("--menu", required=True, help="JSON file: list of menu rows")
    parser.add_argument("--aliases", help="optional JSON file: {menu name: nutrition name}")
    parser.add_argument("--out", help="write the full report here instead of stdout")
    args = parser.parse_args(argv)

    with open(args.nutrition, encoding="utf-8") as handle:
        nutrition_raw = json.load(handle)
    with open(args.menu, encoding="utf-8") as handle:
        menu_raw = json.load(handle)
    aliases = None
    if args.aliases:
        with open(args.aliases, encoding="utf-8") as handle:
            aliases = json.load(handle)

    nutrition_rows = [adapt_nutrition_row(row) for row in nutrition_raw]
    menu_rows = [adapt_menu_row(row) for row in menu_raw]
    report = align(nutrition_rows, menu_rows, aliases)

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
