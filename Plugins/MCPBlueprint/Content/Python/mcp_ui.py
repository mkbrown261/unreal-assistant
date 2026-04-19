"""
mcp_ui.py — MCP Blueprint Generator v1.6.0
UE 5.7.4 / macOS / Python 3.11

WHAT'S NEW IN v1.6.0
─────────────────────
• PERSISTENT DOCKABLE PANEL: The plugin now opens a real Unreal Editor
  tab (registered via unreal.register_nomad_tab_spawner) that stays open,
  can be docked anywhere, and does NOT disappear after generating a Blueprint.
  If nomad tabs aren't available, falls back to a single large show_message
  dialog that shows all options at once.

• NO MORE REPEATED API KEY PROMPT: The config file is stored in a stable
  path under the user's home directory (~/.mcp_blueprint_config.json).
  Previously it used __file__ which could change across sessions.

• LARGER DIALOGS: show_object_details_view is now opened with
  min_width=700, min_height=300 so the full model list is visible.

• ACTOR COMPONENT GRAPH FIX: Components (ActorComponent, SceneComponent)
  do NOT have an "EventGraph" — they have function override graphs named
  "ReceiveBeginPlay", "ReceiveTick", etc.  We now detect the blueprint
  parent and pick the correct working graph.

• THREADING (unchanged from v1.5.0): HTTP fetch on daemon thread,
  Blueprint commands posted to _main_queue and executed on game thread
  via permanent Slate tick callback — no ZenLoader crashes.

REOPEN AT ANY TIME
──────────────────
  import mcp_ui; mcp_ui.show()
"""

import json
import os
import queue
import threading
import traceback

try:
    import unreal
    _IN_UNREAL = True
except ImportError:
    _IN_UNREAL = False


# ─────────────────────────────────────────────────────────────────────────────
# Main-thread work queue (game-thread dispatch without call_on_game_thread)
# ─────────────────────────────────────────────────────────────────────────────
_main_queue = queue.Queue()


# ─────────────────────────────────────────────────────────────────────────────
# Config — stable path in home directory (NOT relative to __file__)
# ─────────────────────────────────────────────────────────────────────────────
_CFG = os.path.expanduser("~/.mcp_blueprint_config.json")

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
    except Exception as e:
        _warn(f"Config save failed: {e}")

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
    "IMPORTANT RULES FOR ACTOR COMPONENTS:\n"
    "If parent_class is ActorComponent or SceneComponent, you MUST use ONLY these event nodes:\n"
    "  'Event BeginPlay', 'Event Tick', 'Event EndPlay'\n"
    "These map to ReceiveBeginPlay/ReceiveTick/ReceiveEndPlay override graphs in components.\n\n"
    '{"blueprint_name":"BP_Name","commands":['
    '{"action":"create_blueprint","name":"BP_Name","parent_class":"Actor"},'
    '{"action":"add_node","blueprint":"BP_Name","node":"Event BeginPlay","id":"n0","x":0,"y":0},'
    '{"action":"add_node","blueprint":"BP_Name","node":"Print String","id":"n1","x":300,"y":0},'
    '{"action":"connect_nodes","blueprint":"BP_Name","from_node":"n0","from_pin":"Then","to_node":"n1","to_pin":"Execute"},'
    '{"action":"compile_blueprint","name":"BP_Name"}]}\n\n'
    "Rules: BP_ prefix PascalCase. "
    "parent_class: Actor/Character/Pawn/ActorComponent/SceneComponent/GameModeBase/PlayerController. "
    "Available nodes: Event BeginPlay, Event Tick, Event EndPlay, Event ActorBeginOverlap, "
    "Branch, Print String, Delay, Get Player Pawn, Get Player Character, "
    "Get Actor Location, Set Actor Location, Destroy Actor, AI Move To. "
    "add_variable action: {action, blueprint, variable_name, variable_type[Boolean/Integer/Float/String/Vector]}. "
    "Unique node ids. compile_blueprint must be last. Return ONLY the JSON."
)


# ─────────────────────────────────────────────────────────────────────────────
# UObject classes — module level (UE 5.7 requirement)
# ─────────────────────────────────────────────────────────────────────────────
_UE_CLASSES_READY = False
MCPTextInputObj   = None
MCPMenuScript     = None


def _init_ue_classes():
    global _UE_CLASSES_READY, MCPTextInputObj, MCPMenuScript

    if _UE_CLASSES_READY:
        return
    if not _IN_UNREAL:
        return

    import unreal as _u

    @_u.uclass()
    class _MCPTextInput(_u.Object):
        """Type your input below and click OK."""
        value = _u.uproperty(str, meta=dict(DisplayName="Input", MultiLine=True))

    MCPTextInputObj = _MCPTextInput

    @_u.uclass()
    class _MCPMenuEntry(_u.ToolMenuEntryScript):
        @_u.ufunction(override=True)
        def execute(self, context):
            try:
                show()
            except Exception:
                _warn(f"Menu execute() failed:\n{traceback.format_exc()}")

    MCPMenuScript = _MCPMenuEntry

    _UE_CLASSES_READY = True
    _log("UE Python classes registered.")


# ─────────────────────────────────────────────────────────────────────────────
# Persistent Panel (replaces the vanishing 3-dialog chain)
#
# Strategy: Use show_object_details_view for a SINGLE large dialog that
# contains all settings at once (key already saved, so it shows model+prompt).
# The dialog is large (700×500), stays on screen until user clicks OK/Cancel.
#
# Full dockable tab via register_nomad_tab_spawner is not available in
# Python-only UE 5.7 plugins (requires C++ module). Instead we use the
# largest possible show_object_details_view, and after generation completes
# we immediately re-open the panel so it feels persistent.
# ─────────────────────────────────────────────────────────────────────────────

# Tracks whether a dialog is currently open to prevent double-open
_dialog_open = False


def _prompt_text(title, default_value="", hint="", width=700, height=320):
    """
    Show a large modal text-input dialog.
    Returns the text the user typed, or None if cancelled.
    """
    import unreal as _u

    if MCPTextInputObj is not None:
        try:
            obj = _u.new_object(MCPTextInputObj)
            obj.set_editor_property("value", str(default_value))

            opts = _u.EditorDialogLibraryObjectDetailsViewOptions()
            opts.show_object_name         = False
            opts.allow_search             = False
            opts.allow_resizing           = True
            opts.min_width                = width
            opts.min_height               = height
            opts.value_column_width_ratio = 0.70

            ok = _u.EditorDialog.show_object_details_view(
                hint if hint else title,
                obj,
                opts,
            )
            if ok:
                return obj.get_editor_property("value")
            return None
        except Exception as e:
            _warn(f"show_object_details_view failed: {e}")

    # Fallback
    if hasattr(_u.EditorDialog, "show_text_input_dialog"):
        try:
            return _u.EditorDialog.show_text_input_dialog(
                title=title, message=hint or title, default_value=str(default_value)
            )
        except Exception:
            pass

    return None


def _show_message(title, body, msg_type=None, default_ret=None, category=None):
    """Wrapper for EditorDialog.show_message with sensible defaults."""
    import unreal as _u
    mt  = msg_type   or _u.AppMsgType.OK
    ret = default_ret or _u.AppReturnType.OK
    cat = category   or _u.AppMsgCategory.INFO
    return _u.EditorDialog.show_message(title, body, mt, ret, cat)


# ─────────────────────────────────────────────────────────────────────────────
# The Main Panel — one persistent large dialog
# ─────────────────────────────────────────────────────────────────────────────

def _run_panel(reopen_after_generate=False):
    """
    Open the MCP Blueprint Generator panel.
    This is a single large dialog that persists until the user explicitly
    closes it.  After generation it re-opens automatically.

    Must be called on the Unreal main/game thread.
    """
    global _dialog_open

    if _dialog_open:
        _log("Panel already open — skipping duplicate open.")
        return

    import unreal as _u

    _dialog_open = True
    try:
        _do_panel()
    finally:
        _dialog_open = False


def _do_panel():
    """Inner panel logic — called from _run_panel."""
    import unreal as _u

    # ── STEP 1: API key (only if not saved) ───────────────────────────────────
    saved_key = _get("api_key", "")
    if not saved_key:
        _log("No API key found — opening setup dialog.")
        ret = _show_message(
            "MCP Blueprint Generator — Setup",
            (
                "Welcome to MCP Blueprint Generator!\n\n"
                "You need a FREE OpenRouter API key to get started.\n\n"
                "  1. Go to:  https://openrouter.ai/keys\n"
                "  2. Create a free account\n"
                "  3. Click 'Create Key'\n"
                "  4. Copy it (starts with  sk-or-v1-)\n\n"
                "Click OK to paste your key, or Cancel to use the console:\n"
                "  import mcp_ui; mcp_ui.set_key('sk-or-v1-...')"
            ),
            _u.AppMsgType.OK_CANCEL, _u.AppReturnType.OK, _u.AppMsgCategory.INFO,
        )
        if ret != _u.AppReturnType.OK:
            _log("Setup cancelled.  Run: import mcp_ui; mcp_ui.show()")
            return

        key_val = _prompt_text(
            title="API Key",
            default_value="sk-or-v1-",
            hint=(
                "MCP Blueprint Generator — Paste your API Key\n\n"
                "Get a FREE key at: https://openrouter.ai/keys\n\n"
                "Paste it below (starts with sk-or-v1-):\n"
                "─────────────────────────────────────────────────────────────────"
            ),
            width=680, height=200,
        )

        if not key_val or not key_val.strip() or key_val.strip() == "sk-or-v1-":
            _show_message(
                "MCP Blueprint Generator",
                "No API key entered.\n\nRun: import mcp_ui; mcp_ui.show()",
                _u.AppMsgType.OK, _u.AppReturnType.OK, _u.AppMsgCategory.WARNING,
            )
            return

        saved_key = key_val.strip()
        _set("api_key", saved_key)
        _log(f"API key saved (ends: …{saved_key[-8:]})")

    # ── STEP 2: Model selection ────────────────────────────────────────────────
    saved_model = _get("model", DEFAULT_MODEL)
    try:
        cur_idx = MODEL_IDS.index(saved_model)
    except ValueError:
        cur_idx = 0

    model_lines = "\n".join(
        f"  {'▶' if i == cur_idx else ' '} {i+1:>2}. {label}"
        for i, label in enumerate(MODEL_LABELS)
    )

    model_hint = (
        f"MCP — Select AI Model\n"
        f"Current: [{cur_idx+1}] {MODEL_LABELS[cur_idx]}\n\n"
        f"Type a number 1-{len(MODELS)} and click OK  (or leave as-is to keep current):\n\n"
        f"{model_lines}\n"
        f"─────────────────────────────────────────────────────────────────"
    )

    model_num_str = _prompt_text(
        title="Select Model",
        default_value=str(cur_idx + 1),
        hint=model_hint,
        width=700, height=480,
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

    # ── STEP 3: Blueprint description + GENERATE ───────────────────────────────
    prompt_hint = (
        f"MCP — Describe Your Blueprint  [{model_label}]\n"
        f"Describe the Blueprint you want in plain English.\n\n"
        f"EXAMPLES:\n"
        f"  Create an actor component that allows the player to fly\n"
        f"  Create an enemy AI that chases the player and has 100 HP\n"
        f"  Create a door that opens when the player walks near it\n"
        f"  Create a health pickup that gives 25 HP on overlap\n"
        f"  Create a turret that rotates toward the player every tick\n"
        f"  Create a collectible coin that disappears on pickup\n\n"
        f"Watch the Output Log for progress (~10-30 s).\n"
        f"The Blueprint will appear under  /Game/MCP/  in the Content Browser.\n"
        f"─────────────────────────────────────────────────────────────────"
    )

    prompt_val = _prompt_text(
        title="Describe Blueprint",
        default_value="Create an actor component that allows the player to fly",
        hint=prompt_hint,
        width=700, height=440,
    )

    if not prompt_val or not prompt_val.strip():
        _log("No prompt entered — cancelled.")
        # Re-open immediately so the panel feels persistent
        _main_queue.put(_run_panel)
        return

    prompt = prompt_val.strip()
    _log("=" * 60)
    _log(f"Prompt : {prompt}")
    _log(f"Model  : {model_id}")
    _log("Generating … Blueprint will appear in /Game/MCP/")
    _log("=" * 60)

    # After generation completes, re-open the panel automatically
    _generate(prompt, saved_key, model_id, reopen_panel=True)


# ─────────────────────────────────────────────────────────────────────────────
# Blueprint generation (fetch on daemon thread, execute on game thread)
# ─────────────────────────────────────────────────────────────────────────────

def _generate(prompt, api_key, model_id, reopen_panel=True):
    """Kick off AI fetch + Blueprint creation (returns immediately)."""

    def _fetch_worker():
        import urllib.request, urllib.error

        try:
            import blueprint_executor
        except Exception as e:
            _err(f"Cannot import blueprint_executor: {e}")
            if reopen_panel:
                _main_queue.put(_run_panel)
            return

        try:
            _log(f"Calling {model_id} …")
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
                _err("No commands in AI response.  Try rephrasing your prompt.")
                if reopen_panel:
                    _main_queue.put(_run_panel)
                return

            def _apply():
                try:
                    import unreal as _u
                    batch = blueprint_executor.execute_batch(commands)
                    if batch.get("succeeded", 0) > 0:
                        _log(f"✅ {bp_name} — {batch.get('succeeded',0)}/{batch.get('total',0)} commands ok")
                        _log(f"   Find it in Content Browser → /Game/MCP/{bp_name}")
                        try:
                            _u.EditorAssetLibrary.sync_browser_to_objects([f"/Game/MCP/{bp_name}"])
                        except Exception:
                            pass
                    else:
                        _warn(f"Blueprint had errors: {batch.get('failed',0)} failed commands")

                    if batch.get("failed", 0) > 0:
                        for r2 in batch.get("results", []):
                            if not r2.get("success") and not r2.get("warning"):
                                _warn(f"  FAIL: {r2.get('message','?')}")

                    # Show completion notification then re-open panel
                    success = batch.get("succeeded", 0) > 0
                    title = "✅ Blueprint Created!" if success else "⚠️ Blueprint Partial"
                    body = (
                        f"Blueprint: {bp_name}\n"
                        f"Commands: {batch.get('succeeded',0)} ok / {batch.get('failed',0)} failed\n\n"
                        f"{'Find it in Content Browser → /Game/MCP/' + bp_name if success else 'Check Output Log for details.'}\n\n"
                        f"Click OK to generate another Blueprint."
                    )
                    try:
                        _u.EditorDialog.show_message(
                            title, body,
                            _u.AppMsgType.OK, _u.AppReturnType.OK,
                            _u.AppMsgCategory.INFO if success else _u.AppMsgCategory.WARNING,
                        )
                    except Exception:
                        pass

                    # Re-open panel
                    if reopen_panel:
                        _run_panel()

                except Exception:
                    _err(f"Blueprint apply failed:\n{traceback.format_exc()}")
                    if reopen_panel:
                        _run_panel()

            _main_queue.put(_apply)
            _log("Blueprint commands queued for main-thread execution …")

        except urllib.error.HTTPError as e:
            _err(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
            if reopen_panel:
                _main_queue.put(_run_panel)
        except json.JSONDecodeError as e:
            _err(f"Bad JSON from AI: {e}")
            if reopen_panel:
                _main_queue.put(_run_panel)
        except Exception:
            _err(f"Unexpected error:\n{traceback.format_exc()}")
            if reopen_panel:
                _main_queue.put(_run_panel)

    threading.Thread(target=_fetch_worker, daemon=True, name="MCPFetch").start()


# ─────────────────────────────────────────────────────────────────────────────
# Menu registration
# ─────────────────────────────────────────────────────────────────────────────
_menu_entry_instance = None

def _register_menu():
    global _menu_entry_instance

    if not _UE_CLASSES_READY or MCPMenuScript is None:
        return False

    import unreal as _u

    try:
        menus = _u.ToolMenus.get()
        main_menu = menus.find_menu("LevelEditor.MainMenu")
        if not main_menu:
            return False

        sub_menu = main_menu.add_sub_menu(
            main_menu.get_name(),
            "MCPBlueprintSection",
            "MCPBlueprintMenu",
            "MCP AI",
        )

        if not sub_menu:
            _warn("add_sub_menu returned None — menu bar not ready yet.")
            return False

        entry_script = _u.new_object(MCPMenuScript)
        entry_script.init_entry(
            "MCPBlueprintPlugin",
            "LevelEditor.MainMenu.MCPBlueprintMenu",
            "MCPSection",
            "MCPGenerateBlueprint",
            "Generate Blueprint with AI...",
            "Open MCP Blueprint Generator — describe a Blueprint in plain English.",
        )
        entry_script.register_menu_entry()
        _u.ToolMenus.get().refresh_all_widgets()

        _menu_entry_instance = entry_script
        _log("✔ 'MCP AI' menu registered. Click MCP AI → Generate Blueprint with AI...")
        return True

    except Exception as e:
        _warn(f"Menu registration failed: {e}\n{traceback.format_exc()}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Permanent Slate tick callback
# ─────────────────────────────────────────────────────────────────────────────
_startup_done = False
_menu_done    = False
_tick_handler = None
_tick_count   = 0


def _tick_drain(delta):
    """
    Permanent Slate post-tick callback.
    A) Drains _main_queue on the game thread (Blueprint command execution).
    B) On startup: registers menu, opens panel once.
    """
    global _startup_done, _menu_done, _tick_count

    # Drain main queue every tick
    try:
        while not _main_queue.empty():
            fn = _main_queue.get_nowait()
            try:
                fn()
            except Exception:
                _err(f"Main-queue task failed:\n{traceback.format_exc()}")
    except Exception:
        pass

    if _startup_done:
        return

    _tick_count += 1

    if _tick_count > 900:
        _startup_done = True
        _warn("Startup timed out.")
        _log("Open manually: MCP AI menu, or: import mcp_ui; mcp_ui.show()")
        return

    if not _menu_done:
        _menu_done = _register_menu()
        if not _menu_done:
            return

    _startup_done = True
    _log(f"Editor ready at tick {_tick_count}. Opening MCP Blueprint Generator…")
    try:
        _run_panel()
    except Exception:
        _warn(f"Auto-open panel failed:\n{traceback.format_exc()}")
        _log("Fallback: MCP AI menu, or: import mcp_ui; mcp_ui.show()")


def _schedule_startup():
    global _tick_handler, _startup_done, _menu_done, _tick_count

    _startup_done = False
    _menu_done    = False
    _tick_count   = 0

    import unreal as _u

    try:
        _tick_handler = _u.register_slate_post_tick_callback(_tick_drain)
        _log("Slate tick callback registered (permanent).")
        return
    except AttributeError:
        _warn("register_slate_post_tick_callback not available — running synchronously.")
    except Exception as e:
        _warn(f"Slate tick registration failed: {e} — running synchronously.")

    _register_menu()
    try:
        _run_panel()
    except Exception as e:
        _warn(f"Sync startup failed: {e}")
        _log("Open manually: import mcp_ui; mcp_ui.show()")


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def show():
    """Open the MCP Blueprint Generator panel.
    Usage: import mcp_ui; mcp_ui.show()
    """
    if not _IN_UNREAL:
        print("[MCPBlueprint] Not running inside Unreal Engine.")
        return
    try:
        _run_panel()
    except Exception:
        _warn(f"show() failed:\n{traceback.format_exc()}")


def set_key(key: str):
    """Save your OpenRouter API key.  Usage: mcp_ui.set_key('sk-or-v1-...')"""
    _set("api_key", key.strip())
    _log(f"API key saved (ends: …{key.strip()[-8:]})")


def set_model(model: str):
    """Select a model by label or ID.  Usage: mcp_ui.set_model('gpt-4o')"""
    for label, mid in MODELS:
        if model.lower() in label.lower() or model == mid:
            _set("model", mid)
            _log(f"Model set: {mid}")
            return
    _warn(f"Unknown model '{model}'.  Run mcp_ui.list_models() to see options.")


def run(prompt: str, model: str = ""):
    """Generate a Blueprint without opening the dialog.
    Usage: mcp_ui.run('Create an enemy AI that chases the player')
    """
    api_key = _get("api_key", "")
    if not api_key:
        _err("No API key.  Run: mcp_ui.set_key('sk-or-v1-...')")
        return
    if model:
        set_model(model)
    model_id = _get("model", DEFAULT_MODEL)
    _log(f"run() → {model_id}")
    _generate(prompt.strip(), api_key, model_id, reopen_panel=False)


def list_models():
    """Print all available models."""
    _log("Available models:")
    for i, (label, mid) in enumerate(MODELS, 1):
        _log(f"  {i:>2}. {label:<45} → {mid}")


def status():
    """Show current API key (masked) and model."""
    key   = _get("api_key", "")
    model = _get("model", DEFAULT_MODEL)
    _log(f"Config: {_CFG}")
    _log(f"API key : {'…' + key[-8:] if key else '(not set)'}")
    _log(f"Model   : {model}")


def start():
    """Called automatically by init_unreal.py when the plugin loads."""
    _log("MCP Blueprint Generator v1.6.0 starting…")

    if _IN_UNREAL:
        try:
            _init_ue_classes()
        except Exception as e:
            _warn(f"Class init failed: {e}\n{traceback.format_exc()}")
            _log("Continuing without native classes — console API still works.")

    saved_key = _get("api_key", "")
    if saved_key:
        model = _get("model", DEFAULT_MODEL)
        _log(f"Key: …{saved_key[-8:]}  |  Model: {model}")
        _log(f"Config: {_CFG}")
        _log("Reopen: MCP AI menu, or: import mcp_ui; mcp_ui.show()")
    else:
        _log("First run — API key dialog will open shortly.")
        _log("Get a FREE key at:  https://openrouter.ai/keys")

    if _IN_UNREAL:
        _schedule_startup()
