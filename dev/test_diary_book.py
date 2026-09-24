import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from diary_book import ensure_book, opening_context, generate_prologue
import host_frontend


def event(seq, kind, data=None, carrier=None, day=1):
    return dict(sequence=seq, type=kind, data=data or {}, diary_carrier_id=carrier,
                game_day=day, map_id=1, playthrough_id='game', session_id='session')


def records():
    return [event(1,'session.started',{'scenario':{'name':'Naked Brutality'}}),
            event(2,'pawn.profile',{'pawn_id':'a','name':'Engie','childhood':'Engineer'}),
            event(3,'map.environment',{'biome':'Desert','weather':'Clear'}),
            event(4,'diary.owner_changed',carrier='a'),
            event(5,'map.environment',{'weather':'FutureRain'},carrier='a'),
            event(6,'pawn.profile',{'pawn_id':'a','name':'LaterName'},carrier='a'),
            event(7,'diary.owner_changed',carrier='b',day=2)]


class BookTests(unittest.TestCase):
    def test_opening_excludes_later_context(self):
        opening=opening_context(records())
        self.assertEqual(opening['protagonist_name'],'Engie')
        self.assertEqual(opening['background']['childhood'],'Engineer')
        self.assertEqual(opening['scenario']['name'],'Naked Brutality')
        self.assertEqual(opening['environment'][0]['weather'],'Clear')
        self.assertNotIn('FutureRain',json.dumps(opening))
        self.assertEqual(opening['source_end_sequence'],4)

    def test_title_is_immutable_and_first_day_uses_daily_protagonist(self):
        with tempfile.TemporaryDirectory() as folder:
            book=ensure_book(records(),folder)
            self.assertEqual(book['title'],"Engie's story")
            changed=records()+[event(8,'diary.owner_changed',carrier='b')]
            self.assertEqual(ensure_book(changed,folder),book)
            self.assertEqual(opening_context(changed)['protagonist_id'],'b')

    def test_no_carrier_has_no_opening(self):
        self.assertIsNone(opening_context([event(1,'session.started')]))

    def test_prologue_cached_and_displayed_before_day_one(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'chronicles'/'game'/'session'
            book=ensure_book(records(),folder)
            reply=Mock()
            reply.json.return_value={'message':{'content':json.dumps({'chronicle':'An opening.'})}}
            with patch('diary_book.requests.post',return_value=reply) as post:
                options=dict(model='test',url='http://localhost/api/chat',context_tokens=4096,output_tokens=1024)
                generate_prologue(book,folder,**options)
                generate_prologue(book,folder,**options)
                self.assertEqual(post.call_count,1)
                self.assertNotIn('FutureRain',post.call_args.kwargs['json']['messages'][1]['content'])
            (folder/'day001.json').write_text(json.dumps({'day':1,'chronicle':'Day one.'}))
            with patch('host_frontend.DIRECTORY',Path(root)):
                diary=host_frontend.load_diaries()[0]
            self.assertEqual(diary['title'],"Engie's story")
            self.assertEqual([e['kind'] for e in diary['entries']],['prologue','day'])
            self.assertFalse((folder/'story_memory.json').exists())

    def test_truncated_response_is_not_published(self):
        with tempfile.TemporaryDirectory() as folder:
            book=ensure_book(records(),folder)
            reply=Mock()
            reply.json.return_value={'done_reason':'length','message':{'content':'partial'}}
            with patch('diary_book.requests.post',return_value=reply), self.assertRaises(ValueError):
                generate_prologue(book,folder,model='test',url='unused',context_tokens=1,output_tokens=1)
            self.assertFalse((Path(folder)/'prologue.json').exists())


if __name__=='__main__':
    unittest.main()
