"""Small local story store, isolated by playthrough and save ancestry."""
import json
from pathlib import Path
import re

MEMORY_PATH = Path(__file__).with_name("story_memory.json")


def load_memory(path=MEMORY_PATH):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def parse_story(content):
    text = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    story = json.loads(text)
    if not isinstance(story, dict) or not isinstance(story.get("chronicle"), str) or not story["chronicle"].strip():
        raise ValueError("Response needs a nonempty chronicle string")
    bits = story.get("story_bits")
    if not isinstance(bits, list) or any(not isinstance(b, (str, dict)) for b in bits):
        raise ValueError("Response needs a story_bits list of strings or summary objects")
    for bit in bits:
        if isinstance(bit, dict) and not isinstance(bit.get("summary"), str):
            raise ValueError("Each story-bit object needs a summary string")
    return story


def save_story(story, session, day, path=MEMORY_PATH):
    records = load_memory(path)
    key = (session["playthrough_id"], session["session_id"], day)
    records = [r for r in records if (r["playthrough_id"], r["session_id"], r["day"]) != key]
    records.append({"playthrough_id": key[0], "session_id": key[1], "day": day,
                    "source_end_sequence": session.get("source_end_sequence"),
                    "chronicle": story["chronicle"], "story_bits": story["story_bits"]})
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def lineage(events, playthrough_id, session_id):
    """Allowed sequence cutoff per session; stop if a checkpoint cannot be verified."""
    events = [e for e in events if e.get("playthrough_id") == playthrough_id]
    by_id = {e["event_id"]: e for e in events}
    starts = {e["session_id"]: e for e in events if e["type"] == "session.started"}
    allowed = {session_id: float("inf")}
    while session_id in starts:
        data = starts[session_id].get("data", {})
        parent = data.get("parent_session_id")
        checkpoint = by_id.get(data.get("parent_event_id"))
        if not parent or parent in allowed or not checkpoint or checkpoint["session_id"] != parent:
            break
        allowed[parent] = checkpoint["sequence"]
        session_id = parent
    return allowed


def prior_story_bits(memory, events, playthrough_id, session_id, day):
    allowed = lineage(events, playthrough_id, session_id)
    lines = []
    for record in sorted(memory, key=lambda r: r["day"]):
        if record["playthrough_id"] != playthrough_id or record["day"] >= day:
            continue
        source = record["session_id"]
        if source not in allowed:
            continue
        if source != session_id and (record.get("source_end_sequence") is None or record["source_end_sequence"] > allowed[source]):
            continue
        for bit in record["story_bits"]:
            text = bit if isinstance(bit, str) else bit["summary"]
            if isinstance(bit, dict) and bit.get("invented_interpretation"):
                text += " Interpretation: " + str(bit["invented_interpretation"])
            if text.strip():
                lines.append(f"- Day {record['day']}: {text}")
    return "\n".join(lines)
