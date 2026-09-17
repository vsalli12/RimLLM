import json
from pathlib import Path
import tempfile
import unittest

from receiver import accept_batch, open_database


def event(sequence=1, carrier=None, session="session-a"):
    return dict(schema_version=1, event_id=f"{session}-{sequence}", playthrough_id="colony",
                session_id=session, sequence=sequence, diary_carrier_id=carrier,
                type="diary.owner_changed", data={})


def batch(*events):
    return dict(schema_version=1, batch_id="test-batch", events=list(events))


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "events.sqlite3"
        self.db = open_database(self.path)

    def tearDown(self):
        self.db.close()
        self.directory.cleanup()

    def test_retry_after_restart_is_deduplicated(self):
        self.assertEqual(len(accept_batch(self.db, batch(event()))[1]), 1)
        self.db.close()
        self.db = open_database(self.path)
        self.assertEqual(accept_batch(self.db, batch(event()))[1], [])

    def test_drop_and_out_of_order_delivery(self):
        accept_batch(self.db, batch(event(2, "pawn-1"), event(3), event(1, "pawn-old")))
        self.assertEqual(self.db.execute("SELECT sequence, pawn_id FROM narrators").fetchone(), (3, None))

    def test_reload_has_separate_narrator(self):
        accept_batch(self.db, batch(event(10, "pawn-1"), event(1, None, "session-b")))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM narrators").fetchone()[0], 2)

    def test_invalid_batch_is_atomic(self):
        invalid = event(2)
        del invalid["diary_carrier_id"]
        with self.assertRaises(ValueError):
            accept_batch(self.db, batch(event(), invalid))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)

    def test_unicode_and_newlines_are_preserved(self):
        sample = event()
        sample["data"] = {"name": 'Ääni "Diary"\n雪'}
        accept_batch(self.db, batch(sample))
        stored = json.loads(self.db.execute("SELECT payload FROM events").fetchone()[0])
        self.assertEqual(stored["data"], sample["data"])


if __name__ == "__main__":
    unittest.main()
