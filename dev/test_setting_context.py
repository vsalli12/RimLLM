import unittest

from prompt_constructor import build_document


def event(seq, day, kind, data, session='a', map_id=None):
    return dict(event_id=f'{session}-{seq}', playthrough_id='game', session_id=session,
                sequence=seq, tick=day * 60000 + seq, game_day=day, tick_of_day=seq * 100,
                type=kind, data=data, map_id=map_id, diary_carrier_id=None)


class SettingContextTests(unittest.TestCase):
    def test_origins_persist_but_weather_is_day_and_map_specific(self):
        records = [event(1, 1, 'session.started', {'scenario': {
            'name': 'Crashlanded', 'description': 'Three survivors escaped.'}}),
            event(2, 1, 'map.environment', {'weather': 'OldFog', 'outdoor_temperature_c': -80}, map_id=1),
            event(3, 2, 'map.environment', {'biome_label': 'Temperate forest',
                  'weather_label': 'Clear', 'outdoor_temperature_c': 10}, map_id=1),
            event(4, 2, 'map.environment', {'biome_label': 'Temperate forest',
                  'weather_label': 'Rain', 'outdoor_temperature_c': 0}, map_id=1),
            event(5, 2, 'map.environment', {'biome_label': 'Desert',
                  'weather_label': 'Clear', 'outdoor_temperature_c': 40}, map_id=2)]
        prompt = build_document(records, day=2)['sessions'][0]['prompt']['user']
        for text in ('Crashlanded', 'Three survivors escaped.', 'Map 1: biome: Temperate forest',
                     'Map 2: biome: Desert', '0.0 to 10.0 C', '40.0 to 40.0 C', 'Rain'):
            self.assertIn(text, prompt)
        self.assertNotIn('OldFog', prompt)
        self.assertNotIn('-80', prompt)

    def test_unrelated_session_does_not_supply_context(self):
        records = [event(1, 1, 'session.started', {'scenario': {'name': 'Wrong origin'}}, session='other'),
                   event(1, 2, 'session.started', {}, session='current')]
        prompt = build_document(records, day=2)['sessions'][0]['prompt']['user']
        self.assertNotIn('Wrong origin', prompt)
        self.assertNotIn('Environment during', prompt)

    def test_saved_ancestor_supplies_scenario(self):
        records = [event(1, 1, 'session.started', {'scenario': {'name': 'Tribal origin'}}),
                   event(1, 2, 'session.started', {'parent_session_id': 'a',
                         'parent_event_id': 'a-1'}, session='b')]
        prompt = build_document(records, day=2)['sessions'][0]['prompt']['user']
        self.assertIn('Tribal origin', prompt)

    def test_legacy_records_need_no_environment_fields(self):
        records = [event(1, 1, 'session.started', {})]
        prompt = build_document(records)['sessions'][0]['prompt']['user']
        self.assertNotIn('Colony origins', prompt)
        self.assertNotIn('Environment during', prompt)


if __name__ == '__main__':
    unittest.main()
