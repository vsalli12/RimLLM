"""Run this file, then open http://127.0.0.1:8766 to read generated chronicles."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent
PORT = 8766


def load_diaries():
    diaries = []
    for folder in (DIRECTORY / "chronicles").glob("*/*"):
        entries = []
        for path in folder.glob("day*.json"):
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
                if type(entry.get("day")) is int and isinstance(entry.get("chronicle"), str):
                    entries.append({"day": entry["day"], "text": entry["chronicle"]})
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
