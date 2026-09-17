"""List recorded games and their sessions. No arguments required."""
import json
from pathlib import Path
import sqlite3


def main():
    database = Path(__file__).with_name("events.sqlite3")
    games = {}
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        for (payload,) in db.execute("SELECT payload FROM events ORDER BY rowid"):
            event = json.loads(payload)
            day = event.get("game_day")
            if not isinstance(day, int) or day < 1:
                continue
            sessions = games.setdefault(event["playthrough_id"], {})
            sessions.setdefault(event["session_id"], set()).add(day)
    for game_id, sessions in games.items():
        days = sorted(set().union(*sessions.values()))
        print(f"GAME_ID = \"{game_id}\"  | recorded days: {', '.join(map(str, days))}")
        for session_id, session_days in sessions.items():
            print(f"  Session {session_id}: days {', '.join(map(str, sorted(session_days)))}")


if __name__ == "__main__":
    main()
