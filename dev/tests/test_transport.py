"""Build dev/TransportSmoke first. This test temporarily uses port 8765."""
import json
from http.server import HTTPServer
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from receiver import make_handler, open_database


class TransportTests(unittest.TestCase):
    def test_offline_buffer_restart_and_csharp_delivery(self):
        dll = Path(__file__).parent / "TransportSmoke/bin/Release/net10.0/TransportSmoke.dll"
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            outbox = directory / "outbox"
            command = ["dotnet", str(dll.resolve()), str(outbox)]
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, encoding="utf-8")
            try:
                self.assertEqual(process.stdout.readline().strip(), "BUFFERED")
                stored = json.loads(next(outbox.glob("*.json")).read_text(encoding="utf-8"))
                data = stored["events"][0]["data"]
                self.assertEqual(data["name"], 'Ääni "Diary"\n雪😀')
                self.assertEqual(data["number"], 1.25)
                self.assertEqual(data["values"], [True, None, 3, "\\"])
            finally:
                process.kill()
                process.communicate(timeout=5)

            # Fresh process must deliver the existing file without re-enqueueing the event.
            process = subprocess.Popen(command + ["replay"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, encoding="utf-8")
            db = open_database(directory / "events.sqlite3")
            server = None
            try:
                self.assertEqual(process.stdout.readline().strip(), "BUFFERED")
                server = HTTPServer(("127.0.0.1", 8765), make_handler(db))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                output, error = process.communicate("\n", timeout=25)
                self.assertEqual(process.returncode, 0, error)
                self.assertIn("DELIVERED", output)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
                self.assertEqual(list(outbox.glob("*.json")), [])
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)
                if server:
                    server.shutdown()
                    server.server_close()
                db.close()


if __name__ == "__main__":
    unittest.main()
