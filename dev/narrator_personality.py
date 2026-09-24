"""Read and override the same per-game, per-pawn backstory used by generation."""
import hashlib
import json
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from story_memory import lineage

DIRECTORY = Path(__file__).resolve().parent
CACHE = DIRECTORY / 'backstory_cache'


def cache_path(game_id, pawn_id, directory=CACHE):
    key = hashlib.sha256(json.dumps([game_id, pawn_id], ensure_ascii=False).encode('utf-8')).hexdigest()
    return Path(directory) / f'{key}.json'


def read_backstory(game_id, pawn_id, directory=CACHE):
    try:
        value = json.loads(cache_path(game_id, pawn_id, directory).read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return ''
    if isinstance(value, dict) and value.get('game_id') == game_id and value.get('pawn_id') == pawn_id:
        return value.get('backstory', '') if isinstance(value.get('backstory'), str) else ''
    return ''


def write_backstory(game_id, pawn_id, text, directory=CACHE):
    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
        raise ValueError('Enter between 1 and 20,000 characters of personality or backstory.')
    path = cache_path(game_id, pawn_id, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(dict(game_id=game_id, pawn_id=pawn_id, backstory=text.strip(), source='user'), stream, ensure_ascii=False, indent=2)
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return text.strip()


def narrators(game_id, database=DIRECTORY / 'events.sqlite3', directory=CACHE):
    if not isinstance(game_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', game_id):
        raise ValueError('Enter a valid game ID first.')
    if not Path(database).is_file():
        return {'narrators': [], 'selected': None}
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro', uri=True)) as db:
        events = [json.loads(row[0]) for row in db.execute('SELECT payload FROM events WHERE playthrough_id=? ORDER BY rowid', (game_id,))]
    if not events:
        return {'narrators': [], 'selected': None}
    starts = [e for e in events if e['type'] == 'session.started']
    latest = (starts[-1] if starts else events[-1])['session_id']
    allowed = lineage(events, game_id, latest)
    ordered = [e for session in reversed(list(allowed)) for e in sorted(
        (e for e in events if e['session_id'] == session and e['sequence'] <= allowed[session]), key=lambda e: e['sequence'])]
    owners, names = [], {}
    for event in ordered:
        data = event.get('data', {})
        if event['type'] == 'pawn.profile':
            names[data.get('pawn_id')] = data.get('name')
        owner = event.get('diary_carrier_id')
        if owner:
            if owner in owners:
                owners.remove(owner)
            owners.append(owner)
    return {'selected': owners[-1] if owners else None, 'narrators': [
        {'pawn_id': pawn, 'name': names.get(pawn) or pawn, 'backstory': read_backstory(game_id, pawn, directory)} for pawn in owners]}
