#!/usr/bin/env python3
"""Tests for combo decomposition (pure functions, no network)."""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from decompose import default_components, sum_components  # noqa: E402
from normalize import NameMatcher  # noqa: E402

DETAIL = {
    "code": "9900005456",
    "name": "麦辣鸡腿汉堡三件套",
    "rounds": [
        {
            "id": 1,
            "name": "麦辣鸡腿汉堡",
            "choices": [
                {"code": "1440", "name": "麦辣鸡腿汉堡", "isDefault": 1},
            ],
        },
        {
            "id": 2,
            "name": "选择套餐内小食",
            "choices": [
                {"code": "4810", "name": "中薯条", "isDefault": 1},
                {"code": "4820", "name": "大薯条", "isDefault": 0},
            ],
        },
        {
            "id": 3,
            "name": "选择套餐内饮料",
            "choices": [
                {"code": "3050", "name": "可乐中杯", "isDefault": 1},
            ],
        },
    ],
}


def make_matcher() -> tuple[NameMatcher, dict]:
    matcher = NameMatcher()
    values = {
        "麦辣鸡腿汉堡": {"kcal": 500, "protein_g": 22, "fat_g": 25, "carb_g": 46, "sodium_mg": 1150, "calcium_mg": 90},
        "中薯条": {"kcal": 289, "protein_g": 4, "fat_g": 12, "carb_g": 38, "sodium_mg": 165, "calcium_mg": 18},
        "可乐中杯": {"kcal": 147, "protein_g": 0, "fat_g": 0, "carb_g": 36, "sodium_mg": 0, "calcium_mg": 10},
    }
    for name in values:
        matcher.add(name, name)
    return matcher, values


class DefaultComponentsTests(unittest.TestCase):
    def test_picks_only_default_choices(self) -> None:
        components = default_components(DETAIL)
        names = [component["name"] for component in components]
        self.assertEqual(names, ["麦辣鸡腿汉堡", "中薯条", "可乐中杯"])

    def test_falls_back_to_included_quantity_when_no_is_default(self) -> None:
        detail = {
            "rounds": [
                {"choices": [{"name": "a", "quantity": 0}, {"name": "b", "quantity": 1}]}
            ]
        }
        self.assertEqual([component["name"] for component in default_components(detail)], ["b"])


class SumComponentsTests(unittest.TestCase):
    def test_sums_all_default_components(self) -> None:
        matcher, values = make_matcher()
        components = default_components(DETAIL)
        result = sum_components(components, matcher, values)
        self.assertTrue(result["complete"])
        self.assertEqual(result["totals"]["kcal"], 936.0)  # 500 + 289 + 147
        self.assertEqual(result["totals"]["protein_g"], 26.0)

    def test_missing_component_marks_incomplete(self) -> None:
        matcher, values = make_matcher()
        result = sum_components([{"name": "麦辣鸡腿汉堡"}, {"name": "龙焰鸡腿堡"}], matcher, values)
        self.assertFalse(result["complete"])
        self.assertEqual([item["name"] for item in result["missing"]], ["龙焰鸡腿堡"])
        self.assertEqual(result["totals"]["kcal"], 500.0)  # only the matched one counts


if __name__ == "__main__":
    unittest.main()
