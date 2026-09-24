"""Run this file, then open http://127.0.0.1:8766 to read generated chronicles."""
import json
import hashlib
import re
from urllib.parse import quote, unquote, urlsplit
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent
PORT = 8766


def image_file(url):
    parts = unquote(urlsplit(url).path).split("/")
    if len(parts) != 5 or parts[1] != "scribbles":
        return None
    game, session, name = parts[2:]
    if not all(re.fullmatch(r"[A-Za-z0-9_-]+", value) for value in (game, session)):
        return None
    if not re.fullmatch(r"day[0-9]+\.scribble\.[a-f0-9]{16}\.png", name):
        return None
    root = (DIRECTORY / "chronicles").resolve()
    path = (root / game / session / name).resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


def scribble_url(entry, folder):
    metadata = entry.get("scribble")
    if not isinstance(metadata, dict):
        return None
    digest = hashlib.sha256(entry["chronicle"].encode("utf-8")).hexdigest()
    if metadata.get("source_hash") != digest:
        return None
    filename = metadata.get("filename")
    if not isinstance(filename, str):
        return None
    url = f"/scribbles/{quote(folder.parent.name)}/{quote(folder.name)}/{quote(filename, safe='')}"
    return url if image_file(url) else None


def load_diaries():
    diaries = []
    for folder in (DIRECTORY / "chronicles").glob("*/*"):
        entries = []
        for path in folder.glob("day*.json"):
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
                if type(entry.get("day")) is int and isinstance(entry.get("chronicle"), str):
                    title = entry.get("page_title")
                    entries.append({"day": entry["day"], "text": entry["chronicle"],
                                    "page_title": title.strip() if isinstance(title, str) else "",
                                    "image_url": scribble_url(entry, folder)})
            except (OSError, ValueError, AttributeError):
                continue  # A generation may still be writing this file.
        if entries:
            diaries.append({"game": folder.parent.name, "timeline": folder.name,
                            "entries": sorted(entries, key=lambda entry: entry["day"]),
                            "updated": folder.stat().st_mtime})
    return sorted(diaries, key=lambda diary: diary["updated"], reverse=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            body = (DIRECTORY / "diary.html").read_bytes()
            content_type = "text/html; charset=utf-8"
        elif self.path == "/diaries":
            body = json.dumps(load_diaries(), ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        elif urlsplit(self.path).path.startswith("/scribbles/"):
            path = image_file(self.path)
            if path is None:
                self.send_error(404)
                return
            try:
                body = path.read_bytes()
            except OSError:
                self.send_error(404)
                return
            content_type = "image/png"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    with HTTPServer(("127.0.0.1", PORT), Handler) as server:
        print(f"Read your diary at http://127.0.0.1:{PORT} — Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
