"""A minimal MemPalace-shaped MCP server for the tests.

Answers initialize, notifications/initialized and tools/call for
mempalace_status and mempalace_event_list with canned data, over Streamable
HTTP (JSON or SSE responses, optional bearer token) or over stdio.

    python3 tests/fake_hub.py --http 0 [--token T] [--sse]
    python3 tests/fake_hub.py --stdio
"""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

AGENT = "test-agent"
DRAWERS = 1234
EVENTS = [
    {"id": "evt_task_unacked", "type": "task.request", "from_agent": "other-agent", "to_agent": AGENT,
     "correlation_id": "task_unacked_1", "status": "open", "created_at": "2026-10-01T00:00:00Z",
     "body": "Please do the unacked thing"},
    {"id": "evt_task_acked", "type": "task.request", "from_agent": "other-agent", "to_agent": AGENT,
     "correlation_id": "task_acked_2", "status": "open", "created_at": "2026-10-02T00:00:00Z",
     "body": "Already claimed thing"},
    {"id": "evt_broadcast", "type": "task.request", "from_agent": "other-agent", "to_agent": "*",
     "correlation_id": "task_broadcast_3", "status": "open", "created_at": "2026-10-03T00:00:00Z",
     "body": "Broadcast thing"},
    {"id": "evt_not_mine", "type": "task.request", "from_agent": "other-agent", "to_agent": "someone-else",
     "correlation_id": "task_other_4", "status": "open", "created_at": "2026-10-03T00:00:00Z",
     "body": "Not for test-agent"},
    {"id": "evt_my_ack", "type": "event.ack", "from_agent": AGENT, "to_agent": "other-agent",
     "correlation_id": "task_acked_2", "status": "claimed", "created_at": "2026-10-02T01:00:00Z",
     "body": "claimed", "metadata": {"ack_of": "evt_task_acked"}},
]


def tool_result(data, is_error=False):
    result = {"content": [{"type": "text", "text": json.dumps(data)}]}
    if is_error:
        result["isError"] = True
    return result


def handle(message):
    method = message.get("method")
    rid = message.get("id")
    if rid is None:
        return None
    if method == "initialize":
        result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "fake-mempalace", "version": "0"}}
    elif method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "mempalace_status":
            result = tool_result({"total_drawers": DRAWERS, "wings": {}, "rooms": {}})
        elif name == "mempalace_event_list":
            events = EVENTS
            if args.get("to_agent"):
                events = [e for e in events if e["to_agent"] in (args["to_agent"], "*")]
            if args.get("from_agent"):
                events = [e for e in events if e["from_agent"] == args["from_agent"]]
            if args.get("type"):
                events = [e for e in events if e["type"] == args["type"]]
            if args.get("status"):
                events = [e for e in events if e.get("status") == args["status"]]
            events = events[: int(args.get("limit") or 50)]
            result = tool_result({"events": events, "count": len(events)})
        else:
            result = tool_result("unknown tool %s" % name, is_error=True)
    else:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found: %s" % method}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


class Handler(BaseHTTPRequestHandler):
    token = None
    sse = False

    def log_message(self, *_args):
        pass

    def do_POST(self):
        if self.token and self.headers.get("Authorization") != "Bearer " + self.token:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Bearer resource_metadata="http://127.0.0.1/.well-known/oauth-protected-resource"')
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            message = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            message = {}
        reply = handle(message)
        if reply is None:
            self.send_response(202)
            self.end_headers()
            return
        if self.sse:
            body = ("event: message\ndata: %s\n\n" % json.dumps(reply)).encode("utf-8")
            content_type = "text/event-stream"
        else:
            body = json.dumps(reply).encode("utf-8")
            content_type = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        if message.get("method") == "initialize":
            self.send_header("Mcp-Session-Id", "fake-session-1")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_stdio():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        reply = handle(message)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", type=int, help="port to listen on, 0 for any free port")
    parser.add_argument("--token")
    parser.add_argument("--sse", action="store_true", help="answer with text/event-stream bodies")
    parser.add_argument("--stdio", action="store_true")
    args = parser.parse_args()
    if args.stdio:
        serve_stdio()
        return
    Handler.token = args.token
    Handler.sse = args.sse
    server = HTTPServer(("127.0.0.1", args.http or 0), Handler)
    print("listening on %d" % server.server_address[1], flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
