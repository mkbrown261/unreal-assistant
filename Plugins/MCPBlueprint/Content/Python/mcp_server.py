"""
MCP Blueprint Server v3.0.0
Persistent HTTP server running inside Unreal Engine (port 8080).

Architecture (v3):
  Chat UI (this server at :8080)
    → Python HTTP server (this file, runs inside UE)
      → C++ TCP server at :55557  ← handles ALL Blueprint graph operations
        (UK2Node placement, pin wiring, compile)
    → Python blueprint_executor    ← fallback for create/variable/compile
                                      when C++ server is unavailable

Endpoints:
  GET  /                — redirect to /chat
  GET  /chat            — serve the chat UI HTML
  POST /chat            — receive user message, call OpenRouter, execute blueprints, return reply
  GET  /config          — return current config (key masked)
  POST /config          — update API key / model
  GET  /history         — return conversation history
  POST /history/clear   — wipe conversation history
  GET  /unreal/status   — health check
  POST /unreal/execute  — direct command execution
"""

import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from queue import Queue, Empty

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".mcp_blueprint_config.json")
_DEFAULT_CONFIG = {
    "api_key": "",
    "model": "anthropic/claude-sonnet-4-5",
}


def _load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                merged = dict(_DEFAULT_CONFIG)
                merged.update(data)
                return merged
        except Exception:
            pass
    return dict(_DEFAULT_CONFIG)


def _save_config(cfg):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[MCP] Warning: could not save config: {e}")


# ---------------------------------------------------------------------------
# Game-thread dispatch (works inside Unreal; graceful fallback outside)
# ---------------------------------------------------------------------------

_main_queue: Queue = Queue()


def _tick(_delta):
    """Called every editor tick from Slate post-tick callback."""
    try:
        while True:
            fn, result_box = _main_queue.get_nowait()
            try:
                result_box["result"] = fn()
            except Exception as exc:
                result_box["error"] = traceback.format_exc()
                print(f"[MCP] Main-thread error: {exc}")
            finally:
                result_box["done"] = True
    except Empty:
        pass
    return True


def _run_on_main_thread(fn, timeout=30):
    """Dispatch fn to the game thread and block until done (or timeout)."""
    box = {"done": False, "result": None, "error": None}
    _main_queue.put((fn, box))
    deadline = time.time() + timeout
    while not box["done"] and time.time() < deadline:
        time.sleep(0.05)
    if not box["done"]:
        return {"ok": False, "error": "Timed out waiting for game thread"}
    if box["error"]:
        return {"ok": False, "error": box["error"]}
    return {"ok": True, "result": box["result"]}


# ---------------------------------------------------------------------------
# Available models
# ---------------------------------------------------------------------------

MODELS = [
    {"id": "anthropic/claude-sonnet-4-5",        "name": "Claude Sonnet 4.5 (Recommended)"},
    {"id": "anthropic/claude-opus-4-5",           "name": "Claude Opus 4.5"},
    {"id": "anthropic/claude-3-7-sonnet",         "name": "Claude 3.7 Sonnet"},
    {"id": "anthropic/claude-3-5-haiku",          "name": "Claude Haiku 3.5 (Fast)"},
    {"id": "google/gemini-2.5-pro-preview",       "name": "Gemini 2.5 Pro"},
    {"id": "google/gemini-2.5-flash-preview",     "name": "Gemini 2.5 Flash"},
    {"id": "deepseek/deepseek-chat",              "name": "DeepSeek V3"},
    {"id": "deepseek/deepseek-r1",                "name": "DeepSeek R1 (Reasoning)"},
    {"id": "openai/gpt-4o",                       "name": "GPT-4o"},
    {"id": "openai/gpt-4o-mini",                  "name": "GPT-4o Mini (Fast)"},
]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

CHAT_SYSTEM_PROMPT = “””You are an Unreal Engine 5 Blueprint assistant running INSIDE the Unreal Editor.
You have access to a C++ plugin that can place nodes, wire pins, and compile Blueprints automatically.

When the user asks you to create or modify a Blueprint:
1. Briefly explain what you're building (1-2 sentences).
2. Emit ONE ```json ... ``` block with ALL Blueprint commands — including nodes and connections.
3. After the JSON, confirm what was built.

FULL COMMAND SCHEMA (v3 — C++ node placement):

create_blueprint:
  {“action”: “create_blueprint”, “name”: “BP_Name”, “parent_class”: “Actor”, “path”: “/Game/MCP”}

add_variable:
  {“action”: “add_variable”, “blueprint_path”: “/Game/MCP/BP_Name”, “var_name”: “Health”, “var_type”: “float”, “default_value”: “100.0”}

add_node:
  {“action”: “add_node”, “blueprint_name”: “BP_Name”, “node_type”: “Event”, “event_type”: “BeginPlay”, “pos_x”: 0, “pos_y”: 0}
  {“action”: “add_node”, “blueprint_name”: “BP_Name”, “node_type”: “Print”, “message”: “Hello!”, “pos_x”: 250, “pos_y”: 0}
  {“action”: “add_node”, “blueprint_name”: “BP_Name”, “node_type”: “Branch”, “pos_x”: 500, “pos_y”: 0}
  {“action”: “add_node”, “blueprint_name”: “BP_Name”, “node_type”: “VariableGet”, “variable_name”: “Health”, “pos_x”: 300, “pos_y”: 100}
  {“action”: “add_node”, “blueprint_name”: “BP_Name”, “node_type”: “VariableSet”, “variable_name”: “Health”, “pos_x”: 600, “pos_y”: 0}
  {“action”: “add_node”, “blueprint_name”: “BP_Name”, “node_type”: “Sequence”, “pos_x”: 400, “pos_y”: 0}
  {“action”: “add_node”, “blueprint_name”: “BP_Name”, “node_type”: “Delay”, “pos_x”: 400, “pos_y”: 0}
  {“action”: “add_node”, “blueprint_name”: “BP_Name”, “node_type”: “CallFunction”, “function_name”: “PrintString”, “pos_x”: 250, “pos_y”: 0}

connect_nodes:
  {“action”: “connect_nodes”, “blueprint_name”: “BP_Name”, “source_node_id”: “Event_0”, “source_pin”: “then”, “target_node_id”: “CallFunction_0”, “target_pin”: “execute”}

compile_blueprint:
  {“action”: “compile_blueprint”, “path”: “/Game/MCP/BP_Name”}

NODE IDs: add_node returns a node_id like “Event_0”, “CallFunction_0”, “IfThenElse_0”.
Use these IDs in connect_nodes.

PIN NAMES (use these exactly):
  Exec output: “then”
  Exec input:  “execute”
  Branch true: “true”  Branch false: “false”
  Branch condition: “condition”
  Sequence outputs: “then 0”, “then 1”, etc.

ORDERING RULES:
1. create_blueprint first
2. compile_blueprint immediately after create (before add_variable)
3. add_variable for all variables
4. add_node for all nodes (use pos_x +300 per step, pos_y 0 for main flow, +200 for branches)
5. connect_nodes for all wires
6. compile_blueprint last

EXAMPLE (enemy that prints on BeginPlay):
```json
{
  “commands”: [
    {“action”: “create_blueprint”, “name”: “BP_Enemy”, “parent_class”: “Character”, “path”: “/Game/MCP”},
    {“action”: “compile_blueprint”, “path”: “/Game/MCP/BP_Enemy”},
    {“action”: “add_variable”, “blueprint_path”: “/Game/MCP/BP_Enemy”, “var_name”: “Health”, “var_type”: “float”, “default_value”: “100.0”},
    {“action”: “add_node”, “blueprint_name”: “BP_Enemy”, “node_type”: “Event”, “event_type”: “BeginPlay”, “pos_x”: 0, “pos_y”: 0},
    {“action”: “add_node”, “blueprint_name”: “BP_Enemy”, “node_type”: “Print”, “message”: “Enemy spawned!”, “pos_x”: 300, “pos_y”: 0},
    {“action”: “connect_nodes”, “blueprint_name”: “BP_Enemy”, “source_node_id”: “Event_0”, “source_pin”: “then”, “target_node_id”: “CallFunction_0”, “target_pin”: “execute”},
    {“action”: “compile_blueprint”, “path”: “/Game/MCP/BP_Enemy”}
  ]
}
```

Supported parent_class values: Actor, Character, Pawn, GameModeBase, PlayerController,
  ActorComponent, SceneComponent, GameInstance, GameState, PlayerState, HUD,
  UserWidget, AnimInstance, BlueprintFunctionLibrary

Supported var_type: bool, int, float, string, name, text, vector, rotator, transform

NEVER tell the user to check the Output Log. All results appear in this chat.
Respond conversationally. After the JSON block confirm what was built.”””

# ---------------------------------------------------------------------------
# Conversation history (single-user, in-memory)
# ---------------------------------------------------------------------------

_conversation_history = []
_history_lock = threading.Lock()


# ---------------------------------------------------------------------------
# OpenRouter API call
# ---------------------------------------------------------------------------

def _call_openrouter(user_message, api_key, model):
    """Call OpenRouter chat completions API. Returns (reply_text, error_str)."""
    with _history_lock:
        _conversation_history.append({"role": "user", "content": user_message})
        messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}] + list(_conversation_history)

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2048,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://unreal-assistant.pages.dev",
            "X-Title": "MCP Blueprint Generator",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        reply = data["choices"][0]["message"]["content"]
        with _history_lock:
            _conversation_history.append({"role": "assistant", "content": reply})
        return reply, None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return None, f"HTTP {e.code}: {body}"
    except Exception as exc:
        return None, str(exc)


def _extract_json_commands(text):
    """Extract the first ```json ... ``` block from AI reply text."""
    m = re.search(r"```json\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
    # Fallback: bare JSON object containing "commands"
    m2 = re.search(r"\{[\s\S]*?\"commands\"[\s\S]*?\}", text)
    if m2:
        try:
            return json.loads(m2.group(0))
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# C++ TCP server bridge (port 55557)
# ---------------------------------------------------------------------------

_CPP_SERVER_AVAILABLE = None  # None = not yet checked, True/False after first call


def _call_cpp_server(cmd: dict, timeout: int = 10) -> dict:
    """Send a single command to the C++ TCP server on port 55557 and return the result dict."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 55557), timeout=timeout) as s:
            msg = json.dumps(cmd) + "\n"
            s.sendall(msg.encode("utf-8"))
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
            return json.loads(buf.decode("utf-8").strip())
    except Exception as e:
        return {"success": False, "error": str(e)}


def _cpp_server_alive() -> bool:
    """Return True if the C++ TCP server is reachable."""
    global _CPP_SERVER_AVAILABLE
    if _CPP_SERVER_AVAILABLE is True:
        return True
    result = _call_cpp_server({"action": "get_status"}, timeout=2)
    _CPP_SERVER_AVAILABLE = result.get("success", False)
    return _CPP_SERVER_AVAILABLE


# Commands that require C++ graph manipulation (Python has no bindings for these)
_CPP_ONLY_ACTIONS = {"add_node", "connect_nodes", "wire_pins"}

# Commands Python can handle directly (create/variable/compile work fine in Python)
_PYTHON_ACTIONS = {"create_blueprint", "compile_blueprint", "add_variable",
                    "add_member_variable", "add_function", "add_function_graph",
                    "blueprint_instructions"}


def _execute_commands(commands):
    """
    Execute blueprint command list.
    Routes:
      - add_node / connect_nodes → C++ TCP server (port 55557)
      - everything else → Python blueprint_executor (or C++ if available)
    Returns a human-readable summary string.
    """
    cpp_alive = _cpp_server_alive()
    results = []

    try:
        import blueprint_executor  # available inside Unreal
        python_available = True
    except ImportError:
        blueprint_executor = None
        python_available = False

    for cmd in commands:
        action = cmd.get("action", "unknown").lower()
        try:
            # ── Route to C++ server ────────────────────────────────────────
            if cpp_alive and (action in _CPP_ONLY_ACTIONS or action not in _PYTHON_ACTIONS):
                r = _call_cpp_server(cmd)
                if r.get("success"):
                    msg = r.get("message", r.get("node_id", "ok"))
                    results.append(f"  \u2705 {action}: {msg}")
                    # If it was add_node, stash the returned node_id back into cmd
                    # so subsequent connect_nodes commands can reference it.
                    if action == "add_node" and "node_id" in r:
                        cmd["_returned_node_id"] = r["node_id"]
                else:
                    err = r.get("error", "unknown error")
                    results.append(f"  \u26a0\ufe0f {action} (C++): {err}")
                    # Fall through to Python if C++ fails on a create/compile
                    if action in _PYTHON_ACTIONS and python_available:
                        r2 = blueprint_executor.execute_command(cmd)
                        results[-1] = f"  \u2705 {action} (py fallback): {r2}"

            # ── Route to Python executor ───────────────────────────────────
            elif python_available:
                r = blueprint_executor.execute_command(cmd)
                results.append(f"  \u2705 {action}: {r}")

            else:
                results.append(f"  \u26a0\ufe0f {action}: no executor available (running outside Unreal?)")

        except Exception as exc:
            results.append(f"  \u274c {action}: {exc}")
            try:
                import unreal
                unreal.log_error(f"[MCPBlueprint] {action} failed: {exc}")
            except Exception:
                pass

    return "\n".join(results) if results else "No commands executed."


# ---------------------------------------------------------------------------
# HTML loader
# ---------------------------------------------------------------------------

def _get_chat_ui_html():
    here = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(here, "chat_ui.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "<html><body><h1>chat_ui.html not found.</h1></body></html>"


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):  # suppress default stdout access log
        pass

    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json_response(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, code, html):
        body = html.encode("utf-8") if isinstance(html, str) else html
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(body)

    def _read_body_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return None  # signals parse error

    # ---- OPTIONS (CORS preflight) ------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    # ---- GET ------------------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?")[0]

        if path in ("/", "/chat"):
            self._html_response(200, _get_chat_ui_html())

        elif path == "/unreal/status":
            self._json_response(200, {
                "status": "ok",
                "version": "3.0.0",
                "cpp_server": _cpp_server_alive(),
            })

        elif path == "/config":
            cfg = _load_config()
            key = cfg.get("api_key", "")
            if len(key) > 8:
                masked = key[:4] + "..." + key[-4:]
            elif key:
                masked = "****"
            else:
                masked = ""
            self._json_response(200, {
                "api_key_set": bool(key),
                "api_key_masked": masked,
                "model": cfg.get("model", _DEFAULT_CONFIG["model"]),
                "models": MODELS,
            })

        elif path == "/history":
            with _history_lock:
                self._json_response(200, {"history": list(_conversation_history)})

        else:
            self._json_response(404, {"error": "Not found"})

    # ---- POST ----------------------------------------------------------------
    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._read_body_json()
        if body is None:
            self._json_response(400, {"error": "Invalid JSON body"})
            return

        # /chat — main AI endpoint
        if path == "/chat":
            message = (body.get("message") or "").strip()
            if not message:
                self._json_response(400, {"error": "message is required"})
                return

            cfg = _load_config()
            api_key = cfg.get("api_key", "")
            if not api_key:
                self._json_response(200, {
                    "reply": (
                        "\u26a0\ufe0f **No API key configured.**\n\n"
                        "Please enter your OpenRouter API key using the \u2699\ufe0f **Settings** button above.\n\n"
                        "Get a free key at [openrouter.ai](https://openrouter.ai) \u2014 it takes under a minute."
                    ),
                    "executed": False,
                    "exec_summary": "",
                })
                return

            model = (body.get("model") or "").strip() or cfg.get("model", _DEFAULT_CONFIG["model"])
            reply, err = _call_openrouter(message, api_key, model)

            if err:
                self._json_response(200, {
                    "reply": (
                        f"\u274c **API Error:**\n```\n{err}\n```\n\n"
                        "Check your API key in \u2699\ufe0f Settings."
                    ),
                    "executed": False,
                    "exec_summary": "",
                })
                return

            # Extract and execute any blueprint commands embedded in the reply
            exec_summary = ""
            data = _extract_json_commands(reply)
            if data and isinstance(data.get("commands"), list):
                cmds = data["commands"]

                def _do_execute():
                    return _execute_commands(cmds)

                result = _run_on_main_thread(_do_execute, timeout=30)
                exec_summary = result.get("result", "") if result.get("ok") else (
                    f"\u26a0\ufe0f Execution error: {result.get('error', 'unknown')}"
                )

            self._json_response(200, {
                "reply": reply,
                "exec_summary": exec_summary,
                "executed": bool(exec_summary),
            })

        # /config — update API key / model
        elif path == "/config":
            cfg = _load_config()
            if "api_key" in body:
                cfg["api_key"] = str(body["api_key"]).strip()
            if "model" in body:
                cfg["model"] = str(body["model"]).strip()
            _save_config(cfg)
            self._json_response(200, {"ok": True, "model": cfg["model"]})

        # /history/clear
        elif path == "/history/clear":
            with _history_lock:
                _conversation_history.clear()
            self._json_response(200, {"ok": True})

        # /unreal/execute — legacy direct execution
        elif path == "/unreal/execute":
            commands = body.get("commands", [])
            if not isinstance(commands, list):
                self._json_response(400, {"error": "commands must be a list"})
                return

            def _do():
                return _execute_commands(commands)

            result = _run_on_main_thread(_do, timeout=30)
            if result.get("ok"):
                self._json_response(200, {"ok": True, "result": result.get("result", "")})
            else:
                self._json_response(500, {"ok": False, "error": result.get("error", "unknown")})

        else:
            self._json_response(404, {"error": "Not found"})


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

_server_thread = None
_server_instance = None
_tick_handle = None


def start(port=8080):
    """Start the HTTP server and register the game-thread tick callback."""
    global _server_thread, _server_instance, _tick_handle

    if _server_thread and _server_thread.is_alive():
        print(f"[MCPBlueprint] Server already running on port {port}")
        return

    try:
        _server_instance = HTTPServer(("0.0.0.0", port), _Handler)
    except OSError as e:
        print(f"[MCPBlueprint] Could not bind to port {port}: {e}")
        return

    _server_thread = threading.Thread(
        target=_server_instance.serve_forever,
        daemon=True,
        name="MCPBlueprintHTTPServer",
    )
    _server_thread.start()

    # Register the per-frame tick so Blueprint commands run on the game thread
    try:
        import unreal
        _tick_handle = unreal.register_slate_post_tick_callback(_tick)
    except ImportError:
        pass  # running outside Unreal — that's fine

    print(f"[MCPBlueprint] Server started \u2192 http://localhost:{port}/chat")


def stop():
    """Shut down the HTTP server and unregister the tick callback."""
    global _server_instance, _server_thread, _tick_handle
    if _server_instance:
        _server_instance.shutdown()
        _server_instance = None
    if _tick_handle:
        try:
            import unreal
            unreal.unregister_slate_post_tick_callback(_tick_handle)
        except Exception:
            pass
        _tick_handle = None
    _server_thread = None
    print("[MCPBlueprint] Server stopped.")
