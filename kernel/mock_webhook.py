"""Mock webhook receiver: records every POST for the Phase 3 test."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

RECEIVED = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else ""
        RECEIVED.append({
            "path": self.path,
            "signature": self.headers.get("X-Truss-Signature", ""),
            "body": body,
        })
        print(f"RECEIVED #{len(RECEIVED)}: {body[:120]}", flush=True)
        resp = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def do_GET(self):
        # test helper: dump what we received
        data = json.dumps(RECEIVED).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 9998), Handler)
    print("mock webhook receiver on :9998", flush=True)
    server.serve_forever()
