import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from generate_chronicles import game_timeline, generate_days


def event(day, sequence, session="a", data=None, kind="colony.letter"):
    return dict(playthrough_id="game", session_id=session, event_id=f"{session}-{sequence}",
                sequence=sequence, game_day=day, tick=day * 60000, tick_of_day=0,
                diary_carrier_id=None, type=kind, data=data or {"label": "News", "text": "A visitor arrived."})


class GenerateChroniclesTests(unittest.TestCase):
    def test_stops_at_gap_and_passes_memory_to_next_day(self):
        reply = Mock()
        reply.json.return_value = {"message": {"content": json.dumps({"chronicle": "Our diary.", "story_bits": ["We welcomed a visitor."]})}}
        with tempfile.TemporaryDirectory() as folder, patch("generate_chronicles.requests.post", return_value=reply) as post, contextlib.redirect_stdout(io.StringIO()):
            stop = generate_days([event(1, 1), event(2, 2), event(4, 3)], folder, 1)
            self.assertEqual(stop, 3)
            self.assertEqual(post.call_count, 2)
            self.assertEqual(post.call_args.kwargs["json"]["format"], "json")
            self.assertIn("Day 1: We welcomed a visitor.", post.call_args_list[1].kwargs["json"]["messages"][1]["content"])
            self.assertEqual((Path(folder) / "day002.txt").read_text(), "Our diary.\n")
            self.assertFalse((Path(folder) / "day004.txt").exists())

    def test_reload_discards_future_and_combines_same_day(self):
        records = [event(1, 1), event(1, 2), event(2, 3),
                   event(1, 1, "b", {"parent_session_id": "a", "parent_event_id": "a-2"}, "session.started"),
                   event(1, 2, "b")]
        latest, timeline = game_timeline(records, "game")
        self.assertEqual(latest, "b")
        self.assertEqual([e["event_id"] for e in timeline], ["a-1", "a-2", "b-1", "b-2"])
        self.assertEqual({e["session_id"] for e in timeline}, {"b"})

    def test_bad_response_is_saved_and_stops_generation(self):
        reply = Mock()
        reply.json.return_value = {"message": {"content": "Not JSON"}}
        with tempfile.TemporaryDirectory() as folder, patch("generate_chronicles.requests.post", return_value=reply) as post, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, r"Day 1: invalid story response.*day001.response.txt"):
                generate_days([event(1, 1), event(2, 2)], folder, 1)
            self.assertEqual(post.call_count, 1)
            self.assertEqual((Path(folder) / "day001.response.txt").read_text(), "Not JSON")
            self.assertFalse((Path(folder) / "story_memory.json").exists())


if __name__ == "__main__":
    unittest.main()
