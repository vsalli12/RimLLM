"""Validated, persistent settings shared by the dashboard and generator."""
import json
import re
from pathlib import Path

SETTINGS_PATH = Path(__file__).with_name("diary_settings.json")
DEFAULTS = dict(game_id="", beginning_day=1, ending_day=None,
                model="qwen3.5:4b", context_tokens=16384, output_tokens=4096,
                force_generate_new=False, generate_scribbles=False)


def validate_settings(value):
    if isinstance(value, dict):
        value = {key: item for key, item in value.items() if key != "session_id"}
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Unrecognized settings")
    result = {**DEFAULTS, **value}
    for key in ("game_id", "model"):
        if not isinstance(result[key], str) or len(result[key]) > 200:
            raise ValueError(f"Invalid {key}")
        result[key] = result[key].strip()
    for key in ("game_id",):
        if result[key] and not re.fullmatch(r"[A-Za-z0-9_-]+", result[key]):
            raise ValueError(f"Invalid {key}")
    if not result["model"]:
        raise ValueError("Choose an Ollama model")
    for key in ("beginning_day", "ending_day", "context_tokens", "output_tokens"):
        if key == "ending_day" and result[key] is None:
            continue
        if type(result[key]) is not int or not 1 <= result[key] <= 1000000:
            raise ValueError(f"{key} must be a positive integer up to 1000000")
    if result["ending_day"] is not None and result["ending_day"] < result["beginning_day"]:
        raise ValueError("Ending day must be at least the beginning day")
    for key in ("force_generate_new", "generate_scribbles"):
        if type(result[key]) is not bool:
            raise ValueError(f"{key} must be true or false")
    return result


def load_settings(path=SETTINGS_PATH):
    return validate_settings(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else dict(DEFAULTS)
