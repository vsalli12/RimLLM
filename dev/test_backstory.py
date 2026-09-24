import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from prompt_constructor import Pawn, build_document


class BackstoryTests(unittest.TestCase):
    def setUp(self):
        self.pawn = Pawn('sam', 'Sam')
        self.pawn.update({'data': {
            'childhood': 'Coma child', 'adulthood': 'Sheriff',
            'traits': [{'label': 'Nimble'}, {'label': 'Abrasive'}],
            'skills': [{'def': 'Social', 'level': 13, 'passion': 'Major'}],
        }})

    @patch('prompt_constructor.requests.post')
    def test_persistent_cache_is_scoped_to_game_and_pawn(self, post):
        post.return_value.json.return_value = {'message': {'content': 'A remembered life.'}}
        with tempfile.TemporaryDirectory() as folder:
            self.pawn.expandBackStory('game-a', folder)
            # A new instance, including a changed name/profile, reuses the disk cache.
            renamed = Pawn('sam', 'Samuel')
            self.assertEqual(renamed.expandBackStory('game-a', folder), 'A remembered life.')
            self.assertEqual(post.call_count, 1)
            renamed.expandBackStory('game-b', folder)
            Pawn('other', 'Sam').expandBackStory('game-a', folder)
            self.assertEqual(post.call_count, 3)
            self.assertEqual(len(list(Path(folder).glob('*.json'))), 3)

    @patch('prompt_constructor.requests.post')
    def test_failed_generation_is_not_cached_and_corrupt_cache_is_rebuilt(self, post):
        with tempfile.TemporaryDirectory() as folder:
            post.return_value.json.return_value = {'error': 'prediction aborted'}
            with self.assertRaises(RuntimeError):
                self.pawn.expandBackStory('game', folder)
            self.assertEqual(list(Path(folder).iterdir()), [])
            post.return_value.json.return_value = {'message': {'content': 'A remembered life.'}}
            self.pawn.expandBackStory('game', folder)
            cache_file = next(Path(folder).glob('*.json'))
            cache_file.write_text('{broken', encoding='utf-8')
            self.assertEqual(self.pawn.expandBackStory('game', folder), 'A remembered life.')
            self.assertEqual(post.call_count, 3)
            self.assertEqual(json.loads(cache_file.read_text())['backstory'], 'A remembered life.')

    @patch('prompt_constructor.requests.post')
    def test_document_reuses_writer_backstory(self, post):
        post.return_value.json.return_value = {'message': {'content': 'A remembered life.'}}
        record = dict(playthrough_id='game', session_id='session', event_id='1',
                      sequence=1, game_day=1, tick=0, tick_of_day=0,
                      diary_carrier_id='sam', type='pawn.profile',
                      data={'pawn_id': 'sam', 'name': 'Sam', 'is_colonist': True})
        with tempfile.TemporaryDirectory() as folder:
            for day in (1, 2):
                document = build_document([{**record, 'game_day': day}], day=day,
                                          backstory_cache=folder)
                prompt = document['sessions'][0]['prompt']['user']
                self.assertIn('A remembered life.', prompt)
                self.assertIn('not recorded game facts', prompt)
            self.assertEqual(post.call_count, 1)

    @patch('prompt_constructor.requests.post')
    def test_returns_prose_and_sends_character_background(self, post):
        post.return_value.json.return_value = {
            'message': {'content': '  Sam learned to read people as a sheriff.\n'}}
        self.assertEqual(self.pawn.expandBackStory(),
                         'Sam learned to read people as a sheriff.')
        body = post.call_args.kwargs['json']
        self.assertNotIn('format', body)
        for detail in ('Coma child', 'Sheriff', 'Nimble', 'Abrasive', 'Social'):
            self.assertIn(detail, body['messages'][1]['content'])

    @patch('prompt_constructor.requests.post')
    def test_reports_ollama_generation_error(self, post):
        post.return_value.json.return_value = {
            'error': 'prediction aborted, token repeat limit reached'}
        with self.assertRaisesRegex(RuntimeError, 'Sam.*token repeat limit reached'):
            self.pawn.expandBackStory()

    @patch('prompt_constructor.requests.post')
    def test_rejects_missing_or_empty_content(self, post):
        for payload in ({}, [], {'message': None}, {'message': {'content': ' '}}):
            with self.subTest(payload=payload):
                post.return_value.json.return_value = payload
                with self.assertRaisesRegex(ValueError, 'no backstory text'):
                    self.pawn.expandBackStory()

    @patch('prompt_constructor.requests.post')
    def test_non_json_http_error_is_preserved(self, post):
        post.return_value.json.side_effect = ValueError('not JSON')
        post.return_value.raise_for_status.side_effect = requests.HTTPError('502')
        with self.assertRaises(requests.HTTPError):
            self.pawn.expandBackStory()


if __name__ == '__main__':
    unittest.main()
