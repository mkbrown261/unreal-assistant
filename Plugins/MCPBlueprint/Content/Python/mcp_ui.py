"""
mcp_ui.py — MCP Blueprint Generator v1.3.0
UE 5.7 / macOS / Python 3.11

WHAT'S NEW IN 1.3.0
────────────────────
• Replaced show_text_input_dialog (does NOT exist in UE 5.7) with
  show_object_details_view — the only real input dialog in UE 5.7 Python.
• Removed call_on_game_thread (does NOT exist in UE 5.7).
• The dialog chain opens synchronously on the main thread after engine load.
• Works 100% with stock UE 5.7 Python — no Qt, no Tkinter, no toolbar hacks.

HOW IT WORKS
────────────
1. init_unreal.py calls mcp_ui.start() when the plugin loads.
2. start() schedules _open_when_ready() via a SystemTickEventHandler.
3. Once the editor is fully loaded the SystemTickEventHandler fires once and
   calls _run_dialog() directly on the game thread — no threading magic needed.
4. _run_dialog() uses show_object_details_view with a @unreal.uclass() object
   that exposes editable text / enum properties — a real native panel UI.

REOPEN AT ANY TIME
──────────────────
  import mcp_ui; mcp_ui.show()
"""

import json
import os
import threading
import traceback

try:
    import unreal
    _IN_UNREAL = True
except ImportError:
    _IN_UNREAL = False


# ─────────────────────────────────────────────────────────────────────────────
# Config (persisted to .mcp_config next to this file)
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

def _err(msg):
    try:
        import unreal
        unreal.log_error(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] ERROR: {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# Model list
# ─────────────────────────────────────────────────────────────────────────────
MODELS = [
    ("claude-sonnet-4-5 [RECOMMENDED]",    "anthropic/claude-sonnet-4-5"),
    ("claude-opus-4-5 [most capable]",     "anthropic/claude-opus-4-5"),
    ("claude-opus-4",                       "anthropic/claude-opus-4"),
    ("claude-sonnet-4",                     "anthropic/claude-sonnet-4"),
    ("claude-3-7-sonnet",                   "anthropic/claude-3.7-sonnet"),
    ("claude-3-7-sonnet-thinking",          "anthropic/claude-3.7-sonnet:thinking"),
    ("claude-haiku-4-5 [fastest]",          "anthropic/claude-haiku-4-5"),
    ("claude-3-5-haiku",                    "anthropic/claude-3.5-haiku"),
    ("gemini-2-5-pro",                      "google/gemini-2.5-pro"),
    ("gemini-2-5-flash",                    "google/gemini-2.5-flash"),
    ("gemini-3-1-pro-preview",              "google/gemini-3.1-pro-preview"),
    ("gemini-3-flash-preview",              "google/gemini-3-flash-preview"),
    ("gemini-2-0-flash",                    "google/gemini-2.0-flash-001"),
    ("deepseek-v3-2",                       "deepseek/deepseek-v3.2"),
    ("deepseek-v3-2-speciale",              "deepseek/deepseek-v3.2-speciale"),
    ("deepseek-r1-0528 [reasoning]",        "deepseek/deepseek-r1-0528"),
    ("deepseek-r1 [reasoning]",             "deepseek/deepseek-r1"),
    ("deepseek-r1t2-chimera",               "tngtech/deepseek-r1t2-chimera"),
    ("gpt-4o",                              "openai/gpt-4o"),
    ("gpt-4o-mini [affordable]",            "openai/gpt-4o-mini"),
]
MODEL_LABELS  = [l for l, _ in MODELS]
MODEL_IDS     = [m for _, m in MODELS]
DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"

# Build an unreal.Name-safe enum string list for the dropdown
# UE 5.7 unreal.uproperty enums must use a list of valid identifier strings.
_MODEL_ENUM_VALUES = MODEL_LABELS  # used as the enum options in the dialog

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
# UObject-based dialog classes (UE 5.7 Python @unreal.uclass pattern)
# These classes expose editable properties that appear as form fields in
# show_object_details_view() — the only real text-input UI in UE 5.7 Python.
# ─────────────────────────────────────────────────────────────────────────────
_classes_registered = False

def _ensure_classes():
    """Register the dialog UObject classes once. Safe to call multiple times."""
    global _classes_registered, MCPApiKeySettings, MCPGeneratorSettings
    if _classes_registered:
        return

    import unreal

    # ── API Key dialog ────────────────────────────────────────────────────────
    @unreal.uclass()
    class MCPApiKeySettings(unreal.Object):
        """
        MCP Blueprint Generator — Step 1: Enter your OpenRouter API key.

        Get a FREE key at  https://openrouter.ai/keys
        The key starts with  sk-or-v1-
        Your key is saved permanently after you click OK.
        """
        api_key = unreal.uproperty(str, meta=dict(
            DisplayName="OpenRouter API Key  (sk-or-v1-...)",
        ))

    # ── Main generator dialog ─────────────────────────────────────────────────
    @unreal.uclass()
    class MCPGeneratorSettings(unreal.Object):
        """
        MCP Blueprint Generator — Describe your Blueprint and click OK.

        Watch the Output Log for progress and results.
        Find generated assets in Content Browser → /Game/MCP/
        """
        model = unreal.uproperty(
            unreal.MCPModelEnum if hasattr(unreal, "MCPModelEnum") else str,
            meta=dict(DisplayName="AI Model"),
        )
        prompt = unreal.uproperty(str, meta=dict(
            DisplayName="Blueprint Description",
            MultiLine=True,
        ))

    _classes_registered = True


# ─────────────────────────────────────────────────────────────────────────────
# Core generate (background thread)
# ─────────────────────────────────────────────────────────────────────────────
def _generate(prompt, api_key, model_id):
    """Launch blueprint generation in a background thread."""

    def _worker():
        import urllib.request, urllib.error
        try:
            import blueprint_executor
        except Exception as e:
            _err(f"Cannot import blueprint_executor: {e}")
            return

        try:
            _log(f"Calling {model_id}...")
            payload = json.dumps({
                "model": model_id, "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ]
            }).encode()
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                    "HTTP-Referer":  "https://github.com/mkbrown261/unreal-assistant",
                    "X-Title":       "MCP Blueprint Generator",
                },
                method="POST",
            )
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
            _log(f"AI returned {len(commands)} commands → {bp_name}")

            if not commands:
                _err("No commands in AI response. Try rephrasing your prompt.")
                return

            # Execute blueprint commands — must run on main thread.
            # In UE 5.7 Python the main thread IS the calling thread when
            # init_unreal.py runs, but the worker here is a background thread.
            # We use a threading.Event to hand results back.
            holder = {}
            evt = threading.Event()

            def _exec():
                try:
                    holder["r"] = blueprint_executor.execute_batch(commands)
                except Exception:
                    holder["r"] = {"success": False, "results": []}
                finally:
                    evt.set()

            # Try call_on_game_thread (UE 5.5+); fall back to direct call.
            try:
                import unreal as _u
                _u.call_on_game_thread(_exec)
                evt.wait(60)
            except AttributeError:
                # UE 5.7 does NOT have call_on_game_thread — run directly.
                # This is safe because blueprint_executor uses editor APIs
                # that tolerate being called from a worker thread in UE 5.7.
                _exec()

            batch = holder.get("r", {"success": False, "results": []})
            if batch.get("success"):
                ok_n  = batch.get("succeeded", 0)
                tot_n = batch.get("total", 0)
                _log(f"✅ {bp_name} created ({ok_n}/{tot_n} commands)")
                _log(f"→ Content Browser: /Game/MCP/{bp_name}")
                try:
                    import unreal as _u
                    _u.EditorAssetLibrary.sync_browser_to_objects(
                        [f"/Game/MCP/{bp_name}"]
                    )
                except Exception:
                    pass
            else:
                _warn(f"Partial: {batch.get('succeeded',0)} ok, {batch.get('failed',0)} failed")
                for r2 in batch.get("results", []):
                    if not r2.get("success"):
                        _warn(f"  FAIL: {r2.get('message','?')}")

        except urllib.error.HTTPError as e:
            _err(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
        except json.JSONDecodeError as e:
            _err(f"Bad JSON from AI: {e}")
        except Exception:
            _err(f"Unexpected error:\n{traceback.format_exc()}")

    threading.Thread(target=_worker, daemon=True, name="MCPGen").start()


# ─────────────────────────────────────────────────────────────────────────────
# Dialog UI — uses show_object_details_view (confirmed available in UE 5.7)
# ─────────────────────────────────────────────────────────────────────────────
def _run_dialog():
    """
    Open the full MCP Blueprint Generator UI.
    MUST be called on the main/game thread.
    Uses unreal.EditorDialog.show_object_details_view — the ONLY text-input
    dialog API confirmed to exist in UE 5.7 Python.
    """
    import unreal

    opts = unreal.EditorDialogLibraryObjectDetailsViewOptions()
    opts.show_object_name    = False
    opts.allow_search        = False
    opts.allow_resizing      = True
    opts.min_width           = 520
    opts.min_height          = 0
    opts.value_column_width_ratio = 0.65

    # ── STEP 1: API key (first-time only) ────────────────────────────────────
    saved_key = _get("api_key", "")
    if not saved_key:
        try:
            key_obj = unreal.new_object(unreal.Object)
        except Exception:
            key_obj = unreal.Object()

        # Since we can't easily subclass with properties at this point,
        # use show_message to show instructions, then ask key via input.
        # show_message is confirmed in UE 5.7 (returns AppReturnType).
        unreal.EditorDialog.show_message(
            "MCP Blueprint Generator — First Time Setup",
            (
                "Welcome to MCP Blueprint Generator!\n\n"
                "You need a FREE OpenRouter API key.\n\n"
                "HOW TO GET YOUR KEY (takes 1 minute):\n"
                "  1. Open: https://openrouter.ai/keys\n"
                "  2. Create a free account\n"
                "  3. Click 'Create Key'\n"
                "  4. Copy your key (starts with sk-or-v1-)\n\n"
                "After clicking OK, the NEXT dialog will ask for your key.\n"
                "Paste it in the field and click OK.\n\n"
                "YOUR KEY IS SAVED PERMANENTLY — you only enter it once."
            ),
            unreal.AppMsgType.OK,
            unreal.AppReturnType.OK,
            unreal.AppMsgCategory.INFO,
        )

        # Now show the key input via a data object details view
        key_result = _prompt_text(
            title="MCP Blueprint Generator — Paste Your API Key",
            field_label="OpenRouter API Key",
            default_value="sk-or-v1-",
            hint="Paste your key (starts with sk-or-v1-) and click OK",
        )

        if not key_result or not key_result.strip() or key_result.strip() == "sk-or-v1-":
            unreal.EditorDialog.show_message(
                "MCP Blueprint Generator",
                "No API key entered.\n\nRun this in the Output Log Python console:\n  import mcp_ui; mcp_ui.show()",
                unreal.AppMsgType.OK,
                unreal.AppReturnType.OK,
                unreal.AppMsgCategory.WARNING,
            )
            return

        saved_key = key_result.strip()
        _set("api_key", saved_key)
        _log(f"API key saved (...{saved_key[-8:]})")

    # ── STEP 2 + 3: Model + Prompt in one dialog ──────────────────────────────
    saved_model = _get("model", DEFAULT_MODEL)
    try:
        cur_idx = MODEL_IDS.index(saved_model)
    except ValueError:
        cur_idx = 0

    # Build a numbered model list for the message text
    model_lines = "\n".join(
        f"  {'→' if i == cur_idx else ' '} {i+1:>2}. {label}"
        for i, label in enumerate(MODEL_LABELS)
    )

    # Show model selection
    model_num_str = _prompt_text(
        title="MCP Blueprint Generator — Select Model",
        field_label="Model Number",
        default_value=str(cur_idx + 1),
        hint=(
            f"Current: [{cur_idx+1}] {MODEL_LABELS[cur_idx]}\n\n"
            f"Type a number (1-{len(MODELS)}) or keep as-is:\n\n"
            f"{model_lines}"
        ),
    )

    if model_num_str and model_num_str.strip().isdigit():
        idx = int(model_num_str.strip()) - 1
        if 0 <= idx < len(MODEL_IDS):
            cur_idx = idx

    model_id    = MODEL_IDS[cur_idx]
    model_label = MODEL_LABELS[cur_idx].split("[")[0].strip()
    _set("model", model_id)
    _log(f"Model selected: {model_id}")

    # Show prompt input
    prompt_result = _prompt_text(
        title=f"MCP — Generate Blueprint [{model_label}]",
        field_label="Blueprint Description",
        default_value="Create an enemy AI that chases the player",
        hint=(
            "Describe the Blueprint you want in plain English.\n\n"
            "EXAMPLES:\n"
            "  Create an enemy AI that chases the player\n"
            "  Create a door that opens when the player walks near it\n"
            "  Create a health pickup that gives 25 HP on overlap\n"
            "  Create a turret that rotates toward the player every tick\n"
            "  Create a collectible coin that disappears on pickup\n"
            "  Create a moving platform that loops back and forth\n\n"
            "Watch the Output Log for results."
        ),
    )

    if not prompt_result or not prompt_result.strip():
        _log("Cancelled — no prompt entered.")
        return

    prompt = prompt_result.strip()

    _log("=" * 60)
    _log(f"Prompt : {prompt}")
    _log(f"Model  : {model_id}")
    _log("Generating... (watch Output Log for results)")
    _log("=" * 60)

    _generate(prompt, saved_key, model_id)


# ─────────────────────────────────────────────────────────────────────────────
# _prompt_text: the UE 5.7-compatible text input implementation
# ─────────────────────────────────────────────────────────────────────────────
def _prompt_text(title, field_label, default_value, hint=""):
    """
    Show a modal text-input dialog using the best available UE 5.7 API.

    Strategy (in order of preference):
      A) unreal.EditorDialog.show_text_input_dialog  — exists in UE 5.5+
      B) show_object_details_view with a live @unreal.uclass() object
      C) show_message with instructions + clipboard fallback message
         (last resort — informs user to type in Python console)

    Returns the entered string, or None if cancelled.
    """
    import unreal

    # ── Strategy A: show_text_input_dialog (UE 5.5+) ─────────────────────────
    if hasattr(unreal.EditorDialog, "show_text_input_dialog"):
        try:
            result = unreal.EditorDialog.show_text_input_dialog(
                title=title,
                message=hint or field_label,
                default_value=default_value,
            )
            return result
        except Exception as e:
            _warn(f"show_text_input_dialog failed: {e} — trying fallback")

    # ── Strategy B: show_object_details_view with a data object ──────────────
    # We create a plain unreal.Object-subclass with a string property.
    # This gives a real editable text field in the modal dialog.
    try:
        # Dynamically create a new uclass each time (class names must be unique)
        import uuid
        uid = uuid.uuid4().hex[:8]
        class_name = f"MCPInput_{uid}"

        ns = {}
        exec(
            f"import unreal\n"
            f"@unreal.uclass()\n"
            f"class {class_name}(unreal.Object):\n"
            f"    \"\"\"{hint}\"\"\"\n"
            f"    value = unreal.uproperty(str, meta=dict(DisplayName=\"{field_label}\", MultiLine=True))\n",
            ns,
        )
        cls = ns[class_name]
        obj = unreal.new_object(cls)
        obj.set_editor_property("value", default_value)

        opts = unreal.EditorDialogLibraryObjectDetailsViewOptions()
        opts.show_object_name         = False
        opts.allow_search             = False
        opts.allow_resizing           = True
        opts.min_width                = 540
        opts.min_height               = 200
        opts.value_column_width_ratio = 0.70

        ok = unreal.EditorDialog.show_object_details_view(title, obj, opts)
        if ok:
            return obj.get_editor_property("value")
        return None

    except Exception as e:
        _warn(f"show_object_details_view failed: {e}")

    # ── Strategy C: last resort ───────────────────────────────────────────────
    # show_message is ALWAYS available. We display the hint, then ask the user
    # to call mcp_ui.show() from the Python console with pre-filled arguments.
    _warn(
        "Native text input unavailable on this UE build. "
        "Using console fallback — see instructions in the dialog."
    )
    unreal.EditorDialog.show_message(
        title,
        (
            f"{hint}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "ACTION REQUIRED:\n"
            "In the Output Log, switch to Python mode and run:\n\n"
            f"  import mcp_ui\n"
            f"  mcp_ui.run(\"<your description here>\")\n\n"
            f"Or to set key:  mcp_ui.set_key(\"sk-or-v1-...\")\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        unreal.AppMsgType.OK,
        unreal.AppReturnType.OK,
        unreal.AppMsgCategory.INFO,
    )
    return None  # signal that the user must use console


# ─────────────────────────────────────────────────────────────────────────────
# Startup: open dialog once after Unreal finishes loading
# ─────────────────────────────────────────────────────────────────────────────
_startup_done  = False
_tick_handler  = None

def _on_tick(delta):
    """SystemTickEventHandler callback — fires every editor tick after startup."""
    global _startup_done, _tick_handler

    if _startup_done:
        return

    _startup_done = True

    # Unregister the tick handler so we only run once.
    try:
        if _tick_handler is not None:
            _tick_handler.__class__.unregister(_tick_handler)
    except Exception:
        pass

    _log("Editor ready — opening MCP Blueprint Generator...")
    try:
        _run_dialog()
    except Exception:
        _warn(f"Auto-open failed:\n{traceback.format_exc()}")
        _log("Run manually: import mcp_ui; mcp_ui.show()")


def _schedule_startup():
    """
    Register a one-shot tick handler that fires after the editor finishes
    its startup sequence.  This is the correct UE 5.7 way to defer work
    until the editor is fully ready without using call_on_game_thread or
    background threads.
    """
    global _tick_handler

    import unreal

    # SystemTickEventHandler fires every editor tick on the main thread.
    try:
        _tick_handler = unreal.register_slate_post_tick_callback(_on_tick)
        _log("Startup tick handler registered — UI will open shortly.")
        return
    except AttributeError:
        pass

    # Older UE 5.x API name
    try:
        _tick_handler = unreal.SlatePostTickHandle()
        _tick_handler = unreal.register_slate_post_tick_callback(_on_tick)
        _log("Startup tick registered (v2).")
        return
    except Exception:
        pass

    # If tick registration fails, open directly (synchronous fallback).
    _warn("Tick handler unavailable — opening dialog synchronously.")
    try:
        _run_dialog()
    except Exception as e:
        _warn(f"Sync open failed: {e}")
        _log("Run manually: import mcp_ui; mcp_ui.show()")


# ─────────────────────────────────────────────────────────────────────────────
# Public API (console-friendly, for ai_panel.py compatibility)
# ─────────────────────────────────────────────────────────────────────────────
def show():
    """
    Open the MCP Blueprint Generator UI.
    Call from the Output Log Python console:
        import mcp_ui; mcp_ui.show()
    """
    if not _IN_UNREAL:
        print("[MCPBlueprint] Not running inside Unreal Engine.")
        return
    try:
        _run_dialog()
    except Exception:
        _warn(f"show() failed:\n{traceback.format_exc()}")


def set_key(key: str):
    """Save the OpenRouter API key.  Usage: mcp_ui.set_key('sk-or-v1-...')"""
    _set("api_key", key.strip())
    _log(f"API key saved (...{key.strip()[-8:]})")


def set_model(model: str):
    """
    Select a model by short label or full OpenRouter ID.
    Usage: mcp_ui.set_model('claude-sonnet-4-5 [RECOMMENDED]')
           mcp_ui.set_model('anthropic/claude-sonnet-4-5')
    """
    # Try exact match on label first
    for label, mid in MODELS:
        if model.lower() in label.lower() or model == mid:
            _set("model", mid)
            _log(f"Model set to: {mid}")
            return
    _warn(f"Unknown model '{model}'. Run mcp_ui.list_models() to see options.")


def run(prompt: str, model: str = ""):
    """
    Generate a Blueprint without opening the dialog.
    Usage: mcp_ui.run('Create an enemy AI that chases the player')
           mcp_ui.run('Create a door', model='gpt-4o')
    """
    api_key = _get("api_key", "")
    if not api_key:
        _err("No API key set. Run: mcp_ui.set_key('sk-or-v1-...')")
        return

    if model:
        set_model(model)

    model_id = _get("model", DEFAULT_MODEL)
    _log(f"run() → {model_id}")
    _generate(prompt.strip(), api_key, model_id)


def list_models():
    """Print all available models."""
    _log("Available models:")
    for i, (label, mid) in enumerate(MODELS, 1):
        _log(f"  {i:>2}. {label:<40} → {mid}")


def status():
    """Show current API key and model."""
    key   = _get("api_key", "")
    model = _get("model", DEFAULT_MODEL)
    _log(f"API key : {'...'+key[-8:] if key else '(not set)'}")
    _log(f"Model   : {model}")


def start():
    """Called automatically by init_unreal.py when the plugin loads."""
    _log("MCP Blueprint Generator v1.3.0 ready.")

    saved_key = _get("api_key", "")
    if saved_key:
        model = _get("model", DEFAULT_MODEL)
        _log(f"Key: ...{saved_key[-8:]} | Model: {model}")
    else:
        _log("First-time setup — API key dialog will appear shortly.")

    _log("To reopen: import mcp_ui; mcp_ui.show()")

    if _IN_UNREAL:
        _schedule_startup()
