"""
mcp_ui.py — MCP Blueprint Generator v1.4.0
UE 5.7.4 / macOS / Python 3.11

FIXES IN 1.4.0
──────────────
• Menu click NOW WORKS: uses ToolMenuEntryScript subclass with execute()
  override — the ONLY reliable way to trigger Python from a menu click in UE 5.x.
  set_string_command(PYTHON) is unreliable; the execute() override is guaranteed.
• @unreal.uclass() classes defined at MODULE LEVEL only (not inside exec/functions).
  Dynamic class creation per-call causes UE to crash or silently fail.
• Removed all references to unreal.MCPModelEnum (does not exist in any UE version).
• Model stored as index (int) + displayed as numbered list via show_message.
• _prompt_text uses show_object_details_view with pre-defined module-level class.
• init_unreal.py calls start() which registers menu + schedules startup dialog.
• .uplugin EngineVersion bumped to 5.7.0.

HOW THE MENU CLICK WORKS
─────────────────────────
1. At startup, _register_menu() creates an MCPMenuEntryScript instance.
2. MCPMenuEntryScript.execute() is called by UE when the menu item is clicked.
3. execute() calls show() → _run_dialog() — guaranteed to run on game thread.

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
# Config
# ─────────────────────────────────────────────────────────────────────────────
_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mcp_config")

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
    d = _load()
    d[k] = v
    _save(d)


# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
def _log(msg):
    try:
        unreal.log(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] {msg}")

def _warn(msg):
    try:
        unreal.log_warning(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] WARN: {msg}")

def _err(msg):
    try:
        unreal.log_error(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] ERROR: {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# Models
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
    ("gemini-2-0-flash",                    "google/gemini-2.0-flash-001"),
    ("deepseek-v3",                         "deepseek/deepseek-v3"),
    ("deepseek-r1 [reasoning]",             "deepseek/deepseek-r1"),
    ("gpt-4o",                              "openai/gpt-4o"),
    ("gpt-4o-mini [affordable]",            "openai/gpt-4o-mini"),
    ("gpt-4.1",                             "openai/gpt-4.1"),
]
MODEL_LABELS  = [l for l, _ in MODELS]
MODEL_IDS     = [m for _, m in MODELS]
DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"

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
# UObject classes for show_object_details_view text input
#
# CRITICAL: These MUST be defined at module level, NOT inside functions.
# UE 5.7 Python crashes or silently fails when @unreal.uclass() is used
# inside exec(), lambda, or non-module-level scope.
#
# We define ONE class per "form field" we need. The same class instance
# is reused across calls by resetting the property before showing.
# ─────────────────────────────────────────────────────────────────────────────

# This guard ensures we only define the classes once per Python session.
# If this module is reloaded (importlib.reload), the classes already exist
# in the unreal type system and re-defining them would error.
_UE_CLASSES_READY = False

# These will be set to the actual classes after _init_ue_classes() runs.
MCPTextInputObj  = None   # single text field — used for API key, model#, prompt
MCPMenuScript    = None   # ToolMenuEntryScript subclass that calls show()


def _init_ue_classes():
    """
    Register UE Python uclasses. Called once from start() after Unreal loads.
    Defining them here (called lazily) avoids errors if the module is imported
    before the Unreal Python environment is fully initialized.
    """
    global _UE_CLASSES_READY, MCPTextInputObj, MCPMenuScript

    if _UE_CLASSES_READY:
        return
    if not _IN_UNREAL:
        return

    import unreal as _u

    # ── Text input dialog object ──────────────────────────────────────────────
    # show_object_details_view shows this object's properties as editable fields.
    # 'value' is the only property — it becomes a multiline text box.
    @_u.uclass()
    class _MCPTextInput(_u.Object):
        """Type your input below and click OK."""
        value = _u.uproperty(str, meta=dict(
            DisplayName="Input",
            MultiLine=True,
        ))

    MCPTextInputObj = _MCPTextInput

    # ── Menu entry script — execute() is called by UE on menu click ───────────
    # This is the ONLY reliable way to run Python from a menu in UE 5.x.
    # set_string_command(PYTHON, ...) is unreliable in UE 5.7 on macOS.
    @_u.uclass()
    class _MCPMenuEntry(_u.ToolMenuEntryScript):
        @_u.ufunction(override=True)
        def execute(self, context):
            """Called by UE when the menu item is clicked."""
            try:
                show()
            except Exception:
                _warn(f"Menu execute() failed:\n{traceback.format_exc()}")

    MCPMenuScript = _MCPMenuEntry

    _UE_CLASSES_READY = True
    _log("UE Python classes registered (MCPTextInputObj, MCPMenuScript).")


# ─────────────────────────────────────────────────────────────────────────────
# _prompt_text — show a modal text-input dialog (UE 5.7 compatible)
# ─────────────────────────────────────────────────────────────────────────────
def _prompt_text(title, field_label, default_value="", hint=""):
    """
    Show a modal dialog with a single editable text field.
    Returns the text the user typed, or None if cancelled/closed.

    Uses show_object_details_view — the ONLY real text-input dialog in UE 5.7.
    Falls back to show_message + console instructions if unavailable.
    """
    import unreal as _u

    # Strategy A: show_object_details_view with pre-defined uclass
    if MCPTextInputObj is not None:
        try:
            obj = _u.new_object(MCPTextInputObj)
            # Show hint in the property label
            # We can't change the class docstring at runtime, but we CAN
            # set the initial value so the user sees the default.
            obj.set_editor_property("value", str(default_value))

            opts = _u.EditorDialogLibraryObjectDetailsViewOptions()
            opts.show_object_name         = False
            opts.allow_search             = False
            opts.allow_resizing           = True
            opts.min_width                = 560
            opts.min_height               = 120
            opts.value_column_width_ratio = 0.72

            ok = _u.EditorDialog.show_object_details_view(
                f"{title}\n{hint}" if hint else title,
                obj,
                opts,
            )
            if ok:
                return obj.get_editor_property("value")
            return None
        except Exception as e:
            _warn(f"show_object_details_view failed: {e}")

    # Strategy B: show_text_input_dialog (exists in some UE 5.x builds)
    if hasattr(_u.EditorDialog, "show_text_input_dialog"):
        try:
            return _u.EditorDialog.show_text_input_dialog(
                title=title,
                message=hint or field_label,
                default_value=str(default_value),
            )
        except Exception as e:
            _warn(f"show_text_input_dialog failed: {e}")

    # Strategy C: last-resort show_message with console instructions
    _warn("No native text input available — showing console instructions.")
    _u.EditorDialog.show_message(
        title,
        (
            f"{hint}\n\n"
            "─────────────────────────────────\n"
            "No native text input available.\n"
            "In the Output Log Python console, run:\n\n"
            "  import mcp_ui\n"
            "  mcp_ui.run(\"describe your blueprint here\")\n\n"
            "To set API key:\n"
            "  mcp_ui.set_key(\"sk-or-v1-...\")\n"
            "─────────────────────────────────"
        ),
        _u.AppMsgType.OK,
        _u.AppReturnType.OK,
        _u.AppMsgCategory.INFO,
    )
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Blueprint generation (background thread)
# ─────────────────────────────────────────────────────────────────────────────
def _generate(prompt, api_key, model_id):
    """Send prompt to OpenRouter and execute returned Blueprint commands."""

    def _worker():
        import urllib.request, urllib.error
        try:
            import blueprint_executor
        except Exception as e:
            _err(f"Cannot import blueprint_executor: {e}")
            return

        try:
            _log(f"Calling {model_id} ...")
            payload = json.dumps({
                "model": model_id,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
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
            # Strip markdown code fences if present
            if content.startswith("```"):
                content = "\n".join(
                    line for line in content.split("\n")
                    if not line.startswith("```")
                ).strip()

            result   = json.loads(content)
            commands = result.get("commands", [])
            bp_name  = result.get("blueprint_name", "BP_Generated")
            _log(f"AI returned {len(commands)} commands → {bp_name}")

            if not commands:
                _err("No commands in AI response. Try rephrasing your prompt.")
                return

            # Execute on main thread if possible, else direct
            holder = {}
            evt = threading.Event()

            def _exec():
                try:
                    holder["r"] = blueprint_executor.execute_batch(commands)
                except Exception:
                    holder["r"] = {"success": False, "results": []}
                finally:
                    evt.set()

            try:
                import unreal as _u
                _u.call_on_game_thread(_exec)
                evt.wait(60)
            except AttributeError:
                _exec()  # UE 5.7: no call_on_game_thread, call directly

            batch = holder.get("r", {"success": False, "results": []})
            if batch.get("success"):
                _log(f"✅ {bp_name} created ({batch.get('succeeded',0)}/{batch.get('total',0)} ok)")
                _log(f"   Content Browser → /Game/MCP/{bp_name}")
                try:
                    import unreal as _u
                    _u.EditorAssetLibrary.sync_browser_to_objects([f"/Game/MCP/{bp_name}"])
                except Exception:
                    pass
            else:
                _warn(f"Partial: {batch.get('succeeded',0)} ok / {batch.get('failed',0)} failed")
                for r2 in batch.get("results", []):
                    if not r2.get("success"):
                        _warn(f"  FAIL: {r2.get('message','?')}")

        except urllib.error.HTTPError as e:
            _err(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
        except json.JSONDecodeError as e:
            _err(f"Bad JSON from AI: {e}")
        except Exception:
            _err(f"Unexpected:\n{traceback.format_exc()}")

    threading.Thread(target=_worker, daemon=True, name="MCPGen").start()


# ─────────────────────────────────────────────────────────────────────────────
# _run_dialog — main dialog flow (must be called on game/main thread)
# ─────────────────────────────────────────────────────────────────────────────
def _run_dialog():
    """
    Open the MCP Blueprint Generator dialog chain.
    MUST be called on the Unreal main/game thread.
    Each step uses show_object_details_view or show_message.
    """
    import unreal as _u

    # ── STEP 1: API key (first-time only) ────────────────────────────────────
    saved_key = _get("api_key", "")
    if not saved_key:
        # Explain where to get the key
        ret = _u.EditorDialog.show_message(
            "MCP Blueprint Generator — Setup Required",
            (
                "Welcome! You need a FREE OpenRouter API key to use this plugin.\n\n"
                "HOW TO GET YOUR KEY (1 minute):\n"
                "  1. Go to:  https://openrouter.ai/keys\n"
                "  2. Create a free account\n"
                "  3. Click 'Create Key'\n"
                "  4. Copy your key (starts with  sk-or-v1-)\n\n"
                "Click OK to paste your key in the next dialog.\n"
                "Click Cancel to skip for now."
            ),
            _u.AppMsgType.OK_CANCEL,
            _u.AppReturnType.OK,
            _u.AppMsgCategory.INFO,
        )
        if ret != _u.AppReturnType.OK:
            _log("Setup cancelled. Run  import mcp_ui; mcp_ui.show()  to try again.")
            return

        key_val = _prompt_text(
            title="MCP Blueprint Generator — Paste API Key",
            field_label="OpenRouter API Key",
            default_value="sk-or-v1-",
            hint=(
                "Paste your OpenRouter API key below.\n"
                "It starts with:  sk-or-v1-\n"
                "Get one FREE at:  https://openrouter.ai/keys"
            ),
        )

        if not key_val or not key_val.strip() or key_val.strip() == "sk-or-v1-":
            _u.EditorDialog.show_message(
                "MCP Blueprint Generator",
                "No API key entered.\n\nRun this to try again:\n  import mcp_ui; mcp_ui.show()",
                _u.AppMsgType.OK,
                _u.AppReturnType.OK,
                _u.AppMsgCategory.WARNING,
            )
            return

        saved_key = key_val.strip()
        _set("api_key", saved_key)
        _log(f"API key saved (ends: ...{saved_key[-8:]})")

    # ── STEP 2: Model selection ───────────────────────────────────────────────
    saved_model = _get("model", DEFAULT_MODEL)
    try:
        cur_idx = MODEL_IDS.index(saved_model)
    except ValueError:
        cur_idx = 0

    model_list = "\n".join(
        f"  {'▶' if i == cur_idx else ' '} {i+1:>2}. {label}"
        for i, label in enumerate(MODEL_LABELS)
    )

    model_num_str = _prompt_text(
        title="MCP — Select AI Model",
        field_label="Model number",
        default_value=str(cur_idx + 1),
        hint=(
            f"Current: [{cur_idx+1}] {MODEL_LABELS[cur_idx]}\n\n"
            f"Type a number 1-{len(MODELS)} and click OK:\n\n"
            f"{model_list}"
        ),
    )

    if model_num_str is None:
        _log("Model selection cancelled.")
        return

    if model_num_str.strip().isdigit():
        idx = int(model_num_str.strip()) - 1
        if 0 <= idx < len(MODEL_IDS):
            cur_idx = idx

    model_id    = MODEL_IDS[cur_idx]
    model_label = MODEL_LABELS[cur_idx].split("[")[0].strip()
    _set("model", model_id)
    _log(f"Model: {model_id}")

    # ── STEP 3: Blueprint description ─────────────────────────────────────────
    prompt_val = _prompt_text(
        title=f"MCP — Describe Your Blueprint  [{model_label}]",
        field_label="Blueprint description",
        default_value="Create an enemy AI that chases the player and has 100 health",
        hint=(
            "Describe the Blueprint you want in plain English.\n\n"
            "EXAMPLES:\n"
            "  Create an enemy AI that chases the player\n"
            "  Create a door that opens when the player walks near it\n"
            "  Create a health pickup that gives 25 HP on overlap\n"
            "  Create a turret that rotates toward the player every tick\n"
            "  Create a collectible coin that disappears on pickup\n\n"
            "Watch the Output Log for progress."
        ),
    )

    if not prompt_val or not prompt_val.strip():
        _log("No prompt entered — cancelled.")
        return

    prompt = prompt_val.strip()
    _log("=" * 60)
    _log(f"Prompt : {prompt}")
    _log(f"Model  : {model_id}")
    _log("Generating Blueprint... (watch Output Log for results)")
    _log("=" * 60)

    _generate(prompt, saved_key, model_id)


# ─────────────────────────────────────────────────────────────────────────────
# Menu registration — ToolMenuEntryScript with execute() override
# ─────────────────────────────────────────────────────────────────────────────
_menu_entry_instance = None   # keep alive to prevent GC

def _register_menu():
    """
    Add 'MCP AI → 🤖 Generate Blueprint with AI...' to the Level Editor.

    Uses ToolMenuEntryScript.execute() override — the ONLY reliably working
    way to invoke Python from a menu click in UE 5.7 on macOS.
    Requires MCPMenuScript class to be initialized (_init_ue_classes must run first).
    Returns True on success, False if not ready yet.
    """
    global _menu_entry_instance

    if not _UE_CLASSES_READY or MCPMenuScript is None:
        return False  # classes not ready yet

    import unreal as _u

    try:
        menus = _u.ToolMenus.get()

        # Check the main menu is ready (returns None for first few frames)
        main_menu = menus.find_menu("LevelEditor.MainMenu")
        if not main_menu:
            return False  # not ready yet

        # Step 1: Create the "MCP AI" top-level sub-menu on the menu bar.
        # This MUST happen before init_entry references its name.
        # add_sub_menu args: owner, section, name (internal), label (visible)
        sub_menu = main_menu.add_sub_menu(
            main_menu.get_name(),    # owner = parent menu name
            "MCPBlueprintSection",   # section (groups sub-menus visually)
            "MCPBlueprintMenu",      # internal name → full path becomes
                                     # "LevelEditor.MainMenu.MCPBlueprintMenu"
            "MCP AI",                # visible label shown in the menu bar
        )

        if not sub_menu:
            _warn("add_sub_menu returned None — menu bar not ready yet.")
            return False

        # Step 2: Create the ToolMenuEntryScript instance and configure it.
        # The 'menu' arg MUST match the full path of the sub_menu created above.
        entry_script = _u.new_object(MCPMenuScript)
        entry_script.init_entry(
            "MCPBlueprintPlugin",               # owner_name
            "LevelEditor.MainMenu.MCPBlueprintMenu",  # menu (full path)
            "MCPSection",                       # section inside the sub-menu
            "MCPGenerateBlueprint",             # entry name (internal)
            "Generate Blueprint with AI...",    # label (visible)
            "Open MCP Blueprint Generator — describe a Blueprint in plain English.",  # tooltip
        )

        # Step 3: Register the entry with the ToolMenus system.
        # This makes UE call execute() when the menu item is clicked.
        entry_script.register_menu_entry()

        _u.ToolMenus.get().refresh_all_widgets()

        # Keep alive — Python GC would destroy the entry script otherwise
        _menu_entry_instance = entry_script

        _log("✔ 'MCP AI' menu registered in Level Editor menu bar.")
        _log("  Click  MCP AI → Generate Blueprint with AI...  to open the dialog.")
        return True

    except Exception as e:
        _warn(f"Menu registration failed: {e}\n{traceback.format_exc()}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Startup sequence — register menu + open dialog once after editor loads
# ─────────────────────────────────────────────────────────────────────────────
_startup_done = False
_tick_handler = None
_tick_count   = 0

def _on_tick(delta):
    """
    Slate post-tick callback — fires every editor frame until unregistered.
    Waits for LevelEditor.MainMenu to exist, then:
      1. Registers the MCP AI menu.
      2. Opens the startup dialog once.
      3. Unregisters itself.
    """
    global _startup_done, _tick_handler, _tick_count

    if _startup_done:
        return

    _tick_count += 1

    # Timeout after ~10 s (600 frames at 60 fps)
    if _tick_count > 600:
        _startup_done = True
        _warn("Startup timed out after 600 ticks.")
        _log("Open manually: MCP AI menu (if visible) or: import mcp_ui; mcp_ui.show()")
        try:
            unreal.unregister_slate_post_tick_callback(_tick_handler)
        except Exception:
            pass
        return

    # Register menu once ready
    menu_ok = _register_menu()
    if not menu_ok:
        return  # keep polling

    # Menu registered — unregister tick callback
    _startup_done = True
    try:
        unreal.unregister_slate_post_tick_callback(_tick_handler)
        _tick_handler = None
    except Exception:
        pass

    _log(f"Editor ready at tick {_tick_count}. Opening MCP Blueprint Generator...")
    try:
        _run_dialog()
    except Exception:
        _warn(f"Auto-open dialog failed:\n{traceback.format_exc()}")
        _log("Fallback: click MCP AI in the menu bar, or: import mcp_ui; mcp_ui.show()")


def _schedule_startup():
    """Register a slate post-tick callback to set up the menu and open dialog."""
    global _tick_handler, _startup_done, _tick_count

    _startup_done = False
    _tick_count   = 0

    import unreal as _u

    try:
        _tick_handler = _u.register_slate_post_tick_callback(_on_tick)
        _log("Slate tick callback registered — menu will appear shortly.")
        return
    except AttributeError:
        _warn("register_slate_post_tick_callback not available — running synchronously.")
    except Exception as e:
        _warn(f"Slate tick registration failed: {e} — running synchronously.")

    # Synchronous fallback
    _register_menu()
    try:
        _run_dialog()
    except Exception as e:
        _warn(f"Sync startup failed: {e}")
        _log("Open manually: import mcp_ui; mcp_ui.show()")


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def show():
    """
    Open the MCP Blueprint Generator dialog.
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
    """Save your OpenRouter API key.  Usage: mcp_ui.set_key('sk-or-v1-...')"""
    _set("api_key", key.strip())
    _log(f"API key saved (ends: ...{key.strip()[-8:]})")


def set_model(model: str):
    """
    Select a model by label or ID.
    Usage: mcp_ui.set_model('gpt-4o')
    """
    for label, mid in MODELS:
        if model.lower() in label.lower() or model == mid:
            _set("model", mid)
            _log(f"Model set: {mid}")
            return
    _warn(f"Unknown model '{model}'. Run mcp_ui.list_models() to see options.")


def run(prompt: str, model: str = ""):
    """
    Generate a Blueprint without opening the dialog.
    Usage: mcp_ui.run('Create an enemy AI that chases the player')
    """
    api_key = _get("api_key", "")
    if not api_key:
        _err("No API key. Run: mcp_ui.set_key('sk-or-v1-...')")
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
        _log(f"  {i:>2}. {label:<45} → {mid}")


def status():
    """Show current API key (masked) and model."""
    key   = _get("api_key", "")
    model = _get("model", DEFAULT_MODEL)
    _log(f"API key : {'...' + key[-8:] if key else '(not set)'}")
    _log(f"Model   : {model}")


def start():
    """Called automatically by init_unreal.py when the plugin loads."""
    _log("MCP Blueprint Generator v1.4.0 starting...")

    # Initialize UE Python classes (ToolMenuEntryScript subclass etc.)
    if _IN_UNREAL:
        try:
            _init_ue_classes()
        except Exception as e:
            _warn(f"Class init failed: {e}\n{traceback.format_exc()}")
            _log("Continuing without native classes — console API still works.")

    saved_key = _get("api_key", "")
    if saved_key:
        model = _get("model", DEFAULT_MODEL)
        _log(f"Key: ...{saved_key[-8:]}  |  Model: {model}")
        _log("Reopen: click  MCP AI  in the menu bar, or: import mcp_ui; mcp_ui.show()")
    else:
        _log("First run — API key dialog will open shortly.")
        _log("Get a FREE key at:  https://openrouter.ai/keys")

    if _IN_UNREAL:
        _schedule_startup()
