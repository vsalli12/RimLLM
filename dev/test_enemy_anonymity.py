import copy
import unittest
from prompt_constructor import build_document


def event(seq, kind, data, participants=None):
    return dict(event_id=str(seq), sequence=seq, game_day=1, tick=seq,
                tick_of_day=seq, playthrough_id="game", session_id="session",
                type=kind, data=data, participants=participants or [],
                map_id=0, diary_carrier_id=None)


def profile(seq, sid, name, **fields):
    return event(seq, "pawn.profile", dict(pawn_id=sid, name=name,
                 species="human", gender="Female", spawned=True, **fields))


class EnemyAnonymityTests(unittest.TestCase):
    def test_enemy_names_hidden_in_combat_targets_and_memory(self):
        records = [profile(1, "p", "Chaz", is_colonist=True),
                   profile(2, "a", "Shift", hostile_to_player=True),
                   profile(3, "b", "Diver", hostile_to_player=True),
                   event(4, "pawn.injured", {"details": {"injury": "Gunshot", "part": "arm"}},
                         [{"pawn_id": "p", "role": "subject"}, {"pawn_id": "a", "role": "attacker"}]),
                   event(5, "pawn.job_changed", {"pawn_id": "p", "current_job": {
                         "def": "AttackStatic", "target_a": {"thing_id": "b", "label": "Diver"}}}),
                   event(6, "social.interaction", {"interaction": "Chitchat", "social_log_text": "Shift discussed secret plans with Diver."},
                         [{"pawn_id": "a", "role": "initiator"}, {"pawn_id": "b", "role": "recipient"}])]
        original = copy.deepcopy(records)
        memory = [{"playthrough_id": "game", "session_id": "session", "day": 0, "story_bits": ["Shift attacked Chaz."]}]
        session = build_document(records, memory=memory)["sessions"][0]
        text = session["prompt"]["user"]
        self.assertNotIn("Shift", text)
        self.assertNotIn("Diver", text)
        self.assertNotIn("secret plans", text)
        self.assertIn("Chaz was injured by enemy 1", text)
        self.assertIn("involving enemy 2", text)
        self.assertIn("Yesterday: enemy 1 attacked Chaz.", text)
        self.assertEqual(session["source_end_sequence"], 6)
        self.assertEqual(session["event_count"], 6)
        self.assertEqual(records, original)

    def test_neutral_prisoner_slave_and_pet_names_are_preserved(self):
        records = [profile(1, "visitor", "Ryan", hostile_to_player=False),
                   profile(2, "prisoner", "PrisonerName", hostile_to_player=True, is_prisoner=True),
                   profile(3, "slave", "SlaveName", hostile_to_player=True, is_slave=True),
                   profile(4, "pet", "PetName", is_colony_animal=True),
                   event(5, "session.snapshot", {"pawns": [{"pawn_id": "visitor", "dead": False}]}),
                   event(6, "social.interaction", {"interaction": "Chitchat", "social_log_text": "Ryan greeted PrisonerName."},
                         [{"pawn_id": "visitor", "role": "initiator"}, {"pawn_id": "prisoner", "role": "recipient"}])]
        text = build_document(records)["sessions"][0]["prompt"]["user"]
        for name in ("Ryan", "PrisonerName", "SlaveName", "PetName"):
            self.assertIn(name, text)
        self.assertIn("Ryan greeted PrisonerName", text)

    def test_capture_keeps_name_but_drops_socializing_while_hostile(self):
        records = [profile(1, "a", "Shift", hostile_to_player=True),
                   event(2, "social.interaction", {"interaction": "Chitchat", "social_log_text": "Secret enemy conversation."},
                         [{"pawn_id": "a", "role": "initiator"}]),
                   profile(3, "a", "Shift", hostile_to_player=True, is_prisoner=True)]
        text = build_document(records)["sessions"][0]["prompt"]["user"]
        self.assertIn("Shift", text)
        self.assertNotIn("Secret enemy conversation", text)


if __name__ == "__main__":
    unittest.main()
