"""
MCP Blueprint Server v2.0.0
Persistent HTTP server running inside Unreal Engine (port 8080).

Endpoints:
  GET  /                — redirect to /chat
  GET  /chat            — serve the chat UI HTML
  POST /chat            — receive user message, call OpenRouter, execute blueprints, return reply
  GET  /config          — return current config (key masked)
  POST /config          — update API key / model
  GET  /history         — return conversation history
  POST /history/clear   — wipe conversation history
  GET  /unreal/status   — health check (legacy)
  POST /unreal/execute  — direct command execution (legacy)
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

CHAT_SYSTEM_PROMPT = """You are an Unreal Engine 5 Blueprint assistant running INSIDE the Unreal Editor.

When the user asks you to create or modify a Blueprint:
1. Briefly explain what you're building (1-2 sentences).
2. Emit ONE ```json ... ``` block with all Blueprint commands.
3. After the JSON, summarize what was created and give exact wiring steps.

CRITICAL JSON FIELD RULES — follow exactly or Blueprint creation will fail:
- create_blueprint:  fields are "name", "parent_class", "path"
- compile_blueprint: field is "path" (full asset path: /Game/MCP/BP_Name)
- add_variable:      fields are "blueprint_path", "var_name", "var_type", "default_value"
- add_function:      fields are "blueprint_path", "function_name"

EXACT SCHEMA (copy this pattern every time):
```json
{
  "commands": [
    {"action": "create_blueprint", "name": "BP_Enemy", "parent_class": "Character", "path": "/Game/MCP"},
    {"action": "compile_blueprint", "path": "/Game/MCP/BP_Enemy"},
    {"action": "add_variable", "blueprint_path": "/Game/MCP/BP_Enemy", "var_name": "Health", "var_type": "float", "default_value": "100.0"},
    {"action": "add_variable", "blueprint_path": "/Game/MCP/BP_Enemy", "var_name": "MoveSpeed", "var_type": "float", "default_value": "300.0"},
    {"action": "add_function", "blueprint_path": "/Game/MCP/BP_Enemy", "function_name": "TakeDamage_Custom"},
    {"action": "compile_blueprint", "path": "/Game/MCP/BP_Enemy"}
  ]
}
```

RULES:
- ALWAYS compile_blueprint immediately after create_blueprint (before adding variables).
- ALWAYS compile_blueprint again as the final command.
- "path" for create_blueprint is the FOLDER: /Game/MCP
- "path" for compile_blueprint is the FULL ASSET PATH: /Game/MCP/BP_Name
- "blueprint_path" for add_variable and add_function is the FULL ASSET PATH: /Game/MCP/BP_Name
- Never mix up "path" and "blueprint_path" — wrong field = Blueprint not found.
- All blueprints go in /Game/MCP/ unless user specifies otherwise.

Supported parent classes: Actor, Character, Pawn, GameModeBase, PlayerController,
  ActorComponent, SceneComponent, GameInstance, GameState, PlayerState, HUD,
  UserWidget, AnimInstance, BlueprintFunctionLibrary

Supported var_type values: bool, int, float, string, vector, rotator, transform

After the JSON block, give wiring instructions like this:

📋 HOW TO WIRE THIS BLUEPRINT:
1. Open /Game/MCP/BP_Name in Content Browser (double-click)
2. In EventGraph: right-click → search “Event BeginPlay” → add it
3. Drag from BeginPlay exec pin → search “Print String” → connect
(use exact Unreal node names so the user can find them by searching)

NEVER tell the user to check the Output Log. All results appear in this chat.
Respond conversationally and clearly."""

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


def _execute_commands(commands):
    """Execute blueprint command list. Returns a human-readable summary."""
    try:
        import blueprint_executor  # available inside Unreal
        results = []
        for cmd in commands:
            action = cmd.get("action", "unknown")
            try:
                r = blueprint_executor.execute_command(cmd)
                results.append(f"  \u2705 {action}: {r}")
            except Exception as exc:
                results.append(f"  \u274c {action}: {exc}")
                # Log to UE output log as well for debugging
                try:
                    import unreal
                    unreal.log_error(f"[MCPBlueprint] {action} failed: {exc}")
                except Exception:
                    pass
        return "\n".join(results) if results else "No commands executed."
    except ImportError:
        return "(blueprint_executor unavailable \u2014 running outside Unreal)"
    except Exception as exc:
        return f"\u274c Executor error: {exc}"


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
            self._json_response(200, {"status": "ok", "version": "2.0.0"})

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
