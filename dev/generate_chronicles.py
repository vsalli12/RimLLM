"""Generate consecutive daily chronicles. Edit the settings below, then run this file."""
import argparse
import json
import os
from pathlib import Path
import sqlite3

import requests
import RAG_main
from image_generation import ensure_entry_scribble
from prompt_constructor import BACKSTORY_CACHE, build_document
from story_memory import lineage, load_memory, parse_story, save_story
from diary_book import ensure_book, generate_prologue

# Settings: GAME_ID is the packets' playthrough_id, not a session index.
GAME_ID = "34593c2935574ecca86402bcd1d688f3"
BEGINNING_DAY = 1
ENDING_DAY = None
MODEL = "qwen3.5:4b"
DIRECTORY = Path(__file__).resolve().parent
DATABASE = DIRECTORY / "events.sqlite3"
OUTPUT_DIRECTORY = DIRECTORY / "chronicles"
OLLAMA_URL = "http://localhost:11434/api/chat"
CONTEXT_TOKENS = 16384
OUTPUT_TOKENS = 4096
FORCE_GENERATE_NEW = True
GENERATE_SCRIBBLES = False


def game_timeline(events, game_id, session_id=None):
    """Use a selected session (latest by default) and its saved ancestors."""
    game = [e for e in events if e.get("playthrough_id") == game_id]
    if not game:
        raise ValueError(f"No events found for GAME_ID {game_id}")
    starts = [e for e in game if e["type"] == "session.started"]
    latest_session = session_id or (starts[-1] if starts else game[-1])["session_id"]
    if not any(e['session_id'] == latest_session for e in game):
        raise ValueError(f"Session {latest_session} not found in game {game_id}")
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


def illustrate_entry(path):
    if not GENERATE_SCRIBBLES:
        return
    try:
        ensure_entry_scribble(path)
    except (OSError, ValueError, KeyError, RuntimeError, requests.RequestException) as error:
        print(f"Diary text is saved; scribble could not be generated: {error}. "
              f"Retry with image_generation.py on {path}", flush=True)


def generate_days(events, output_directory, beginning_day, ending_day=None):
    if beginning_day < 1:
        raise ValueError("BEGINNING_DAY must be at least 1")
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    memory_path = output_directory / "story_memory.json"
    day = beginning_day
    while any(e.get("game_day") == day for e in events):

        if ending_day is not None and day > ending_day:
            print(f"Stopping at day {day} because ENDING_DAY={ending_day}.", flush=True)
            break

        
        stem = output_directory / f"day{day:03d}"
        day_events = (e for e in events if e.get("game_day") == day)
        stem.with_suffix(".raw_event_log.txt").write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in day_events) + "\n",
            encoding="utf-8",
        )

        
        if stem.with_suffix(".json").exists() and not FORCE_GENERATE_NEW:
            print(f"Skipping day {day}: {stem.with_suffix('.json')} already exists.", flush=True)
            illustrate_entry(stem.with_suffix(".json"))
            day += 1
            continue

        document = build_document(events, day=day, memory=load_memory(memory_path),
                                  backstory_cache=BACKSTORY_CACHE)
        if not document["sessions"]:
            print(f"Skipping day {day}: no events were recorded while the diary was carried.", flush=True)
            day += 1
            continue
        if len(document["sessions"]) != 1:
            raise ValueError("Expected one selected timeline")
        session = document["sessions"][0]
        prompt = dict(session["prompt"])
        raw_log = session["event_log"]
        if not raw_log or prompt["user"].count(raw_log) != 1:
            raise ValueError(f"Day {day}: cannot locate a unique event-log section")
        stem.with_suffix(".events.raw.txt").write_text(raw_log, encoding="utf-8")
        cleaned_log = RAG_main.clean_event_log(raw_log)
        if not isinstance(cleaned_log, str) or not cleaned_log.strip():
            raise ValueError(f"Day {day}: event cleanup returned no text")
        stem.with_suffix(".events.cleaned.txt").write_text(cleaned_log, encoding="utf-8")
        prompt["user"] = prompt["user"].replace(
            raw_log, "Today's events (cleaned from recorded events):\n" + cleaned_log.strip(), 1)
        #print(prompt["user"], flush=True)
        #RAG_main.additional_context_pass(prompt["user"])
        enriched_prompt = RAG_main.add_context(prompt["user"])
        #print(enriched_prompt)
        
        stem = output_directory / f"day{day:03d}"
        stem.with_suffix(".prompt.txt").write_text(
            prompt["system"] + "\n\n" + enriched_prompt + "\n", encoding="utf-8")
        print(f"Generating day {day} ({session['event_count']} recorded events)...", flush=True)
        
        response = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "messages": [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": enriched_prompt},
            ], "stream": False, "format": "json", 'think': True,
                  "options": {"num_ctx": CONTEXT_TOKENS, "num_predict": OUTPUT_TOKENS}},
            timeout=600,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["message"]["content"]
        # Keep the model response even if it is malformed, then stop rather than skip a day.
        stem.with_suffix(".response.txt").write_text(content, encoding="utf-8")
        if payload.get('done_reason') == 'length':
            raise ValueError(
                f"Day {day}: Ollama reached its context or output token limit. "
                "Increase CONTEXT_TOKENS/OUTPUT_TOKENS or shorten the prompt. "
                "Partial response saved; story memory was not changed."
            )
        try:
            story = parse_story(content, day=day)
        except (ValueError, TypeError) as error:
            raise ValueError(
                f"Day {day}: invalid story response ({error}). "
                f"Inspect {stem.with_suffix('.response.txt')}. Story memory was not changed."
            ) from None
        stem.with_suffix(".json").write_text(
            json.dumps({"day": day, "game_id": session["playthrough_id"],
                        "session_id": session["session_id"], "model": MODEL, **story,
                        "narrator_name": session.get("narrator_name", "")},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stem.with_suffix(".txt").write_text(story["chronicle"] + "\n", encoding="utf-8")
        save_story(story, session, day, memory_path)
        print(f"Saved {stem.with_suffix('.txt')}", flush=True)
        illustrate_entry(stem.with_suffix(".json"))
        day += 1
    print(f"Stopped: no recorded entries for day {day}.", flush=True)
    return day


def main():
    global GAME_ID, MODEL, CONTEXT_TOKENS, OUTPUT_TOKENS, FORCE_GENERATE_NEW, GENERATE_SCRIBBLES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path, help='Settings JSON saved by the dashboard')
    parser.add_argument('--beginning-day', type=int, default=BEGINNING_DAY)
    args = parser.parse_args()
    ending_day = ENDING_DAY
    if args.settings:
        from diary_settings import load_settings
        if not args.settings.is_file():
            parser.error('Settings file does not exist')
        settings = load_settings(args.settings)
        GAME_ID = settings['game_id']
        MODEL = settings['model']
        CONTEXT_TOKENS = settings['context_tokens']
        OUTPUT_TOKENS = settings['output_tokens']
        FORCE_GENERATE_NEW = settings['force_generate_new']
        GENERATE_SCRIBBLES = settings['generate_scribbles']
        args.beginning_day = settings['beginning_day']
        ending_day = settings['ending_day']
    if not DATABASE.is_file():
        raise FileNotFoundError(f"Receiver database not found: {DATABASE}")
    # Snapshot the available records once; this script does not wait for live gameplay.
    with sqlite3.connect(DATABASE.resolve().as_uri() + "?mode=ro", uri=True) as db:
        events = [json.loads(row[0]) for row in db.execute("SELECT payload FROM events ORDER BY rowid")]
    session_id, timeline = game_timeline(events, GAME_ID)
    output = OUTPUT_DIRECTORY / GAME_ID / session_id
    print(f"Game {GAME_ID}, timeline {session_id}. Output: {output}", flush=True)
    book = ensure_book(timeline, output)
    generate_prologue(book, output, model=MODEL, url=OLLAMA_URL,
                      context_tokens=CONTEXT_TOKENS, output_tokens=OUTPUT_TOKENS)
    generate_days(timeline, output, args.beginning_day, ending_day)


if __name__ == "__main__":
    main()
