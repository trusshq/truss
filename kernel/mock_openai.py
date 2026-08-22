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

        # find the last user message to decide which tool to simulate
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                last_user = m["content"].lower()
                break
        wants_analytics = "how many" in last_user or "analytics" in last_user

        def _tc(call_id, name, args):
            return {
                "id": call_id, "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }

        if not has_tool_result:
            # first turn: request a tool call, routed by intent keywords
            if "hire" in last_user and ("agent" in last_user or "employee" in last_user):
                tool_call = _tc("call_mock_hire", "kernel__hire_agent",
                                {"name": "Mock Hire", "role": "Assistant", "icon": "🤖"})
            elif "assign" in last_user and "task" in last_user:
                tool_call = _tc("call_mock_assign", "kernel__assign_task",
                                {"agent_id": "00000000-0000-0000-0000-000000000000", "title": "Mock task"})
            elif "goal" in last_user and ("create" in last_user or "set" in last_user or "add" in last_user):
                tool_call = _tc("call_mock_goal", "kernel__create_goal",
                                {"title": "Mock goal", "metric": "leads", "target_value": 10})
            elif "list objects" in last_user or "what objects" in last_user:
                tool_call = _tc("call_mock_objs", "kernel__list_objects", {})
            elif "list agents" in last_user or "who are" in last_user or "employees" in last_user:
                tool_call = _tc("call_mock_agents", "kernel__list_agents", {})
            elif ("create" in last_user or "build" in last_user) and ("object" in last_user or "table" in last_user) and "field" not in last_user:
                tool_call = _tc("call_mock_obj", "kernel__create_object", {
                    "slug": "project", "name": "Project", "icon": "📁",
                    "fields": [
                        {"slug": "name", "name": "Name", "type": "text", "required": True},
                        {"slug": "budget", "name": "Budget", "type": "currency"},
                        {"slug": "deadline", "name": "Deadline", "type": "date"},
                    ],
                })
            elif "add" in last_user and "field" in last_user:
                tool_call = _tc("call_mock_field", "kernel__add_field", {
                    "object": "lead", "slug": "priority", "name": "Priority", "type": "select",
                })
            elif "find" in last_user or "search everywhere" in last_user or "search the workspace" in last_user:
                tool_call = _tc("call_mock_gsearch", "kernel__global_search", {"q": "Acme"})
            elif wants_analytics:
                tool_call = _tc("call_mock_analytics", "kernel__analytics",
                                {"object": "lead", "metric": "count"})
            else:
                tool_call = _tc("call_mock_1", "truss_crm__create_lead", {
                    "name": "AI Test Lead",
                    "email": "ai-test@example.com",
                    "source": "Website",
                    "status": "New",
                })
            choice_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": [tool_call],
            }
        else:
            # second turn: final answer
            if wants_analytics:
                answer = "You have 5 leads in total."
            elif "hire" in last_user:
                answer = "Done — I hired the AI employee 'Mock Hire'."
            elif "assign" in last_user and "task" in last_user:
                answer = "Done — I assigned the task (pending approval)."
            elif "goal" in last_user:
                answer = "Done — I created the goal 'Mock goal'."
            elif "list objects" in last_user or "what objects" in last_user:
                answer = "Here are the objects in your workspace."
            elif "list agents" in last_user or "who are" in last_user or "employees" in last_user:
                answer = "Here are your AI employees."
            elif ("create" in last_user or "build" in last_user) and ("object" in last_user or "table" in last_user) and "field" not in last_user:
                answer = "Done — I created the 'Project' object with 3 fields (name, budget, deadline)."
            elif "add" in last_user and "field" in last_user:
                answer = "Done — I added the 'priority' select field to leads."
            elif "find" in last_user or "search everywhere" in last_user or "search the workspace" in last_user:
                answer = "I searched the whole workspace for 'Acme' — here's what I found."
            else:
                answer = "Done — I created the lead 'AI Test Lead' (ai-test@example.com) with source Website."
            choice_msg = {
                "role": "assistant",
                "content": answer,
            }

        resp = {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "model": body.get("model", "mock-model"),
            "choices": [{"index": 0, "message": choice_msg, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
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
