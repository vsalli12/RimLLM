import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from story_memory import load_memory, parse_story, save_story, prior_story_bits
from prompt_constructor import build_document


def event(session, sequence, kind="session.started", data=None, day=1):
    return dict(event_id=f"{session}-{sequence}", session_id=session, playthrough_id="colony",
                sequence=sequence, type=kind, data=data or {}, game_day=day, tick=100,
                tick_of_day=100, diary_carrier_id=None, map_id=0)


class StoryMemoryTests(unittest.TestCase):
    def test_relative_dates_change_with_entry_day(self):
        memory = [dict(playthrough_id="colony", session_id="a", day=1,
                       story_bits=["Chaz is experiencing malnutrition."]),
                  dict(playthrough_id="colony", session_id="a", day=4,
                       story_bits=[{"summary": "Ryan died."}])]
        text = prior_story_bits(memory, [], "colony", "a", 5)
        self.assertEqual(text, "- Four days ago: Chaz is experiencing malnutrition.\n- Yesterday: Ryan died.")
        self.assertIn("- Two days ago: Ryan died.", prior_story_bits(memory, [], "colony", "a", 6))
        self.assertIn("- 11 days ago:", prior_story_bits(memory, [], "colony", "a", 12))

    def test_parse_and_replace_same_day(self):
        story = parse_story('```json\n{"chronicle":"A day.","story_bits":["Grief lingered."]}\n```')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "memory.json"
            session = dict(playthrough_id="colony", session_id="a", source_end_sequence=10)
            save_story(story, session, 1, path)
            save_story(story, session, 1, path)
            self.assertEqual(len(load_memory(path)), 1)

    def test_invalid_response_is_rejected(self):
        for text in ('Summary of events', '{"chronicle":"Entry"}', '{"chronicle":"Entry","story_bits":[{}]}'):
            with self.assertRaises(ValueError):
                parse_story(text)

    def test_memory_only_from_earlier_days_and_own_playthrough(self):
        memory = [dict(playthrough_id="colony", session_id="a", day=1, story_bits=["Grief."]),
                  dict(playthrough_id="colony", session_id="a", day=2, story_bits=["Future."]),
                  dict(playthrough_id="other", session_id="a", day=1, story_bits=["Other colony."])]
        text = prior_story_bits(memory, [], "colony", "a", 2)
        self.assertEqual(text, "- Yesterday: Grief.")

    def test_ancestry_excludes_abandoned_future_and_unrelated_session(self):
        events = [event("a", 10, "pawn.observed"), event("b", 1, data={"parent_session_id":"a", "parent_event_id":"a-10"})]
        def memory(source, end, note):
            return dict(playthrough_id="colony", session_id=source, source_end_sequence=end, day=1, story_bits=[note])
        text = prior_story_bits([memory("a", 9, "Before save."), memory("a", 11, "Abandoned."), memory("c", 1, "Unrelated.")], events, "colony", "b", 2)
        self.assertEqual(text, "- Yesterday: Before save.")

    def test_next_day_inherits_profile_and_readable_memory(self):
        profile = event("a", 1, "pawn.profile", dict(pawn_id="p", name="Oaks", faction="Renamed colony", is_colonist=True, age_biological=53))
        today = event("a", 2, "session.snapshot", day=2)
        today["diary_carrier_id"] = "p"
        memory = [dict(playthrough_id="colony", session_id="a", day=1, story_bits=["Oaks felt regret."])]
        with contextlib.redirect_stdout(io.StringIO()):
            doc = build_document([profile, today], day=2, memory=memory)
        prompt = doc["sessions"][0]["prompt"]["user"]
        self.assertIn("Oaks is a 53-year-old", prompt)
        self.assertIn("Yesterday: Oaks felt regret.", prompt)
        self.assertIn("not verified game facts", prompt)


if __name__ == "__main__":
    unittest.main()
