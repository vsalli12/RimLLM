import unittest
from prompt_constructor import Event, compact_incidents


class InjurySourceTests(unittest.TestCase):
    def render(self, health, attacker=False):
        participants = [{"role": "subject", "pawn_id": "p"}]
        if attacker:
            participants.append({"role": "attacker", "pawn_id": "a"})
        record = dict(type="pawn.injured", tick_of_day=0, map_id=0,
                      participants=participants, data={
                          "details": {"injury": "Gunshot", "part": "liver"},
                          "subject_state": {"health": health}})
        return compact_incidents([Event(record, {"p": "Chaz", "a": "Shift"})])[1][0]

    def test_source_label_and_attacker_are_preserved(self):
        wound = dict(definition="unused", label="Gunshot (ancient defender turret gun)", part="liver")
        wound["def"] = "Gunshot"
        self.assertIn("Gunshot (ancient defender turret gun) to liver", self.render([wound]))
        self.assertIn("injured by Shift", self.render([wound], attacker=True))

    def test_missing_unrelated_or_ambiguous_wounds_do_not_invent_source(self):
        wound = {"def": "Gunshot", "label": "Gunshot (turret)", "part": "liver"}
        for health in ([], [{**wound, "part": "leg"}], [wound, {**wound, "label": "Gunshot (rifle)"}]):
            with self.subTest(health=health):
                text = self.render(health)
                self.assertIn("gunshot to liver", text)
                self.assertNotIn("turret", text)
                self.assertNotIn("rifle", text)


if __name__ == "__main__":
    unittest.main()
