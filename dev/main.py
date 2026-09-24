"""Local RimChronicle dashboard: python dev/main.py."""
import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import HTTPServer, ThreadingHTTPServer
from urllib.request import urlopen
from urllib.parse import urlsplit, parse_qs

from host_frontend import DIRECTORY, Handler as DiaryHandler
from diary_settings import SETTINGS_PATH, load_settings, validate_settings
from receiver import open_database, make_handler
from narrator_personality import narrators, write_backstory

PORT = 8766
SERVICES = {
    "receiver": "http://127.0.0.1:8765/health",
    "comfyui": "http://127.0.0.1:8188/system_stats",
    "ollama": "http://127.0.0.1:11434/api/tags",
}
LOCK = threading.Lock()
generation = None


def service_status(item):
    name, url = item
    try:
        with urlopen(url, timeout=2) as response:
            body = response.read()
        result = {"online": True}
        if name == "ollama":
            result["models"] = [m["name"] for m in json.loads(body)["models"]]
        return name, result
    except (OSError, ValueError, KeyError, TypeError):
        return name, {"online": False}


class Handler(DiaryHandler):
    def reply_json(self, value, status=200):
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlsplit(self.path).path == "/api/personalities":
            try:
                game_id = parse_qs(urlsplit(self.path).query).get('game_id', [''])[0]
                self.reply_json(narrators(game_id))
            except (OSError, ValueError) as error:
                self.reply_json({'error': str(error)}, 400)
        elif self.path == "/api/settings":
            try:
                self.reply_json(load_settings())
            except (OSError, ValueError) as error:
                self.reply_json({"error": str(error)}, 500)
        elif self.path == "/api/status":
            with ThreadPoolExecutor(max_workers=3) as pool:
                services = dict(pool.map(service_status, SERVICES.items()))
            with LOCK:
                code = generation.poll() if generation else None
                job = {"running": generation is not None and code is None, "exit_code": code}
            self.reply_json({"services": services, "generation": job})
        elif self.path == "/":
            body = (DIRECTORY / "dashboard.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            if self.path in ("/diary", "/diary/"):
                self.path = "/"
            super().do_GET()

    def do_POST(self):
        global generation
        if self.headers.get("Origin") != f"http://127.0.0.1:{self.server.server_port}":
            self.reply_json({"error": "Open the dashboard using its 127.0.0.1 address."}, 403)
            return
        try:
            if self.path == "/api/personalities":
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 100000:
                    raise ValueError('Invalid personality request size')
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict):
                    raise ValueError('Invalid personality request')
                game_id, pawn_id = value.get('game_id'), value.get('pawn_id')
                with LOCK:
                    if generation is not None and generation.poll() is None:
                        self.reply_json({'error': 'Wait for generation to finish before changing personality.'}, 409)
                        return
                    if pawn_id not in [n['pawn_id'] for n in narrators(game_id)['narrators']]:
                        raise ValueError('Select a recorded diary teller for this game.')
                    text = write_backstory(game_id, pawn_id, value.get('backstory'))
                self.reply_json({'backstory': text})
            elif self.path == "/api/settings":
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ValueError("Invalid settings request size")
                settings = validate_settings(json.loads(self.rfile.read(length)))
                with LOCK:
                    temporary = SETTINGS_PATH.with_suffix(".tmp")
                    temporary.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
                    temporary.replace(SETTINGS_PATH)
                self.reply_json(settings)
            elif self.path == "/api/generate":
                with LOCK:
                    if generation is not None and generation.poll() is None:
                        self.reply_json({"error": "Generation is already running."}, 409)
                        return
                    settings = load_settings()
                    if not settings["game_id"]:
                        raise ValueError("Set a game ID before generating.")
                    snapshot = DIRECTORY / "generation_settings.json"
                    snapshot.write_text(json.dumps(settings), encoding="utf-8")
                    generation = subprocess.Popen(
                        [sys.executable, "-u", str(DIRECTORY / "generate_chronicles.py"),
                         "--settings", str(snapshot)], cwd=DIRECTORY)
                self.reply_json({"started": True}, 202)
            else:
                self.reply_json({"error": "Not found"}, 404)
        except (OSError, ValueError) as error:
            self.reply_json({"error": str(error)}, 400)


@contextmanager
def managed_receiver(port=8765, database=DIRECTORY / "events.sqlite3"):
    """Run the receiver in this process so it cannot outlive the dashboard."""
    db = open_database(database)
    try:
        with HTTPServer(("127.0.0.1", port), make_handler(db)) as receiver:
            thread = threading.Thread(target=receiver.serve_forever, daemon=True)
            thread.start()
            try:
                yield receiver
            finally:
                receiver.shutdown()
                thread.join()
    finally:
        db.close()


def main():
    with ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as server, managed_receiver():
        print(f"RimChronicle: http://127.0.0.1:{PORT} (Ctrl+C to stop)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if generation is not None and generation.poll() is None:
                generation.terminate()
                generation.wait()


if __name__ == "__main__":
    main()
