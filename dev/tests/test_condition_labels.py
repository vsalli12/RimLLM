import unittest
from prompt_constructor import condition_change


class ConditionLabelsTests(unittest.TestCase):
    def test_prefers_display_label_and_preserves_character_name(self):
        before = {"health": []}
        after = {"health": [{"def": "ToxicBuildup", "label": "<color=red>toxic buildup (initial)</color>", "part": None}]}
        result = condition_change(before, after, "McDonald")
        self.assertIn("McDonald: new health conditions: toxic buildup (initial)", result)
        self.assertNotIn("ToxicBuildup", result)
        self.assertNotIn("<color", result)
        self.assertIn("conditions no longer recorded: toxic buildup (initial)", condition_change(after, before, "McDonald"))

    def test_fallback_splits_ids_without_changing_comparison(self):
        before = {"health": []}
        after = {"health": [{"def": "BloodLoss", "part": None}], "mental_state": "Wander_OwnRoom"}
        result = condition_change(before, after, "Chaz")
        self.assertIn("blood loss", result)
        self.assertIn("wander own room", result)
        changed_label = {**after, "health": [{"def": "BloodLoss", "label": "blood loss (minor)", "part": None}]}
        self.assertEqual(condition_change(after, changed_label, "Chaz"), "")


if __name__ == "__main__":
    unittest.main()
