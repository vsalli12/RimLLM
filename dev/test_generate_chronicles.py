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
    def setUp(self):
        rag_patch = patch('generate_chronicles.RAG_main.add_context', side_effect=lambda prompt: prompt)
        self.rag = rag_patch.start()
        self.addCleanup(rag_patch.stop)
        cleanup_patch = patch('generate_chronicles.RAG_main.clean_event_log',
                              return_value='A visitor arrived. CLEANED_MARKER')
        self.cleanup = cleanup_patch.start()
        self.addCleanup(cleanup_patch.stop)
        image_patch = patch('generate_chronicles.ensure_entry_scribble')
        self.images = image_patch.start()
        self.addCleanup(image_patch.stop)

    def test_image_failure_does_not_discard_completed_diary(self):
        self.images.side_effect = RuntimeError('ComfyUI offline')
        reply = Mock()
        reply.json.return_value = {'message': {'content': json.dumps({'chronicle': 'Saved diary.', 'story_bits': []})}}
        with tempfile.TemporaryDirectory() as folder, patch('generate_chronicles.requests.post', return_value=reply), contextlib.redirect_stdout(io.StringIO()):
            generate_days([event(1, 1)], folder, 1)
            self.assertEqual(json.loads((Path(folder) / 'day001.json').read_text())['chronicle'], 'Saved diary.')
            self.assertTrue((Path(folder) / 'story_memory.json').exists())

    def test_skipped_diary_gets_missing_scribble_without_text_inference(self):
        with tempfile.TemporaryDirectory() as folder, patch('generate_chronicles.FORCE_GENERATE_NEW', False), patch('generate_chronicles.requests.post') as post, contextlib.redirect_stdout(io.StringIO()):
            path = Path(folder) / 'day001.json'
            path.write_text(json.dumps({'day': 1, 'chronicle': 'Saved diary.', 'story_bits': []}))
            generate_days([event(1, 1)], folder, 1)
            post.assert_not_called()
            self.images.assert_called_once_with(path)

    def test_explicit_session_can_resume_original_after_new_session_starts(self):
        records = [event(1, 1), event(9, 2),
                   event(9, 1, 'b', kind='session.started')]
        selected, timeline = game_timeline(records, 'game', 'a')
        self.assertEqual(selected, 'a')
        self.assertEqual([e['event_id'] for e in timeline], ['a-1', 'a-2'])
        with self.assertRaisesRegex(ValueError, 'not found'):
            game_timeline(records, 'game', 'missing')

    def test_stops_at_gap_and_passes_memory_to_next_day(self):
        reply = Mock()
        reply.json.return_value = {"message": {"content": json.dumps({"chronicle": "Our diary.", "story_bits": ["We welcomed a visitor."]})}}
        with tempfile.TemporaryDirectory() as folder, patch("generate_chronicles.requests.post", return_value=reply) as post, contextlib.redirect_stdout(io.StringIO()):
            stop = generate_days([event(1, 1), event(2, 2), event(4, 3)], folder, 1)
            self.assertEqual(stop, 3)
            self.assertEqual(post.call_count, 2)
            self.assertEqual(self.cleanup.call_count, 2)
            sent = post.call_args_list[0].kwargs['json']['messages'][1]['content']
            raw = self.cleanup.call_args_list[0].args[0]
            self.assertIn('Major events', raw)
            self.assertNotIn("The writer's background", raw)
            self.assertNotIn(raw, sent)
            self.assertIn('CLEANED_MARKER', sent)
            self.assertIn("The writer's background", sent)
            self.assertEqual((Path(folder) / 'day001.events.raw.txt').read_text(), raw)
            self.assertIn('CLEANED_MARKER', (Path(folder) / 'day001.events.cleaned.txt').read_text())
            self.assertEqual(self.rag.call_count, 2)
            for call in self.rag.call_args_list:
                prompt = call.args[0]
                self.assertIsInstance(prompt, str)
                self.assertIn('A visitor arrived.', prompt)
                self.assertIn("Today's events (cleaned from recorded events)", prompt)
                self.assertIn('never pad it with unrecorded actions', prompt)
            self.assertEqual(post.call_args.kwargs["json"]["format"], "json")
            self.assertIn("Yesterday: We welcomed a visitor.", post.call_args_list[1].kwargs["json"]["messages"][1]["content"])
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

    def test_token_limit_preserves_partial_response_without_saving_story(self):
        reply = Mock()
        reply.json.return_value = {'message': {'content': '{"chronicle": "unfinished'},
                                   'done_reason': 'length'}
        with tempfile.TemporaryDirectory() as folder, patch('generate_chronicles.requests.post', return_value=reply) as post, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'context or output token limit'):
                generate_days([event(1, 1)], folder, 1)
            options = post.call_args.kwargs['json']['options']
            self.assertGreater(options['num_ctx'], options['num_predict'])
            self.assertTrue((Path(folder) / 'day001.response.txt').exists())
            self.assertFalse((Path(folder) / 'day001.json').exists())
            self.assertFalse((Path(folder) / 'story_memory.json').exists())


if __name__ == "__main__":
    unittest.main()
