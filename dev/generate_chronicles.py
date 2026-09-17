"""Generate consecutive daily chronicles. Edit the settings below, then run this file."""
import json
import os
from pathlib import Path
import sqlite3

import requests

from build_day_prompt import build_document
from story_memory import lineage, load_memory, parse_story, save_story

# Settings: GAME_ID is the packets' playthrough_id, not a session index.
GAME_ID = "e89807344b4142238c9a023d4da32b96"
BEGINNING_DAY = 1
MODEL = "qwen3"
DIRECTORY = Path(__file__).resolve().parent
DATABASE = DIRECTORY / "events.sqlite3"
OUTPUT_DIRECTORY = DIRECTORY / "chronicles"
OLLAMA_URL = "http://localhost:11434/api/chat"
FORCE_GENERATE_NEW = True


def game_timeline(events, game_id):
    """Use the most recently started session and its saved ancestors, not abandoned futures."""
    game = [e for e in events if e.get("playthrough_id") == game_id]
    if not game:
        raise ValueError(f"No events found for GAME_ID {game_id}")
    starts = [e for e in game if e["type"] == "session.started"]
    latest_session = (starts[-1] if starts else game[-1])["session_id"]
    allowed = lineage(game, game_id, latest_session)
    timeline = []
    # Treat this selected save history as one continuous timeline for the existing builder.
    # SQLite records are never modified. A day spanning a reload gets one chronicle.
    for session_id in reversed(list(allowed)):
        part = sorted((e for e in game if e["session_id"] == session_id
                       and e["sequence"] <= allowed[session_id]), key=lambda e: e["sequence"])
        for event in part:
            timeline.append({**event, "session_id": latest_session, "sequence": len(timeline) + 1})
    return latest_session, timeline


def generate_days(events, output_directory, beginning_day):
    if beginning_day < 1:
        raise ValueError("BEGINNING_DAY must be at least 1")
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    memory_path = output_directory / "story_memory.json"
    day = beginning_day
    while any(e.get("game_day") == day for e in events):
        document = build_document(events, day=day, memory=load_memory(memory_path))
        if len(document["sessions"]) != 1:
            raise ValueError("Expected one selected timeline")
        session = document["sessions"][0]
        prompt = session["prompt"]
        stem = output_directory / f"day{day:03d}"
        stem.with_suffix(".prompt.txt").write_text(
            prompt["system"] + "\n\n" + prompt["user"] + "\n", encoding="utf-8")
        print(f"Generating day {day} ({session['event_count']} recorded events)...", flush=True)

        path = stem.with_suffix(".json")

        if os.path.exists(path) and not FORCE_GENERATE_NEW:
            print(f"Skipping day {day}: {stem.with_suffix('.json')} already exists.", flush=True)
            day += 1
            continue

        response = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "messages": [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ], "stream": False, "format": "json"},
            timeout=600,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        # Keep the model response even if it is malformed, then stop rather than skip a day.
        stem.with_suffix(".response.txt").write_text(content, encoding="utf-8")
        try:
            story = parse_story(content)
        except (ValueError, TypeError) as error:
            raise ValueError(
                f"Day {day}: invalid story response ({error}). "
                f"Inspect {stem.with_suffix('.response.txt')}. Story memory was not changed."
            ) from None
        stem.with_suffix(".json").write_text(
            json.dumps({"day": day, "game_id": session["playthrough_id"],
                        "session_id": session["session_id"], "model": MODEL, **story},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stem.with_suffix(".txt").write_text(story["chronicle"] + "\n", encoding="utf-8")
        save_story(story, session, day, memory_path)
        print(f"Saved {stem.with_suffix('.txt')}", flush=True)
        day += 1
    print(f"Stopped: no recorded entries for day {day}.", flush=True)
    return day


def main():
    if not DATABASE.is_file():
        raise FileNotFoundError(f"Receiver database not found: {DATABASE}")
    # Snapshot the available records once; this script does not wait for live gameplay.
    with sqlite3.connect(DATABASE.resolve().as_uri() + "?mode=ro", uri=True) as db:
        events = [json.loads(row[0]) for row in db.execute("SELECT payload FROM events ORDER BY rowid")]
    session_id, timeline = game_timeline(events, GAME_ID)
    output = OUTPUT_DIRECTORY / GAME_ID / session_id
    print(f"Game {GAME_ID}, timeline {session_id}. Output: {output}", flush=True)
    generate_days(timeline, output, BEGINNING_DAY)


if __name__ == "__main__":
    main()
