"""Mock OpenAI-compatible server for testing the Truss agent loop.

Simulates a model that:
1. First call: requests the create_lead tool
2. Second call (after tool result): returns a final text answer
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

CALL_COUNT = {"n": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet

    def do_POST(self):
        if not self.path.endswith("/chat/completions"):
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        # verify auth header present
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer test-key-123"):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"bad key"}')
            return

        CALL_COUNT["n"] += 1
        messages = body.get("messages", [])
        has_tool_result = any(m.get("role") == "tool" for m in messages)

        if not has_tool_result:
            # first turn: request a tool call
            choice_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_mock_1",
                    "type": "function",
                    "function": {
                        "name": "truss_crm__create_lead",
                        "arguments": json.dumps({
                            "name": "AI Test Lead",
                            "email": "ai-test@example.com",
                            "source": "Website",
                            "status": "New",
                        }),
                    },
                }],
            }
        else:
            # second turn: final answer
            choice_msg = {
                "role": "assistant",
                "content": "Done — I created the lead 'AI Test Lead' (ai-test@example.com) with source Website.",
            }

        resp = {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "model": body.get("model", "mock-model"),
            "choices": [{"index": 0, "message": choice_msg, "finish_reason": "stop"}],
        }
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    server = HTTPServer((os.environ.get("MOCK_BIND", "127.0.0.1"), 9999), Handler)
    print("mock OpenAI server on :9999", flush=True)
    server.serve_forever()
