import unittest

from build_day_prompt import build_document
from test_day_prompt import event


def profile(seq, pawn_id, name, **fields):
    return event(seq, 'pawn.profile', dict(pawn_id=pawn_id, name=name, dead=False,
                 species='human', gender='Female', **fields))


def incident(seq, kind, subject, attacker=None, **data):
    record = event(seq, kind, data)
    record['participants'] = [dict(pawn_id=subject, role='subject')]
    if attacker:
        record['participants'].append(dict(pawn_id=attacker, role='attacker'))
    return record


def prompt(records, day=1):
    return build_document(records, day)['sessions'][0]['prompt']['user']


class IncidentTests(unittest.TestCase):
    def test_dead_pet_and_departed_colonist_are_not_in_next_day_cast(self):
        today = event(5, 'session.started')
        today['game_day'] = 2
        records = [profile(1, 'pet', 'Sport', is_colony_animal=True),
                   profile(2, 'p', 'Gone', is_colonist=True),
                   incident(3, 'pawn.died', 'pet'),
                   event(4, 'pawn.no_longer_observed', {'pawn_id': 'p'}), today]
        text = prompt(records, 2)
        self.assertNotIn('Sport', text)
        self.assertNotIn('Gone', text)
        records[2] = event(3, 'pawn.profile', dict(pawn_id='pet', dead=True))
        self.assertNotIn('Sport', prompt(records, 2))

    def test_death_today_remains_in_cast_and_merges_late_injury_callbacks(self):
        records = [profile(1, 'p', 'Victim', is_colonist=True), profile(2, 'a', 'Attacker'),
                   incident(3, 'pawn.died', 'p', 'a', details={'damage_type': 'Bullet'}),
                   incident(4, 'pawn.injured', 'p', 'a', details={'injury': 'Gunshot', 'part': 'liver'})]
        text = prompt(records)
        self.assertIn('Victim — COLONIST; DEAD', text)
        self.assertIn('DEATH: Victim was killed by Attacker (Bullet)', text)
        self.assertEqual(text.count('Gunshot to liver'), 1)
        self.assertNotIn('Victim was injured', text)
        self.assertEqual(build_document(records), build_document(records))

    def test_raider_and_neutral_outsider_are_distinguished(self):
        records = [event(1, 'colony.letter', {'label': 'Raid: Gas Gang', 'text': 'They will attack.'}),
                   profile(2, 'r', 'Erick', faction='Gas Gang'), profile(3, 'v', 'Trader', faction='Union'),
                   event(4, 'pawn.observed', {'pawn_id': 'v'}),
                   event(5, 'pawn.job_changed', {'pawn_id': 'r', 'current_job': {'def': 'Ignite'}}),
                   incident(6, 'pawn.died', 'r')]
        text = prompt(records)
        self.assertIn('Erick — RAIDER; faction: Gas Gang; DEAD', text)
        self.assertIn('Trader — OUTSIDER', text)
        self.assertIn('Erick [RAIDER] started Ignite', text)
        self.assertIn('DEATH: Erick [RAIDER] died', text)
        self.assertLess(text.index('Raid: Gas Gang'), text.index('Other events'))

    def test_only_confirmed_wildlife_combat_is_omitted(self):
        for pet, known in ((False, True), (True, True), (False, False)):
            with self.subTest(pet=pet, known=known):
                a = event(1, 'pawn.profile', dict(pawn_id='a', name='Prey', species='mod creature', is_animal=known,
                          is_colony_animal=pet, faction=None, dead=False))
                b = event(2, 'pawn.profile', dict(pawn_id='b', name='Predator', species='cougar', faction=None, dead=False))
                text = prompt([a, b, incident(3, 'pawn.died', 'a', 'b')])
                self.assertEqual('DEATH:' in text, pet or not known)
                if not pet and known:
                    self.assertNotIn('Prey', text)
                    self.assertNotIn('Predator', text)

    def test_unknown_attacker_death_is_retained(self):
        records = [event(1, 'pawn.profile', dict(pawn_id='p', name='Rat', species='rat')),
                   incident(2, 'pawn.died', 'p')]
        self.assertIn('DEATH: Rat died', prompt(records))

    def test_combat_is_compact_and_recovers_separately(self):
        records = [profile(1, 'p', 'Oaks', is_colonist=True)]
        for i in range(2, 20):
            records.append(incident(i, 'pawn.injured', 'p', details={'injury': 'Scratch', 'part': 'arm'}))
        records.append(incident(20, 'pawn.recovered_from_downing', 'p'))
        text = prompt(records)
        self.assertIn('Combat notes', text)
        self.assertEqual(text.count('Scratch to arm'), 1)
        self.assertIn('recovered from being downed', text)

    def test_fire_merges_across_hour_boundary_but_not_maps(self):
        records = [profile(1, 'p', 'Oaks', is_colonist=True)]
        for i, tick in enumerate((1200, 1400, 1600), 2):
            e = event(i, 'pawn.job_changed', {'pawn_id': 'p', 'current_job': {'def': 'BeatFire'}})
            e['tick_of_day'] = tick
            records.append(e)
        records[-1]['map_id'] = 1
        text = prompt(records)
        self.assertEqual(text.count('FIRE RESPONSE:'), 2)
        self.assertIn('(2 assignments)', text)
        self.assertIn('12:00 to 13:00', text)
        self.assertNotIn('started Beat Fire', text)
        self.assertIn('outcome and cause not recorded', text)

    def test_mood_is_once_per_colonist_and_health_changes_survive(self):
        state = dict(pawn_id='p', map_id=0, dead=False, mood=.7, health=[],
                     mood_contributors=[{'def': 'BondedAnimalDied', 'label': 'Bonded animal died', 'mood_offset': -8}] * 3)
        records = [profile(1, 'p', 'Oaks', is_colonist=True),
                   event(2, 'session.snapshot', {'pawns': [state]}),
                   incident(3, 'pawn.condition_changed', 'p', subject_state={**state, 'health': [{'def': 'AlcoholHigh'}]}),
                   incident(4, 'pawn.condition_changed', 'p', subject_state={**state, 'mood': .2, 'health': [{'def': 'Infection', 'part': 'arm'}]})]
        text = prompt(records)
        self.assertEqual(text.count('Bonded animal died'), 1)
        self.assertIn('content -> unhappy', text)
        self.assertIn('new health conditions: Infection on arm', text)
        self.assertNotIn('AlcoholHigh', text)
        self.assertNotIn('condition or relationship change', text)

    def test_abandoned_save_death_does_not_remove_living_actor(self):
        p = profile(1, 'p', 'Oaks', is_colonist=True)
        abandoned = incident(2, 'pawn.died', 'p')
        resumed = event(1, 'session.started', {'parent_session_id': 'a', 'parent_event_id': 'a-1'}, session='b')
        resumed['game_day'] = 2
        self.assertIn('Oaks — COLONIST', prompt([p, abandoned, resumed], 2))
        self.assertNotIn('DEAD', prompt([p, abandoned, resumed], 2))

    def test_death_is_ordered_by_outcome_time_not_first_injury(self):
        text = prompt([profile(1, 'p', 'Oaks', is_colonist=True),
                       incident(2, 'pawn.injured', 'p', details={'injury': 'Cut'}),
                       event(3, 'colony.letter', {'label': 'Raid: Gang', 'text': 'Raiders arrived.'}),
                       incident(4, 'pawn.died', 'p')])
        self.assertLess(text.index('Raid: Gang'), text.index('DEATH:'))

    def test_recovery_splits_combat_bouts(self):
        text = prompt([profile(1, 'p', 'Oaks', is_colonist=True),
                       incident(2, 'pawn.injured', 'p', details={'injury': 'Cut'}),
                       incident(3, 'pawn.recovered_from_downing', 'p'),
                       incident(4, 'pawn.injured', 'p', details={'injury': 'Cut'})])
        self.assertEqual(text.count('Oaks was injured'), 2)


if __name__ == '__main__':
    unittest.main()
