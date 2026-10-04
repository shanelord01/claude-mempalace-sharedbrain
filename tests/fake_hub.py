"""A minimal MemPalace-shaped hub for the tests.

Answers initialize, notifications/initialized, tools/list and tools/call for
mempalace_status, mempalace_event_list and mempalace_mesh_peers with canned
data, over Streamable HTTP (JSON or SSE bodies, optional bearer token, plus
GET /healthz and GET /statusz) or over stdio.

    python3 tests/fake_hub.py --http 0 [--token T] [--sse] [--no-writer]
    python3 tests/fake_hub.py --stdio
"""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

AGENT = "office-desktop:claude:demo"
DRAWERS = 1234
# Append order, oldest first. since_event_id means strictly after that id in this order.
EVENTS = [
    {"id": "evt_01_task_unacked", "type": "task.request", "from_agent": "other-agent", "to_agent": AGENT,
     "correlation_id": "task_unacked_1", "status": "open", "created_at": "2026-10-01T00:00:00Z",
     "body": "Please do the unacked thing"},
    {"id": "evt_02_task_acked", "type": "task.request", "from_agent": "other-agent", "to_agent": AGENT,
     "correlation_id": "task_acked_2", "status": "open", "created_at": "2026-10-02T00:00:00Z",
     "body": "Already claimed thing"},
    {"id": "evt_03_my_ack", "type": "event.ack", "from_agent": AGENT, "to_agent": "other-agent",
     "correlation_id": "task_acked_2", "status": "claimed", "created_at": "2026-10-02T01:00:00Z",
     "body": "claimed", "metadata": {"ack_of": "evt_02_task_acked"}},
    {"id": "evt_04_broadcast", "type": "task.request", "from_agent": "other-agent", "to_agent": "*",
     "correlation_id": "task_broadcast_3", "status": "open", "created_at": "2026-10-03T00:00:00Z",
     "body": "Broadcast thing"},
    {"id": "evt_05_not_mine", "type": "task.request", "from_agent": "other-agent", "to_agent": "someone-else",
     "correlation_id": "task_other_4", "status": "open", "created_at": "2026-10-03T00:00:00Z",
     "body": "Not for office-desktop"},
    {"id": "evt_06_reply_blocked", "type": "task.reply", "from_agent": "other-agent", "to_agent": AGENT,
     "correlation_id": "task_acked_2", "status": "blocked", "created_at": "2026-10-03T01:00:00Z",
     "body": "Blocked: need the base commit"},
    {"id": "evt_07_status_other", "type": "status", "from_agent": "other-agent", "to_agent": "*",
     "correlation_id": None, "status": None, "created_at": "2026-10-03T02:00:00Z",
     "body": "other-agent is MONITORING"},
    {"id": "evt_08_my_broadcast", "type": "status", "from_agent": AGENT, "to_agent": "*",
     "correlation_id": None, "status": None, "created_at": "2026-10-03T03:00:00Z",
     "body": "office-desktop:claude:demo is MONITORING"},
]
WRITER_PARAM = True


def tool_result(data, is_error=False):
    result = {"content": [{"type": "text", "text": json.dumps(data)}]}
    if is_error:
        result["isError"] = True
    return result


def event_list(args):
    events = list(EVENTS)
    since = args.get("since_event_id")
    if since:
        ids = [e["id"] for e in events]
        events = events[ids.index(since) + 1:] if since in ids else []
    if args.get("to_agent"):
        events = [e for e in events if e["to_agent"] in (args["to_agent"], "*")]
    if args.get("writer"):
        events = [e for e in events if e["from_agent"] == args["writer"]]
    elif args.get("from_agent") and not WRITER_PARAM:
        events = [e for e in events if e["from_agent"] == args["from_agent"]]
    for key in ("type", "status", "correlation_id", "topic"):
        if args.get(key):
            events = [e for e in events if e.get(key) == args[key]]
    order = args.get("order") or ("asc" if since else "desc")
    if order == "desc":
        events = list(reversed(events))
    events = events[: int(args.get("limit") or 50)]
    if args.get("preview"):
        events = [dict(e, body=e["body"][:40], body_truncated=len(e["body"]) > 40) for e in events]
    return {"events": events, "count": len(events)}


def tools_list():
    props = {"to_agent": {}, "from_agent": {}, "type": {}, "status": {}, "correlation_id": {},
             "topic": {}, "since_event_id": {}, "limit": {}, "order": {}, "preview": {}}
    if WRITER_PARAM:
        props["writer"] = {}
    return {"tools": [
        {"name": "mempalace_status", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "mempalace_event_list", "inputSchema": {"type": "object", "properties": props}},
        {"name": "mempalace_mesh_peers", "inputSchema": {"type": "object", "properties": {}}},
    ]}


def handle(message):
    method = message.get("method")
    rid = message.get("id")
    if rid is None:
        return None
    if method == "initialize":
        result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "fake-mempalace", "version": "0"}}
    elif method == "tools/list":
        result = tools_list()
    elif method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "mempalace_status":
            result = tool_result({"total_drawers": DRAWERS, "wings": {}, "rooms": {},
                                  "library_versions": {"serving": {"mempalace": "9.9.9-fake"}}})
        elif name == "mempalace_event_list":
            result = tool_result(event_list(args))
        elif name == "mempalace_mesh_peers":
            result = tool_result({"replica_id": "rep_fake", "peers": [
                {"name": "desktop", "reachable": True, "last_sync": "ok"}], "estate_source": "process"})
        else:
            result = tool_result("unknown tool %s" % name, is_error=True)
    else:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found: %s" % method}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


class Handler(BaseHTTPRequestHandler):
    token = None
    sse = False
    oauth_secret = None

    def log_message(self, *_args):
        pass

    def _authorised(self):
        return not self.token or self.headers.get("Authorization") == "Bearer " + self.token

    def _send(self, code, body, content_type="application/json", extra=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            self._send(200, "ok", "text/plain")
        elif self.path == "/statusz":
            if not self._authorised():
                self._send(401, "", "text/plain")
            else:
                self._send(200, json.dumps({"ok": True, "server": {"version": "9.9.9-fake", "uptime_seconds": 42},
                                            "clients": {"recent": []}}))
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path == "/api/oidc/token":
            length = int(self.headers.get("Content-Length") or 0)
            from urllib.parse import parse_qs
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode("utf-8")).items()}
            if form.get("grant_type") != "client_credentials" or form.get("client_secret") != (self.oauth_secret or ""):
                self._send(401, json.dumps({"error": "invalid_client"}))
                return
            self._send(200, json.dumps({"access_token": self.token or "cc-token", "token_type": "Bearer",
                                        "expires_in": 3600, "resource": form.get("resource"), "scope": form.get("scope")}))
            return
        if not self._authorised():
            self._send(401, "", "text/plain",
                       {"WWW-Authenticate": 'Bearer resource_metadata="http://127.0.0.1/.well-known/oauth-protected-resource"'})
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
        extra = {"Mcp-Session-Id": "fake-session-1"} if message.get("method") == "initialize" else {}
        if self.sse:
            self._send(200, "event: message\ndata: %s\n\n" % json.dumps(reply), "text/event-stream", extra)
        else:
            self._send(200, json.dumps(reply), "application/json", extra)


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
    global WRITER_PARAM
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", type=int, help="port to listen on, 0 for any free port")
    parser.add_argument("--token")
    parser.add_argument("--sse", action="store_true")
    parser.add_argument("--no-writer", action="store_true", help="older hub: event_list has no writer param")
    parser.add_argument("--oauth-secret", help="serve a client-credentials token endpoint at /api/oidc/token accepting this secret")
    parser.add_argument("--stdio", action="store_true")
    args = parser.parse_args()
    WRITER_PARAM = not args.no_writer
    if args.stdio:
        serve_stdio()
        return
    Handler.token = args.token
    Handler.sse = args.sse
    Handler.oauth_secret = args.oauth_secret
    server = HTTPServer(("127.0.0.1", args.http or 0), Handler)
    print("listening on %d" % server.server_address[1], flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
