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
    def test_unassigned_events_are_kept_for_a_carried_day(self):
        records = [event(1, None, 'BEFORE'), event(2, 'a', 'CARRIED'),
                   event(3, None, 'AFTER')]
        doc = build_document(records)
        session = doc['sessions'][0]
        self.assertEqual(session['source_end_sequence'], 3)
        self.assertEqual(session['event_count'], 3)
        self.assertIn('CARRIED', session['event_log'])
        self.assertIn('BEFORE', session['prompt']['user'])
        self.assertIn('AFTER', session['prompt']['user'])

    def test_last_carrier_keeps_previous_writer_events_and_unheld_gaps(self):
        records = [event(1, 'a', 'FIRST'), event(2, None, 'GAP'),
                   event(3, 'b', 'SECOND'), event(4, None, 'LATE')]
        carrier, selected = narrator_window(records)
        self.assertEqual(carrier, 'b')
        self.assertEqual([e['sequence'] for e in selected], [1, 2, 3, 4])
        text = build_document(records)['sessions'][0]['event_log']
        self.assertIn('SECOND', text)
        for retained in ('FIRST', 'GAP', 'LATE'):
            self.assertIn(retained, text)

    def test_same_carrier_can_resume_after_a_gap(self):
        records = [event(1, 'a'), event(2, None), event(3, 'a')]
        self.assertEqual([e['sequence'] for e in narrator_window(records)[1]], [1, 2, 3])

    def test_first_day_profile_before_pickup_supplies_writer_background(self):
        records = [event(1, None, kind='pawn.profile', data={
            'pawn_id': 'a', 'name': 'Engie', 'childhood': 'Foundry apprentice',
            'is_colonist': True}),
            event(2, 'a', kind='diary.owner_changed', data={'new_carrier_id': 'a'}),
            event(3, None, kind='diary.owner_changed', data={'new_carrier_id': None})]
        prompt = build_document(records)['sessions'][0]['prompt']['user']
        self.assertIn('Engie', prompt)
        self.assertIn('Foundry apprentice', prompt)
        self.assertNotIn('background unavailable', prompt)
        self.assertNotIn('Write in a neutral voice', prompt)

    def test_successor_sees_previous_carriers_death_with_null_carrier(self):
        death = event(3, None, kind='pawn.died')
        death['participants'] = [{'pawn_id': 'a', 'role': 'subject'}]
        records = [event(1, 'a', kind='pawn.profile', data={
            'pawn_id': 'a', 'name': 'Engie', 'is_colonist': True}),
            event(2, 'a', kind='pawn.profile', data={
            'pawn_id': 'b', 'name': 'Sam', 'is_colonist': True}), death,
            event(4, 'b', kind='diary.owner_changed', data={'new_carrier_id': 'b'})]
        session = build_document(records)['sessions'][0]
        self.assertIn('DEATH: Engie', session['event_log'])
        background = session['prompt']['user'].split("The writer's background:\n")[1].split('The actors:')[0]
        self.assertIn('Sam', background)
        self.assertEqual(session['event_count'], 4)

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
