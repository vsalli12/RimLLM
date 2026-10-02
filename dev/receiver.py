"""RimChronicle development receiver. Python 3.10+, standard library only.

Run: python dev/receiver.py
Events are printed and durably stored in SQLite before acknowledging the sender.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sqlite3

MAX_BODY = 16 * 1024 * 1024


def open_database(path):
    db = sqlite3.connect(path, check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            playthrough_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS narrators (
            playthrough_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            pawn_id TEXT,
            PRIMARY KEY (playthrough_id, session_id)
        );
    """)
    return db


def validate_batch(batch):
    if not isinstance(batch, dict) or batch.get("schema_version") != 1:
        raise ValueError("Expected schema_version 1")
    batch_id = batch.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id or len(batch_id) > 128:
        raise ValueError("Invalid batch_id")
    events = batch.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 100:
        raise ValueError("Expected 1 to 100 events")
    for event in events:
        if not isinstance(event, dict) or event.get("schema_version") != 1:
            raise ValueError("Invalid event")
        for key in ("event_id", "playthrough_id", "session_id", "type"):
            if not isinstance(event.get(key), str) or not event[key]:
                raise ValueError(f"Missing event field: {key}")
        if type(event.get("sequence")) is not int or event["sequence"] < 1:
            raise ValueError("Invalid sequence")
        if "diary_carrier_id" not in event or not (
            event["diary_carrier_id"] is None or isinstance(event["diary_carrier_id"], str)
        ):
            raise ValueError("Invalid diary_carrier_id")
    return batch_id, events


def accept_batch(db, batch):
    batch_id, events = validate_batch(batch)
    received = []
    with db:
        for event in events:
            payload = json.dumps(event, ensure_ascii=False)
            inserted = db.execute(
                "INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?)",
                (event["event_id"], event["playthrough_id"], event["session_id"], event["sequence"], payload),
            ).rowcount
            if not inserted:
                continue
            db.execute("""
                INSERT INTO narrators VALUES (?, ?, ?, ?)
                ON CONFLICT(playthrough_id, session_id) DO UPDATE SET
                    sequence=excluded.sequence, pawn_id=excluded.pawn_id
                WHERE excluded.sequence > narrators.sequence
                """, (event["playthrough_id"], event["session_id"], event["sequence"], event["diary_carrier_id"]))
            received.append(event)
    return batch_id, received


def make_handler(db):
    class Receiver(BaseHTTPRequestHandler):
        def reply(self, status, text):
            body = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.reply(200 if self.path == "/health" else 404,
                       "RimChronicle receiver ready" if self.path == "/health" else "Not found")

        def do_POST(self):
            if self.path != "/events":
                self.reply(404, "Not found")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    self.reply(413, "Invalid or excessive body length")
                    return
                batch = json.loads(self.rfile.read(length).decode("utf-8"))
                batch_id, events = accept_batch(db, batch)
            except (ValueError, UnicodeError) as error:
                self.reply(400, str(error))
                return
            except sqlite3.Error as error:
                self.reply(500, f"Storage error: {error}")
                return
            #for event in events:
            #    print(json.dumps(event, ensure_ascii=False), flush=True)
            self.reply(200, batch_id)

        def log_message(self, format, *args):
            # Keep terminal output focused on events, not one access line per batch.
            pass

    return Receiver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--database", type=Path, default=Path(__file__).with_name("events.sqlite3"))
    args = parser.parse_args()
    db = open_database(args.database)
    server = HTTPServer(("127.0.0.1", args.port), make_handler(db))
    print(f"Listening on http://127.0.0.1:{args.port}/events; storing in {args.database}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        db.close()
        print("Receiver stopped", flush=True)


if __name__ == "__main__":
    main()
