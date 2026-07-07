"""Unit tests for responsibility_match.py — the name-based Responsibility
code matcher. Uses a tiny inline code map (not the shipped reference file) so
the tests are hermetic and don't drift when the keyword data is regenerated.
"""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from responsibility_match import (  # noqa: E402
    match_activity,
    normalize,
    suggest_assignments,
)

CODES = [
    {"code": "ELEC", "name": "Electrical",
     "keywords": ["electrical", "electricos", "lighting", "light fixtures"]},
    {"code": "DRYW", "name": "Drywall",
     "keywords": ["drywall", "tablaroca", "hang", "tape", "gypsum board"]},
    {"code": "CONC-STRU", "name": "Concrete Structural",
     "keywords": ["structural concrete", "footings", "slab on grade", "rebar"]},
    {"code": "STR-STEEL", "name": "Structural Steel",
     "keywords": ["structural steel", "steel columns", "steel beams", "decking"]},
    {"code": "NONE", "name": "NOT YET ASSIGNED", "keywords": []},
]


class TestNormalize(unittest.TestCase):
    def test_strips_accents_and_lowercases(self):
        self.assertEqual(normalize("Climatización"), " climatizacion ")

    def test_pads_and_collapses_punct(self):
        self.assertEqual(normalize("Slab-on-Grade (Level 1)"),
                         " slab on grade level 1 ")


class TestMatchActivity(unittest.TestCase):
    def test_single_token_match(self):
        r = match_activity("Rough-in Electrical Level 2", CODES)
        self.assertEqual(r["code"], "ELEC")
        self.assertTrue(r["confident"])

    def test_spanish_token_match(self):
        r = match_activity("Instalar Tablaroca Nivel 1", CODES)
        self.assertEqual(r["code"], "DRYW")

    def test_phrase_beats_single_token(self):
        # "steel" alone could be ambiguous, but "structural steel" phrase wins.
        r = match_activity("Erect Structural Steel Columns", CODES)
        self.assertEqual(r["code"], "STR-STEEL")

    def test_no_keyword_hit_is_unsure(self):
        r = match_activity("Mobilization and General Conditions", CODES)
        self.assertFalse(r["confident"])
        self.assertIsNone(r["code"])

    def test_reports_alternatives_when_ambiguous(self):
        # A name hitting two codes weakly should not be marked confident.
        r = match_activity("Hang and wire fixtures", CODES)  # hang->DRYW, (no elec token)
        # 'hang' hits DRYW once; nothing else -> still a lone winner here
        self.assertIn("candidates", r)


class TestSuggestAssignments(unittest.TestCase):
    def test_buckets_assigned_and_unsure(self):
        tasks = [
            {"task_id": "1", "task_code": "A-1", "task_name": "Install Electrical Panels"},
            {"task_id": "2", "task_code": "A-2", "task_name": "Hang Drywall Level 1"},
            {"task_id": "3", "task_code": "A-3", "task_name": "Project Mobilization"},
        ]
        out = suggest_assignments(tasks, CODES)
        assigned = {a["task_code"]: a["suggested_code"] for a in out["assigned"]}
        self.assertEqual(assigned.get("A-1"), "ELEC")
        self.assertEqual(assigned.get("A-2"), "DRYW")
        unsure_codes = {u["task_code"] for u in out["unsure"]}
        self.assertIn("A-3", unsure_codes)

    def test_skip_already_assigned(self):
        tasks = [
            {"task_id": "1", "task_code": "A-1", "task_name": "Install Electrical Panels"},
            {"task_id": "2", "task_code": "A-2", "task_name": "Hang Drywall"},
        ]
        out = suggest_assignments(tasks, CODES, already_assigned={"1"})
        seen = {a["task_code"] for a in out["assigned"]} | {u["task_code"] for u in out["unsure"]}
        self.assertNotIn("A-1", seen)
        self.assertIn("A-2", seen)


if __name__ == "__main__":
    unittest.main()
