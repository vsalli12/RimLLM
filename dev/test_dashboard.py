import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer

import main
from diary_settings import DEFAULTS, validate_settings, load_settings


class DashboardTests(unittest.TestCase):
    def test_validation(self):
        for bad in ({'game_id': '../escape'}, {'beginning_day': True},
                    {'ending_day': 1, 'beginning_day': 2}, {'model': ''},
                    {'generate_scribbles': 'false'}, {'unknown': 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_settings(bad)

    def test_health_endpoint_and_offline(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'Ready'
        with patch('main.urlopen', return_value=response) as get:
            self.assertTrue(main.service_status(('receiver', main.SERVICES['receiver']))[1]['online'])
            self.assertEqual(get.call_args.args[0], 'http://127.0.0.1:8765/health')
        with patch('main.urlopen', side_effect=OSError('offline')):
            self.assertFalse(main.service_status(('receiver', main.SERVICES['receiver']))[1]['online'])

    def test_routes_persistence_and_job_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Path(folder) / 'settings.json'
            server = ThreadingHTTPServer(('127.0.0.1', 0), main.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            def post(path, value, origin=base):
                request = Request(base+path, json.dumps(value).encode(),
                                  {'Content-Type': 'application/json', 'Origin': origin})
                return urlopen(request)
            try:
                with patch('main.SETTINGS_PATH', settings), patch('main.DIRECTORY', Path(folder)), patch('main.load_settings', side_effect=lambda: load_settings(settings)), patch('main.generation', None), patch('main.subprocess.Popen') as launch:
                    self.assertEqual(json.load(urlopen(base+'/api/settings')), DEFAULTS)
                    saved = {**DEFAULTS, 'game_id': 'game'}
                    with post('/api/settings', saved) as response:
                        self.assertEqual(json.load(response), saved)
                    self.assertEqual(load_settings(settings), saved)
                    with self.assertRaises(HTTPError) as error:
                        post('/api/settings', saved, 'http://elsewhere')
                    self.assertEqual(error.exception.code, 403)
                    launch.return_value.poll.return_value = None
                    with post('/api/generate', {}) as response:
                        self.assertEqual(response.status, 202)
                    self.assertEqual(json.loads((Path(folder)/'generation_settings.json').read_text()), saved)
                    with self.assertRaises(HTTPError) as error:
                        post('/api/generate', {})
                    self.assertEqual(error.exception.code, 409)
                    self.assertEqual(launch.call_count, 1)
                self.assertIn(b'Your colony', urlopen(base+'/').read())
                self.assertIn(b'<html', urlopen(base+'/diary').read())
                self.assertIsInstance(json.load(urlopen(base+'/diaries')), list)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
