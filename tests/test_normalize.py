#!/usr/bin/env python3
"""Unit tests for name normalization and menu alignment.

The interesting tests here are the *negative* ones: a matcher that never
mismatches is worth more than one that matches everything, because a wrong
nutrition row silently corrupts every number downstream.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from normalize import (  # noqa: E402
    NameMatcher,
    align,
    normalize_name,
    strip_qualifiers,
)


class NormalizationTests(unittest.TestCase):
    def test_strips_parenthetical_qualifier(self) -> None:
        self.assertEqual(normalize_name("巨无霸（单点）"), "巨无霸")

    def test_folds_fullwidth_and_case(self) -> None:
        self.assertEqual(normalize_name("ＭｃＣａｆｅ 拿铁"), "mccafe拿铁")

    def test_strip_size_tokens(self) -> None:
        self.assertEqual(strip_qualifiers("中薯条"), "薯条")
        self.assertEqual(strip_qualifiers("可口可乐大杯"), "可口可乐")

    def test_does_not_strip_to_empty(self) -> None:
        self.assertEqual(strip_qualifiers("中"), "中")

    def test_empty_input(self) -> None:
        self.assertEqual(normalize_name(None), "")


class MatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matcher = NameMatcher()
        for name in ("巨无霸", "麦辣鸡腿堡", "麦香鱼", "中薯条", "猪柳蛋麦满分"):
            self.matcher.add(name, name)

    def test_exact(self) -> None:
        result = self.matcher.match("巨无霸")
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.method, "exact")

    def test_stripped_qualifier_still_matches(self) -> None:
        result = self.matcher.match("巨无霸（单点）")
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.key, "巨无霸")

    def test_generic_category_does_not_match_a_product(self) -> None:
        # "鸡腿堡" is a category. Guessing 麦辣鸡腿堡 from it would be wrong.
        result = self.matcher.match("鸡腿堡")
        self.assertNotEqual(result.status, "matched")

    def test_unrelated_names_do_not_match(self) -> None:
        # The deliberate mismatch fixture: shares "蛋" and "风" but is a
        # different product entirely.
        result = self.matcher.match("北非蛋风味卷")
        self.assertNotEqual(result.status, "matched")

    def test_duplicate_keys_are_ambiguous_not_guessed(self) -> None:
        matcher = NameMatcher()
        matcher.add("a", "香芋派")
        matcher.add("b", "香芋派（大）")
        result = matcher.match("香芋派")
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(sorted(result.candidates), ["a", "b"])

    def test_alias_table_resolves_known_rename(self) -> None:
        matcher = NameMatcher(aliases={"扭扭薯条": "薯条"})
        matcher.add("薯条", "中薯条")
        result = matcher.match("扭扭薯条")
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.method, "alias")

    def test_empty_name_is_unmatched(self) -> None:
        self.assertEqual(self.matcher.match("").status, "unmatched")


class AlignTests(unittest.TestCase):
    def test_coverage_counts_add_up(self) -> None:
        nutrition = [{"name": "巨无霸"}, {"name": "麦香鱼"}]
        menu = [
            {"meal_code": "1", "name": "巨无霸"},
            {"meal_code": "2", "name": "麦香鱼（单点）"},
            {"meal_code": "3", "name": "龙焰芝士棒鸡腿堡三件套"},
        ]
        report = align(nutrition, menu)
        self.assertEqual(report["menu_total"], 3)
        self.assertEqual(report["matched"], 2)
        self.assertEqual(report["unmatched"], 1)
        self.assertEqual(report["matched"] + report["ambiguous"] + report["unmatched"], 3)

    def test_empty_menu_is_zero_not_error(self) -> None:
        report = align([{"name": "巨无霸"}], [])
        self.assertEqual(report["rate"], 0.0)

    def test_report_keeps_per_item_trace(self) -> None:
        report = align([{"name": "巨无霸"}], [{"meal_code": "1", "name": "巨无霸"}])
        self.assertEqual(report["results"][0]["method"], "exact")


if __name__ == "__main__":
    unittest.main()
