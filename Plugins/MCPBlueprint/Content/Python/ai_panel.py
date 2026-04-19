"""
ai_panel.py
Self-contained AI Blueprint generator that runs INSIDE Unreal Engine.

Uses OpenRouter — one API key gives access to Claude, Gemini, DeepSeek, and GPT-4o.

Usage (in Unreal's Python console / Output Log):
  import ai_panel

  # One-time setup — saves key and model to disk
  ai_panel.set_key("sk-or-v1-your-openrouter-key")
  ai_panel.set_model("anthropic/claude-sonnet-4.5")   # optional, see MODELS below

  # Generate a Blueprint any time
  ai_panel.run("Create an enemy that chases the player")
  ai_panel.run("Create a door that opens when the player walks near it")
  ai_panel.run("Create a health pickup that gives 25 health on overlap")

  # List available models
  ai_panel.list_models()

  # Check current settings
  ai_panel.status()
"""

import json
import threading
import traceback
import urllib.request
import urllib.error
import os

import blueprint_executor

try:
    import unreal
    UNREAL = True
except ImportError:
    UNREAL = False

# ─────────────────────────────────────────────────────────────────────────────
# Available models (all verified live on OpenRouter as of 2025)
# ─────────────────────────────────────────────────────────────────────────────

MODELS = {
    # ── Claude ──────────────────────────────────────────────────────────────
    "claude-sonnet-4.5":        "anthropic/claude-sonnet-4.5",
    "claude-sonnet-4":          "anthropic/claude-sonnet-4",
    "claude-opus-4.5":          "anthropic/claude-opus-4.5",
    "claude-opus-4":            "anthropic/claude-opus-4",
    "claude-3.7-sonnet":        "anthropic/claude-3.7-sonnet",
    "claude-3.7-sonnet-think":  "anthropic/claude-3.7-sonnet:thinking",
    "claude-3.5-haiku":         "anthropic/claude-3.5-haiku",
    "claude-haiku-4.5":         "anthropic/claude-haiku-4.5",

    # ── Gemini ───────────────────────────────────────────────────────────────
    "gemini-2.5-pro":           "google/gemini-2.5-pro",
    "gemini-2.5-flash":         "google/gemini-2.5-flash",
    "gemini-2.5-flash-lite":    "google/gemini-2.5-flash-lite",
    "gemini-2.0-flash":         "google/gemini-2.0-flash-001",
    "gemini-2.0-flash-lite":    "google/gemini-2.0-flash-lite-001",
    "gemini-3-flash":           "google/gemini-3-flash-preview",
    "gemini-3.1-pro":           "google/gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite":    "google/gemini-3.1-flash-lite-preview",

    # ── DeepSeek ─────────────────────────────────────────────────────────────
    "deepseek-v3.2":            "deepseek/deepseek-v3.2",
    "deepseek-v3.2-speciale":   "deepseek/deepseek-v3.2-speciale",
    "deepseek-v3.1":            "deepseek/deepseek-chat-v3.1",
    "deepseek-r1":              "deepseek/deepseek-r1",
    "deepseek-r1-0528":         "deepseek/deepseek-r1-0528",
    "deepseek-r1-llama-70b":    "deepseek/deepseek-r1-distill-llama-70b",
    "deepseek-r1-chimera":      "tngtech/deepseek-r1t2-chimera",

    # ── GPT-4o ───────────────────────────────────────────────────────────────
    "gpt-4o":                   "openai/gpt-4o",
    "gpt-4o-mini":              "openai/gpt-4o-mini",
}

# Default model
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"

# ─────────────────────────────────────────────────────────────────────────────
# Config persistence
# ─────────────────────────────────────────────────────────────────────────────

_CFG_PATH = os.path.join(os.path.dirname(__file__), ".mcp_config")

def _load_cfg() -> dict:
    try:
        if os.path.exists(_CFG_PATH):
            with open(_CFG_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_cfg(data: dict):
    try:
        with open(_CFG_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        _log(f"Warning: could not save config: {e}")

def _get(key, default=""):
    return _load_cfg().get(key, default)

def _set(key, value):
    cfg = _load_cfg()
    cfg[key] = value
    _save_cfg(cfg)

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

def _log(msg: str):
    if UNREAL:
        unreal.log(f"[MCPBlueprint] {msg}")
    else:
        print(f"[MCPBlueprint] {msg}")

# ─────────────────────────────────────────────────────────────────────────────
# System prompt
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are an Unreal Engine 5 Blueprint generation assistant.
The user describes game logic in plain English.
You must respond with ONLY a valid JSON object — no explanation, no markdown, no code fences.

The JSON must follow this exact structure:
{
  "blueprint_name": "BP_SomeName",
  "commands": [
    {"action": "create_blueprint", "name": "BP_SomeName", "parent_class": "Actor"},
    {"action": "add_variable", "blueprint": "BP_SomeName", "variable_name": "Health", "variable_type": "Float", "default_value": 100},
    {"action": "add_node", "blueprint": "BP_SomeName", "node": "Event BeginPlay", "id": "node_0", "x": 0, "y": 0},
    {"action": "add_node", "blueprint": "BP_SomeName", "node": "Print String", "id": "node_1", "x": 300, "y": 0, "parameters": {"string": "Hello!"}},
    {"action": "connect_nodes", "blueprint": "BP_SomeName", "from_node": "node_0", "from_pin": "Then", "to_node": "node_1", "to_pin": "Execute"},
    {"action": "compile_blueprint", "name": "BP_SomeName"}
  ]
}

Rules:
- blueprint_name must start with BP_ and use PascalCase
- parent_class choices: Actor, Character, Pawn, GameModeBase, PlayerController, ActorComponent
- variable_type choices: Boolean, Integer, Float, String, Vector, Rotator, Transform
- node choices: Event BeginPlay, Event Tick, Event ActorBeginOverlap, Branch, Print String, Delay, Get Player Pawn, Get Actor Location, Set Actor Location, Destroy Actor, AI Move To, Timeline, Cast To Character
- Every add_node must have a unique "id" string
- connect_nodes uses those id strings
- compile_blueprint must always be the last command
- Respond with ONLY the JSON — nothing else
""".strip()

# ─────────────────────────────────────────────────────────────────────────────
# OpenRouter API call
# ─────────────────────────────────────────────────────────────────────────────

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def _call_openrouter(api_key: str, model_id: str, prompt: str) -> dict:
    """Call OpenRouter and return parsed JSON Blueprint commands dict."""
    payload = json.dumps({
        "model": model_id,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ]
    }).encode("utf-8")

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=payload,
        headers={
            "Authorization":  f"Bearer {api_key}",
            "Content-Type":   "application/json",
            "HTTP-Referer":   "https://github.com/mkbrown261/unreal-assistant",
            "X-Title":        "MCP Blueprint Generator",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter HTTP {e.code}: {body}")

    content = data["choices"][0]["message"]["content"].strip()

    # Strip markdown fences if the model wrapped the JSON anyway
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        content = "\n".join(lines).strip()

    return json.loads(content)

# ─────────────────────────────────────────────────────────────────────────────
# Core generate function
# ─────────────────────────────────────────────────────────────────────────────

def generate_blueprint(prompt: str, api_key: str, model_id: str):
    """Call OpenRouter, parse response, execute Blueprint commands on game thread."""
    if not api_key.strip():
        _log("ERROR: No API key set. Run: ai_panel.set_key('sk-or-v1-...')")
        return
    if not prompt.strip():
        _log("ERROR: Prompt is empty.")
        return

    _log(f'Prompt: "{prompt}"')
    _log(f"Model:  {model_id}")

    def _worker():
        try:
            _log("Calling OpenRouter...")
            result = _call_openrouter(api_key.strip(), model_id, prompt.strip())
            commands = result.get("commands", [])
            bp_name  = result.get("blueprint_name", "BP_Generated")
            _log(f"AI returned {len(commands)} commands → {bp_name}")

            if not commands:
                _log("ERROR: AI returned no commands. Try rephrasing your prompt.")
                return

            def _execute():
                try:
                    batch = blueprint_executor.execute_batch(commands)
                    if batch.get("success"):
                        _log(f"SUCCESS — {bp_name} created ({batch['succeeded']}/{batch['total']} commands)")
                        _log(f"Find it in Content Browser → /Game/MCP/{bp_name}")
                        if UNREAL:
                            try:
                                unreal.EditorAssetLibrary.sync_browser_to_objects([f"/Game/MCP/{bp_name}"])
                            except Exception:
                                pass
                    else:
                        _log(f"PARTIAL — {batch['succeeded']} ok, {batch['failed']} failed")
                        for r in batch.get("results", []):
                            if not r.get("success"):
                                _log(f"  FAIL: {r.get('message','?')}")
                except Exception:
                    _log(f"ERROR during execution:\n{traceback.format_exc()}")

            if UNREAL:
                try:
                    unreal.call_on_game_thread(_execute)
                except AttributeError:
                    _execute()
            else:
                _execute()

        except json.JSONDecodeError as e:
            _log(f"ERROR: AI response was not valid JSON: {e}")
            _log("Try a different model or rephrase your prompt.")
        except RuntimeError as e:
            _log(f"ERROR: {e}")
        except Exception:
            _log(f"ERROR:\n{traceback.format_exc()}")

    t = threading.Thread(target=_worker, daemon=True, name="MCPBlueprint_Generate")
    t.start()

# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def set_key(key: str):
    """
    Save your OpenRouter API key. Only needed once.
    ai_panel.set_key("sk-or-v1-...")
    """
    _set("api_key", key.strip())
    _log(f"API key saved (ends in ...{key.strip()[-8:]})")
    _log("Ready! Now run: ai_panel.run('your prompt here')")


def set_model(model: str):
    """
    Set the AI model to use. Pass a short name or full OpenRouter model ID.

    Short names:
      claude-sonnet-4.5, claude-opus-4, claude-3.7-sonnet, claude-3.7-sonnet-think,
      claude-3.5-haiku, claude-haiku-4.5,
      gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite,
      gemini-2.0-flash, gemini-3-flash, gemini-3.1-pro,
      deepseek-v3.2, deepseek-v3.2-speciale, deepseek-r1, deepseek-r1-0528,
      deepseek-r1-chimera, gpt-4o, gpt-4o-mini

    Or pass the full ID e.g. "anthropic/claude-sonnet-4.5"

    Example:
      ai_panel.set_model("gemini-2.5-pro")
      ai_panel.set_model("deepseek-r1")
    """
    model_id = MODELS.get(model, model)  # resolve short name, else use as-is
    _set("model", model_id)
    _log(f"Model set to: {model_id}")


def run(prompt: str, model: str = ""):
    """
    Generate a Blueprint from a plain-English prompt.

    ai_panel.run("Create an enemy that chases the player")
    ai_panel.run("Create a door that opens on overlap", model="gemini-2.5-pro")
    """
    api_key  = _get("api_key")
    if not api_key:
        _log("ERROR: No API key found. Run: ai_panel.set_key('sk-or-v1-...')")
        return

    if model:
        model_id = MODELS.get(model, model)
    else:
        model_id = _get("model", DEFAULT_MODEL)

    generate_blueprint(prompt, api_key, model_id)


def list_models():
    """Print all available models with their short names."""
    _log("─── Available Models ───────────────────────────────")
    groups = [
        ("Claude",   [k for k in MODELS if k.startswith("claude")]),
        ("Gemini",   [k for k in MODELS if k.startswith("gemini")]),
        ("DeepSeek", [k for k in MODELS if k.startswith("deepseek")]),
        ("GPT-4o",   [k for k in MODELS if k.startswith("gpt")]),
    ]
    for group_name, keys in groups:
        _log(f"  {group_name}:")
        for k in keys:
            _log(f"    {k:<30}  →  {MODELS[k]}")
    _log("────────────────────────────────────────────────────")
    _log("Usage: ai_panel.set_model('claude-sonnet-4.5')")
    _log("       ai_panel.run('your prompt', model='gemini-2.5-pro')")


def status():
    """Show current API key and model settings."""
    key = _get("api_key")
    model = _get("model", DEFAULT_MODEL)
    _log("─── MCP Blueprint Generator Status ─────────────────")
    _log(f"  API Key : {'...'+key[-8:] if key else 'NOT SET — run ai_panel.set_key()'}")
    _log(f"  Model   : {model}")
    _log(f"  Provider: OpenRouter (openrouter.ai)")
    _log("────────────────────────────────────────────────────")
    _log("Commands: ai_panel.run('prompt') | ai_panel.set_model('name') | ai_panel.list_models()")


def start():
    """Called automatically by init_unreal.py when the plugin loads."""
    key   = _get("api_key")
    model = _get("model", DEFAULT_MODEL)

    _log("MCP Blueprint Generator v1.1.0 — powered by OpenRouter")
    _log(f"Model   : {model}")

    if key:
        _log(f"API Key : ...{key[-8:]} (saved)")
        _log('Ready! Run: ai_panel.run("Create an enemy that chases the player")')
    else:
        _log("API Key : NOT SET")
        _log("Run this first: ai_panel.set_key('sk-or-v1-your-key-here')")

    _log("─────────────────────────────────────────────────────────────────────")
    _log("ai_panel.list_models()   — see all available models")
    _log("ai_panel.set_model('gemini-2.5-pro')   — switch models")
    _log("ai_panel.status()        — check current settings")
    _log("─────────────────────────────────────────────────────────────────────")
