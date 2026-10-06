import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch, Mock
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import main
from narrator_personality import read_backstory, write_backstory, narrators
from prompt_constructor import Pawn
from receiver import open_database


class PersonalityTests(unittest.TestCase):
    def test_override_is_used_without_llm_and_is_isolated(self):
        with tempfile.TemporaryDirectory() as folder:
            write_backstory('game', 'pawn', 'Quiet, dry humor. Once a gardener.', folder)
            with patch('prompt_constructor.requests.post') as post:
                self.assertEqual(Pawn('pawn', 'Engie').expandBackStory('game', folder),
                                 'Quiet, dry humor. Once a gardener.')
                post.assert_not_called()
            self.assertEqual(read_backstory('other-game', 'pawn', folder), '')
            self.assertEqual(read_backstory('game', 'other-pawn', folder), '')
            with self.assertRaises(ValueError):
                write_backstory('game', 'pawn', '   ', folder)
            self.assertIn('Quiet', read_backstory('game', 'pawn', folder))

    def test_narrators_follow_latest_ancestry(self):
        with tempfile.TemporaryDirectory() as folder:
            dbpath=Path(folder)/'events.sqlite3'
            with open_database(dbpath) as db:
                records=[('a',1,'session.started',None,{}),
                         ('a',2,'pawn.profile','p',{'pawn_id':'p','name':'Engie'}),
                         ('a',3,'diary.owner_changed','abandoned',{}),
                         ('b',1,'session.started',None,{'parent_session_id':'a','parent_event_id':'a-2'}),
                         ('b',2,'pawn.profile','q',{'pawn_id':'q','name':'New teller'})]
                for session,seq,kind,carrier,data in records:
                    event=dict(event_id=f'{session}-{seq}',playthrough_id='game',session_id=session,
                               sequence=seq,type=kind,diary_carrier_id=carrier,data=data)
                    db.execute('INSERT INTO events VALUES (?,?,?,?,?)',
                               (event['event_id'],'game',session,seq,json.dumps(event)))
            db.close()
            write_backstory('game','p','Original voice.',folder)
            result=narrators('game',dbpath,folder)
            self.assertEqual(result['selected'],'q')
            self.assertEqual([n['pawn_id'] for n in result['narrators']],['p','q'])
            self.assertEqual(result['narrators'][0]['backstory'],'Original voice.')

    def test_http_override_and_generation_guard(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),main.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with patch('main.narrators',return_value={'selected':'p','narrators':[{'pawn_id':'p','name':'Engie','backstory':'Old'}]}), patch('main.write_backstory',return_value='New') as save, patch('main.generation',None):
                with urlopen(base+'/api/personalities?game_id=game') as response:
                    self.assertEqual(json.load(response)['selected'],'p')
                def request(pawn='p'):
                    return Request(base+'/api/personalities',json.dumps({'game_id':'game','pawn_id':pawn,'backstory':'New'}).encode(),{'Origin':base,'Content-Type':'application/json'})
                with urlopen(request()) as response:
                    self.assertEqual(json.load(response)['backstory'],'New')
                save.assert_called_once_with('game','p','New')
                with self.assertRaises(HTTPError) as error:
                    urlopen(request('wrong'))
                self.assertEqual(error.exception.code,400)
                process=Mock();process.poll.return_value=None
                with patch('main.generation',process), self.assertRaises(HTTPError) as error:
                    urlopen(request())
                self.assertEqual(error.exception.code,409)
                for asset in ('theme.css','theme.js'):
                    with urlopen(base+'/'+asset) as response:
                        self.assertEqual(response.status,200)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':
    unittest.main()
