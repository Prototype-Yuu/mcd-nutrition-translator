#!/usr/bin/env python3
"""Unit tests for the meal card.

Three behaviours matter more than the happy path:
1. a missing field is reported, never imputed;
2. an unknown serving basis blocks the total instead of producing a wrong one;
3. output copy never grades a meal as healthy/unhealthy (competition rule).
"""

from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from mealcard import (  # noqa: E402
    ANALOGY_BASIS,
    build_card,
    compute_totals,
    describe_tags,
    one_tip,
    render_markdown,
    solve,
    to_analogy,
)

FIXTURES = os.path.join(ROOT, "tests", "fixtures")

#: Words that would turn a description into a verdict. The competition rules
#: forbid disparaging the brand, and a "healthy/unhealthy" judgement is both
#: a compliance risk and bad product copy.
FORBIDDEN_COPY = ("不健康", "垃圾食品", "超标", "有害", "减肥", "瘦身", "低GI", "无糖", "低钠")


def load(name: str) -> dict:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return json.load(handle)


class TotalsTests(unittest.TestCase):
    def test_sums_all_six_nutrients(self) -> None:
        payload = load("card-simple.json")
        result = compute_totals(payload["items"])
        self.assertEqual(result["totals"]["kcal"], 1040.0)
        self.assertEqual(result["totals"]["protein_g"], 29.0)
        self.assertEqual(result["totals"]["sodium_mg"], 1280.0)
        self.assertEqual(result["coverage"]["rate"], 1.0)

    def test_missing_nutrition_row_is_reported_not_guessed(self) -> None:
        payload = load("card-unit-unknown.json")
        result = compute_totals(payload["items"])
        missing_names = {item["name"] for item in result["coverage"]["missing_fields"]}
        self.assertIn("龙焰芝士棒鸡腿堡三件套", missing_names)
        # Only the one known row may contribute.
        self.assertEqual(result["totals"]["kcal"], 550.0)

    def test_absent_field_is_none_not_zero(self) -> None:
        result = compute_totals(
            [{"name": "x", "basis": "per_serving", "nutrition": {"kcal": 100}}]
        )
        self.assertIsNone(result["totals"]["sodium_mg"])
        self.assertEqual(result["counted_fields"]["sodium_mg"], 0)


class AnalogyTests(unittest.TestCase):
    def test_rice_bowl_conversion(self) -> None:
        analogies = to_analogy({"kcal": 1040.0})
        self.assertAlmostEqual(analogies["rice_bowls"]["value"], 5.2, places=1)
        self.assertIn("碗米饭", analogies["rice_bowls"]["text"])

    def test_egg_conversion(self) -> None:
        analogies = to_analogy({"protein_g": 29.0})
        self.assertAlmostEqual(analogies["eggs"]["value"], 4.8, places=1)

    def test_salt_conversion_uses_chemistry(self) -> None:
        analogies = to_analogy({"sodium_mg": 1280.0})
        self.assertAlmostEqual(analogies["salt_grams"]["value"], 3.2, places=1)

    def test_no_numbers_no_analogy(self) -> None:
        self.assertEqual(to_analogy({"kcal": None}), {})

    def test_basis_is_disclosed(self) -> None:
        # The conversion must ship with its assumptions, not hide them.
        self.assertIn("rice_bowl_kcal", ANALOGY_BASIS)


class TagTests(unittest.TestCase):
    def test_carb_and_filling_tags(self) -> None:
        labels = {tag["label"] for tag in describe_tags({"kcal": 1040.0, "protein_g": 29.0, "carb_g": 127.0, "sodium_mg": 1280.0})}
        self.assertIn("碳水主力", labels)
        self.assertIn("顶饱型", labels)

    def test_high_density_gets_protein_tag(self) -> None:
        labels = {tag["label"] for tag in describe_tags({"kcal": 300.0, "protein_g": 30.0})}
        self.assertIn("蛋白担当", labels)

    def test_tags_contain_no_verdict_words(self) -> None:
        payload = load("card-simple.json")
        card = build_card(payload["items"], payload.get("price_cny"))
        copy = " ".join(tag["label"] + tag["reason"] for tag in card["tags"]) + card["tip"]
        for word in FORBIDDEN_COPY:
            self.assertNotIn(word, copy, f"forbidden verdict word in output: {word}")


class TipTests(unittest.TestCase):
    def test_exactly_one_sentence(self) -> None:
        tip = one_tip({"kcal": 1040.0, "protein_g": 29.0, "sodium_mg": 1280.0})
        self.assertEqual(tip.count("。"), 1)

    def test_high_sodium_points_at_evening_not_at_shame(self) -> None:
        tip = one_tip({"kcal": 900.0, "protein_g": 30.0, "sodium_mg": 1500.0})
        self.assertIn("晚上", tip)

    def test_low_protein_points_at_an_addition(self) -> None:
        tip = one_tip({"kcal": 600.0, "protein_g": 12.0, "sodium_mg": 500.0})
        self.assertIn("蛋白", tip)


class UnknownBasisTests(unittest.TestCase):
    def test_unknown_basis_blocks_the_card(self) -> None:
        payload = load("card-unit-unknown.json")
        card = build_card(payload["items"])
        self.assertFalse(card["computable"])
        codes = {flag["code"] for flag in card["flags"]}
        self.assertIn("UNIT_UNKNOWN", codes)

    def test_markdown_refuses_instead_of_showing_a_wrong_total(self) -> None:
        payload = load("card-unit-unknown.json")
        text = render_markdown(build_card(payload["items"]))
        self.assertIn("先不给数字", text)


class SolveTests(unittest.TestCase):
    def test_solutions_respect_every_constraint(self) -> None:
        payload = load("card-solve.json")
        target = payload["target"]
        outcome = solve(target, payload["consumed"], payload["candidates"])
        self.assertTrue(outcome["computable"])
        self.assertGreaterEqual(len(outcome["solutions"]), 1)
        for solution in outcome["solutions"]:
            totals = solution["totals"]
            self.assertLessEqual(totals["kcal"], target["kcal_max"])
            self.assertGreaterEqual(totals["protein_g"], target["protein_g_min"])
            self.assertLessEqual(totals["sodium_mg"], target["sodium_mg_max"])
            self.assertLessEqual(solution["price_cny"], target["budget_cny_max"])

    def test_deterministic_between_runs(self) -> None:
        payload = load("card-solve.json")
        first = solve(payload["target"], payload["consumed"], payload["candidates"])
        second = solve(payload["target"], payload["consumed"], payload["candidates"])
        self.assertEqual(first["solutions"], second["solutions"])

    def test_too_few_candidates_fails_loudly(self) -> None:
        outcome = solve({"kcal_max": 600}, [], [], min_matched=5)
        self.assertFalse(outcome["computable"])
        self.assertEqual(outcome["reason"], "NOT_ENOUGH_MATCHED_ITEMS")

    def test_unmatched_candidate_is_skipped_not_priced(self) -> None:
        candidates = [{"name": "x", "nutrition": None, "price_cny": 10.0}] + load("card-solve.json")["candidates"]
        outcome = solve({"protein_g_min": 22}, [], candidates)
        names = {item["name"] for solution in outcome["solutions"] for item in solution["items"]}
        self.assertNotIn("x", names)


if __name__ == "__main__":
    unittest.main()
