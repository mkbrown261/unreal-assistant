"""
mcp_server.py
HTTP server that runs inside Unreal Engine via the Python Script Plugin.
Listens on 0.0.0.0:8080 in a background thread so the editor stays responsive.

Endpoints:
  POST /unreal/execute   — Accept {"commands":[...]} and run them via blueprint_executor
  GET  /unreal/status    — Health check, returns server info

Started automatically by init_unreal.py when the plugin is enabled.
Can also be started manually from Unreal's Python console:
  import mcp_server; mcp_server.start()
"""

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

import blueprint_executor

# ── Config ────────────────────────────────────────────────────────────────────

HOST = "0.0.0.0"
PORT = 8080

# ── Global server reference ───────────────────────────────────────────────────

_server: HTTPServer | None = None
_thread: threading.Thread | None = None


# ── Request handler ───────────────────────────────────────────────────────────

class MCPRequestHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Route access logs through Unreal's print so they show in Output Log
        try:
            import unreal
            unreal.log(f"[MCPBlueprint] {self.address_string()} - {format % args}")
        except Exception:
            print(f"[MCPBlueprint] {self.address_string()} - {format % args}")

    def send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        # CORS preflight — let the MCP Node.js server call from any origin
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/unreal/status":
            self.send_json({
                "status": "ok",
                "server": "MCPBlueprint",
                "version": "1.0.0",
                "host": HOST,
                "port": PORT,
                "engine": "Unreal Engine 5",
                "mode": "Python Plugin (no compilation required)",
            })
        else:
            self.send_json({"error": f"Unknown route: {self.path}"}, 404)

    def do_POST(self):
        if self.path != "/unreal/execute":
            self.send_json({"error": f"Unknown route: {self.path}"}, 404)
            return

        # Read body
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self.send_json({"error": "Empty request body"}, 400)
            return

        raw = self.rfile.read(length)

        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            self.send_json({"error": f"Invalid JSON: {e}"}, 400)
            return

        commands = body.get("commands")
        if not isinstance(commands, list) or len(commands) == 0:
            self.send_json({"error": "'commands' must be a non-empty array"}, 400)
            return

        # Execute blueprint commands on the main thread via Unreal's tick mechanism.
        # The http.server runs in a background thread; Blueprint API calls must
        # happen on the game thread. We use a threading.Event to block until done.
        result_holder = {}
        done_event = threading.Event()

        def run_on_game_thread():
            try:
                result_holder["result"] = blueprint_executor.execute_batch(commands)
            except Exception:
                result_holder["result"] = {
                    "success": False,
                    "error": traceback.format_exc(),
                    "results": [],
                }
            finally:
                done_event.set()

        # Schedule execution on Unreal's game thread
        try:
            import unreal
            # unreal.call_on_game_thread executes a callable on the next engine tick
            unreal.call_on_game_thread(run_on_game_thread)
            done_event.wait(timeout=30)  # Wait up to 30s for Unreal to respond
        except (ImportError, AttributeError):
            # Fallback: run directly (will work for testing outside Unreal)
            run_on_game_thread()

        result = result_holder.get("result", {"success": False, "error": "Timeout waiting for game thread"})
        status = 200 if result.get("success") else 500
        self.send_json(result, status)


# ── Start / Stop ──────────────────────────────────────────────────────────────

def start(port: int = PORT):
    """Start the MCP HTTP server in a background daemon thread."""
    global _server, _thread

    if _server is not None:
        _log("MCP server is already running")
        return

    try:
        _server = HTTPServer((HOST, port), MCPRequestHandler)
    except OSError as e:
        _log(f"ERROR: Could not bind to port {port}: {e}")
        _log("Is another process already using port 8080? Kill it or change PORT in mcp_server.py")
        return

    _thread = threading.Thread(target=_server.serve_forever, daemon=True, name="MCPBlueprintHTTP")
    _thread.start()

    _log(f"MCP HTTP server ready → POST http://localhost:{port}/unreal/execute")
    _log(f"Health check         → GET  http://localhost:{port}/unreal/status")


def stop():
    """Stop the MCP HTTP server."""
    global _server, _thread

    if _server is None:
        _log("MCP server is not running")
        return

    _server.shutdown()
    _server = None
    _thread = None
    _log("MCP HTTP server stopped")


def restart(port: int = PORT):
    stop()
    start(port)


def is_running() -> bool:
    return _server is not None


def _log(msg: str):
    try:
        import unreal
        unreal.log(f"[MCPBlueprint] {msg}")
    except ImportError:
        print(f"[MCPBlueprint] {msg}")
