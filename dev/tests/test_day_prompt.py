import unittest
from build_day_prompt import build_document, Dialogue, Event, Pawn, select_events


def event(seq, kind, data=None, session='a', carrier=None):
    return dict(event_id=f'{session}-{seq}', sequence=seq, tick=100 * seq,
                game_day=1, tick_of_day=100 * seq, type=kind, data=data or {},
                playthrough_id='colony', session_id=session, diary_carrier_id=carrier,
                participants=[], map_id=0)


class PromptTests(unittest.TestCase):
    def test_readable_prompt_and_session_isolation(self):
        profile = event(1, 'pawn.profile', dict(pawn_id='p', name='Oaks', is_colonist=True,
                                               childhood='story writer', traits=None, skills=None))
        job = event(2, 'pawn.job_changed', dict(pawn_id='p', current_job={'def': 'Mine'}), carrier='p')
        other = event(1, 'session.started', session='b')
        doc = build_document([profile, job, other])
        first, second = [s['prompt']['user'] for s in doc['sessions']]
        self.assertIsInstance(first, str)
        self.assertIn('Childhood: story writer', first)
        self.assertIn('Oaks started Mine', first)
        self.assertNotIn('Oaks', second)
        self.assertIn('No final Diary carrier', second)

    def test_social_opinions_are_directional_and_topic_is_preserved(self):
        e = event(1, 'social.interaction', dict(interaction='Chitchat', social_log_text='<b>Oaks</b> discussed food.', initiator_opinion=42, recipient_opinion=47))
        e['participants'] = [dict(pawn_id='p', role='initiator'), dict(pawn_id='q', role='recipient')]
        text = Dialogue(e, {'p': 'Oaks', 'q': 'Table'}).readable()
        self.assertIn('Oaks discussed food.', text)
        self.assertIn('Oaks likes Table', text)
        self.assertIn('Table likes Oaks', text)
        self.assertNotIn('42 to 47', text)

    def test_sampling_is_repeatable_and_death_is_always_included(self):
        records = [event(i, 'pawn.job_changed', dict(pawn_id='p', current_job={'def': 'Mine'})) for i in range(1, 50)]
        records.append(event(50, 'pawn.died'))
        a, b = build_document(records), build_document(records)
        self.assertEqual(a, b)
        self.assertIn('DEATH: A pawn died', a['sessions'][0]['prompt']['user'])

    def test_carrier_boost_and_profile_replacement(self):
        e = event(1, 'unknown', dict(pawn_id='p'), carrier='p')
        item = Event(e)
        select_events([item], 'p')
        self.assertEqual(item.weight, 2)
        select_events([item], None)
        self.assertEqual(item.weight, 1)
        pawn = Pawn('p', 'Old')
        pawn.update(event(1, 'pawn.profile', dict(name='New', traits=[{'label': 'kind'}])))
        pawn.update(event(2, 'pawn.profile', dict(traits=[{'label': 'abrasive'}])))
        self.assertEqual(pawn.traits, ['abrasive'])
        self.assertEqual(pawn.name, 'New')

    def test_final_diary_drop_uses_neutral_voice(self):
        doc = build_document([event(1, 'diary.owner_changed', {'new_carrier_id': 'p'}), event(2, 'diary.owner_changed', {'new_carrier_id': None})])
        text = doc['sessions'][0]['prompt']['user']
        self.assertIn('No final Diary carrier', text)


if __name__ == '__main__':
    unittest.main()
