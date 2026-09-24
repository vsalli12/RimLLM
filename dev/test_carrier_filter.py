import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
from urllib.request import urlopen
import socket

from prompt_constructor import build_document, narrator_window
from diary_settings import validate_settings
from main import managed_receiver


def event(seq, carrier, text='News', day=1, kind='colony.letter', data=None):
    return dict(event_id=f'a-{seq}', sequence=seq, tick=seq*100,
                game_day=day, tick_of_day=seq*100, type=kind,
                data=data or {'label': text, 'text': text},
                playthrough_id='game', session_id='a', diary_carrier_id=carrier,
                participants=[], map_id=0)


class CarrierTests(unittest.TestCase):
    def test_drop_and_death_need_no_special_handling(self):
        records = [event(1, None, 'BEFORE'), event(2, 'a', 'CARRIED'),
                   event(3, None, 'AFTER')]
        doc = build_document(records)
        session = doc['sessions'][0]
        self.assertEqual(session['source_end_sequence'], 2)
        self.assertEqual(session['event_count'], 1)
        self.assertIn('CARRIED', session['event_log'])
        self.assertNotIn('BEFORE', session['prompt']['user'])
        self.assertNotIn('AFTER', session['prompt']['user'])

    def test_last_carrier_excludes_previous_writer_and_unheld_gaps(self):
        records = [event(1, 'a', 'FIRST'), event(2, None, 'GAP'),
                   event(3, 'b', 'SECOND'), event(4, None, 'LATE')]
        carrier, selected = narrator_window(records)
        self.assertEqual(carrier, 'b')
        self.assertEqual([e['sequence'] for e in selected], [3])
        text = build_document(records)['sessions'][0]['event_log']
        self.assertIn('SECOND', text)
        for omitted in ('FIRST', 'GAP', 'LATE'):
            self.assertNotIn(omitted, text)

    def test_same_carrier_can_resume_after_a_gap(self):
        records = [event(1, 'a'), event(2, None), event(3, 'a')]
        self.assertEqual([e['sequence'] for e in narrator_window(records)[1]], [1, 3])

    def test_unheld_day_has_no_entry_even_with_previous_carrier(self):
        records = [event(1, 'a'), event(2, None, day=2)]
        self.assertEqual(build_document(records, day=2)['sessions'], [])

    def test_other_sessions_do_not_supply_a_writer(self):
        other = event(2, 'a')
        other['session_id'] = 'b'
        sessions = build_document([event(1, None), other])['sessions']
        self.assertEqual([s['session_id'] for s in sessions], ['b'])


class LifecycleTests(unittest.TestCase):
    def test_saved_session_selection_is_discarded(self):
        self.assertNotIn('session_id', validate_settings({'session_id': 'old-session'}))

    def test_receiver_closes_with_dashboard_context(self):
        with tempfile.TemporaryDirectory() as folder:
            with managed_receiver(port=0, database=Path(folder)/'events.sqlite3') as server:
                port = server.server_port
                with urlopen(f'http://127.0.0.1:{port}/health') as response:
                    self.assertEqual(response.status, 200)
            with socket.socket() as probe:
                self.assertNotEqual(probe.connect_ex(('127.0.0.1', port)), 0)


if __name__ == '__main__':
    unittest.main()
