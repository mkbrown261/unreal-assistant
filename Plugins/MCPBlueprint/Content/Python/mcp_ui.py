"""
mcp_ui.py — MCP Blueprint Generator v1.2.0
UE 5.7 / macOS / Python 3.11

HOW IT WORKS:
  When Unreal finishes loading, this script fires a dialog using
  unreal.call_on_game_thread — which is the ONLY reliable UI method
  available in stock UE 5.7 Python on macOS.

  The dialog chain:
    1. First launch only: asks for your OpenRouter API key (saved forever)
    2. Model selection: numbered list of all 20 AI models — type a number
       or press OK to keep the current model
    3. Prompt: describe the Blueprint in plain English, press OK
    → Blueprint is created and appears in Content Browser / Game/MCP/

  Re-run at any time from the Output Log (Python mode):
    import mcp_ui; mcp_ui.show()
"""

import json
import os
import threading
import traceback

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
_CFG = os.path.join(os.path.dirname(__file__), ".mcp_config")

def _load():
    try:
        if os.path.exists(_CFG):
            with open(_CFG) as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save(d):
    try:
        with open(_CFG, "w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass

def _get(k, default=""):
    return _load().get(k, default)

def _set(k, v):
    d = _load(); d[k] = v; _save(d)


# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
def _log(msg):
    try:
        import unreal
        unreal.log(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] {msg}")

def _warn(msg):
    try:
        import unreal
        unreal.log_warning(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] WARN: {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────
MODELS = [
    ("Claude Sonnet 4.5  [RECOMMENDED]",  "anthropic/claude-sonnet-4.5"),
    ("Claude Opus 4.5   [most capable]",   "anthropic/claude-opus-4.5"),
    ("Claude Opus 4",                       "anthropic/claude-opus-4"),
    ("Claude Sonnet 4",                     "anthropic/claude-sonnet-4"),
    ("Claude 3.7 Sonnet",                   "anthropic/claude-3.7-sonnet"),
    ("Claude 3.7 Sonnet Thinking",          "anthropic/claude-3.7-sonnet:thinking"),
    ("Claude Haiku 4.5  [fastest]",         "anthropic/claude-haiku-4.5"),
    ("Claude 3.5 Haiku",                    "anthropic/claude-3.5-haiku"),
    ("Gemini 2.5 Pro",                      "google/gemini-2.5-pro"),
    ("Gemini 2.5 Flash",                    "google/gemini-2.5-flash"),
    ("Gemini 3.1 Pro Preview",              "google/gemini-3.1-pro-preview"),
    ("Gemini 3 Flash Preview",              "google/gemini-3-flash-preview"),
    ("Gemini 2.0 Flash",                    "google/gemini-2.0-flash-001"),
    ("DeepSeek V3.2",                       "deepseek/deepseek-v3.2"),
    ("DeepSeek V3.2 Speciale",              "deepseek/deepseek-v3.2-speciale"),
    ("DeepSeek R1 0528  [reasoning]",       "deepseek/deepseek-r1-0528"),
    ("DeepSeek R1  [reasoning]",            "deepseek/deepseek-r1"),
    ("DeepSeek R1T2 Chimera",               "tngtech/deepseek-r1t2-chimera"),
    ("GPT-4o",                              "openai/gpt-4o"),
    ("GPT-4o Mini  [most affordable]",      "openai/gpt-4o-mini"),
]
MODEL_LABELS  = [l for l, _ in MODELS]
MODEL_IDS     = [m for _, m in MODELS]
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"

SYSTEM_PROMPT = (
    "You are an Unreal Engine 5 Blueprint generation assistant. "
    "The user describes game logic in plain English. "
    "Respond with ONLY a valid JSON object — no explanation, no markdown.\n\n"
    '{"blueprint_name":"BP_Name","commands":['
    '{"action":"create_blueprint","name":"BP_Name","parent_class":"Actor"},'
    '{"action":"add_node","blueprint":"BP_Name","node":"Event BeginPlay","id":"n0","x":0,"y":0},'
    '{"action":"add_node","blueprint":"BP_Name","node":"Print String","id":"n1","x":300,"y":0},'
    '{"action":"connect_nodes","blueprint":"BP_Name","from_node":"n0","from_pin":"Then","to_node":"n1","to_pin":"Execute"},'
    '{"action":"compile_blueprint","name":"BP_Name"}]}\n\n'
    "Rules: BP_ prefix PascalCase. parent_class: Actor/Character/Pawn/GameModeBase/PlayerController. "
    "Nodes: Event BeginPlay, Event Tick, Event ActorBeginOverlap, Branch, Print String, "
    "Delay, Get Player Pawn, Get Actor Location, Set Actor Location, Destroy Actor, AI Move To. "
    "Unique node ids. compile_blueprint must be last. Return ONLY the JSON."
)


# ─────────────────────────────────────────────────────────────────────────────
# Core generate (background thread)
# ─────────────────────────────────────────────────────────────────────────────
def _generate(prompt, api_key, model_id, on_log=None, on_done=None):
    log = on_log or _log

    def _worker():
        import urllib.request, urllib.error
        import blueprint_executor
        try:
            log(f"Calling {model_id}...")
            payload = json.dumps({
                "model": model_id, "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ]
            }).encode()
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions", data=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                    "HTTP-Referer":  "https://github.com/mkbrown261/unreal-assistant",
                    "X-Title":       "MCP Blueprint Generator",
                }, method="POST")
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read().decode())
            content = data["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = "\n".join(
                    l for l in content.split("\n") if not l.startswith("```")
                ).strip()
            result   = json.loads(content)
            commands = result.get("commands", [])
            bp_name  = result.get("blueprint_name", "BP_Generated")
            log(f"AI returned {len(commands)} commands -> {bp_name}")
            if not commands:
                log("ERROR: No commands returned. Try rephrasing.")
                if on_done: on_done(False, "")
                return
            holder = {}; evt = threading.Event()
            def _exec():
                try:
                    holder["r"] = blueprint_executor.execute_batch(commands)
                except Exception:
                    holder["r"] = {"success": False, "results": []}
                finally:
                    evt.set()
            try:
                import unreal
                unreal.call_on_game_thread(_exec)
                evt.wait(30)
            except (ImportError, AttributeError):
                _exec()
            batch = holder.get("r", {"success": False, "results": []})
            if batch.get("success"):
                log(f"SUCCESS: {bp_name} created ({batch.get('succeeded',0)}/{batch.get('total',0)} commands)")
                log(f"Find it: Content Browser -> /Game/MCP/{bp_name}")
                try:
                    import unreal
                    unreal.EditorAssetLibrary.sync_browser_to_objects([f"/Game/MCP/{bp_name}"])
                except Exception:
                    pass
                if on_done: on_done(True, bp_name)
            else:
                log(f"PARTIAL: {batch.get('succeeded',0)} ok, {batch.get('failed',0)} failed")
                for r2 in batch.get("results", []):
                    if not r2.get("success"):
                        log(f"  FAIL: {r2.get('message','?')}")
                if on_done: on_done(False, bp_name)
        except urllib.error.HTTPError as e:
            log(f"HTTP ERROR {e.code}: {e.read().decode(errors='replace')[:300]}")
            if on_done: on_done(False, "")
        except json.JSONDecodeError as e:
            log(f"Bad JSON from AI: {e}")
            if on_done: on_done(False, "")
        except Exception:
            log(f"ERROR: {traceback.format_exc()}")
            if on_done: on_done(False, "")

    threading.Thread(target=_worker, daemon=True, name="MCPGen").start()


# ─────────────────────────────────────────────────────────────────────────────
# The actual UI — Unreal EditorDialog chain
# This is called ON the game thread so dialogs appear properly on macOS
# ─────────────────────────────────────────────────────────────────────────────
def _run_dialog():
    """
    The complete MCP Blueprint Generator UI.
    Must be called on the game thread (via unreal.call_on_game_thread).

    Flow:
      Step 1 — API key (only shown if not already saved)
      Step 2 — Model selection (numbered list, switchable every run)
      Step 3 — Prompt input
      → Generate blueprint in background thread
    """
    import unreal

    # ── STEP 1: API KEY (first-time only) ────────────────────────────────────
    saved_key = _get("api_key", "")
    if not saved_key:
        key_result = unreal.EditorDialog.show_text_input_dialog(
            title="MCP Blueprint Generator — Welcome! Enter API Key",
            message=(
                "Welcome to MCP Blueprint Generator!\n\n"
                "You need a FREE OpenRouter API key to use AI models.\n\n"
                "HOW TO GET YOUR FREE KEY:\n"
                "  1. Open your browser and go to:  openrouter.ai/keys\n"
                "  2. Create a free account\n"
                "  3. Click 'Create Key'\n"
                "  4. Copy the key  (it starts with sk-or-v1-)\n"
                "  5. Paste it below and press OK\n\n"
                "Your key is saved permanently — you never enter it again."
            ),
            default_value="",
        )
        if not key_result or not key_result.strip():
            unreal.EditorDialog.show_message(
                "MCP Blueprint Generator",
                "No API key entered.\n\nRun  import mcp_ui; mcp_ui.show()  to try again.",
                unreal.AppMsgType.OK,
            )
            return
        saved_key = key_result.strip()
        _set("api_key", saved_key)
        _log(f"API key saved (...{saved_key[-8:]})")

    # ── STEP 2: MODEL SELECTION ───────────────────────────────────────────────
    saved_model = _get("model", DEFAULT_MODEL)
    try:
        cur_idx = MODEL_IDS.index(saved_model)
    except ValueError:
        cur_idx = 0

    # Build the model list string — clear numbered menu
    model_lines = "\n".join(
        f"  {i+1:>2}.  {label}" for i, label in enumerate(MODEL_LABELS)
    )

    model_result = unreal.EditorDialog.show_text_input_dialog(
        title="MCP Blueprint Generator — Choose AI Model",
        message=(
            f"Current model: [{cur_idx + 1}] {MODEL_LABELS[cur_idx]}\n\n"
            f"Type a NUMBER to switch models, or press OK to keep the current one:\n\n"
            f"{model_lines}\n\n"
            f"(Press OK without changing to keep [{cur_idx + 1}])"
        ),
        default_value=str(cur_idx + 1),
    )

    # Parse the selection
    if model_result and model_result.strip().isdigit():
        idx = int(model_result.strip()) - 1
        if 0 <= idx < len(MODEL_IDS):
            cur_idx = idx

    model_id    = MODEL_IDS[cur_idx]
    model_label = MODEL_LABELS[cur_idx].strip()
    _set("model", model_id)

    # ── STEP 3: PROMPT ───────────────────────────────────────────────────────
    prompt_result = unreal.EditorDialog.show_text_input_dialog(
        title=f"MCP Blueprint Generator — [{model_label}]",
        message=(
            "Describe the Blueprint you want in plain English.\n\n"
            "EXAMPLES (you can copy one of these):\n\n"
            "  Create an enemy AI that chases the player\n"
            "  Create a door that opens when the player walks near it\n"
            "  Create a health pickup that gives 25 HP on overlap\n"
            "  Create a turret that rotates toward the player every tick\n"
            "  Create a game timer that ends the match after 60 seconds\n"
            "  Create a moving platform that loops back and forth\n"
            "  Create a checkpoint that saves the player position\n"
            "  Create a collectible coin that disappears on pickup\n\n"
            "Watch the Output Log for results after clicking OK."
        ),
        default_value="Create an enemy AI that chases the player",
    )

    if not prompt_result or not prompt_result.strip():
        _log("Cancelled — no prompt entered.")
        return

    prompt = prompt_result.strip()

    # ── GENERATE ─────────────────────────────────────────────────────────────
    _log("=" * 60)
    _log(f"Prompt : {prompt}")
    _log(f"Model  : {model_id}")
    _log("Generating... watch the Output Log below for results.")
    _log("=" * 60)

    _generate(prompt, saved_key, model_id)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def show():
    """
    Open the MCP Blueprint Generator dialog.
    Call this from the Python console at any time:
        import mcp_ui; mcp_ui.show()
    """
    try:
        import unreal
        unreal.call_on_game_thread(_run_dialog)
    except ImportError:
        _log("Not running inside Unreal Engine.")
    except Exception as e:
        _warn(f"show() failed: {e}")
        # Direct fallback if call_on_game_thread not available
        _run_dialog()


def start():
    """Called automatically by init_unreal.py when the plugin loads."""
    _log("MCP Blueprint Generator v1.2.0 ready.")

    saved_key = _get("api_key", "")
    if saved_key:
        model = _get("model", DEFAULT_MODEL)
        _log(f"API key: ...{saved_key[-8:]} | Model: {model}")
        _log("Opening generator...")
    else:
        _log("First time setup — opening API key dialog...")

    # Fire the dialog on the game thread after a short delay
    # so Unreal finishes its startup sequence first
    def _delayed_open():
        import time
        time.sleep(2.0)  # wait for editor to fully finish loading
        try:
            import unreal
            unreal.call_on_game_thread(_run_dialog)
        except Exception as e:
            _warn(f"Auto-open failed: {e}")
            # Last resort: try directly
            try:
                _run_dialog()
            except Exception:
                pass

    threading.Thread(target=_delayed_open, daemon=True, name="MCPStartup").start()
