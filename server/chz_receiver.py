"""HTTP-сервер для приёма данных ЧЗ от бар-ПК.

Запускается на сервере (100.122.143.1).
Бар-ПК POST'ит JSON на http://100.122.143.1:8765/chz
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"pong")
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if not self.path.startswith("/chz"):
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        data = json.loads(body)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_file = os.path.join(DATA_DIR, f"chz_summary_{timestamp}.json")
        full_file = os.path.join(DATA_DIR, f"chz_full_{timestamp}.json")

        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(data.get("summary", data), f, ensure_ascii=False, indent=2)

        if "full" in data:
            with open(full_file, "w", encoding="utf-8") as f:
                json.dump(data["full"], f, ensure_ascii=False, indent=2)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {"ok": True, "saved": [summary_file, full_file]}
        self.wfile.write(json.dumps(resp, ensure_ascii=False).encode())

    def log_message(self, fmt, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")


if __name__ == "__main__":
    port = 8765
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"CHZ receiver listening on port {port}")
    print(f"Bar PC should POST to: http://100.122.143.1:{port}/chz")
    server.serve_forever()
