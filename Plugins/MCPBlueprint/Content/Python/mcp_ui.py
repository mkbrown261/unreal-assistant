"""
mcp_ui.py — MCP Blueprint Generator v1.7.1
UE 5.7.4 / macOS / Python 3.11

WHAT'S FIXED IN v1.7.0
───────────────────────
• SYSTEM PROMPT REWRITE: The AI no longer generates add_node/connect_nodes
  commands (which the UE 5.7 Python API cannot execute). Instead it generates
  create_blueprint + add_variable + add_function + blueprint_instructions.
  Blueprint assets are created with full variable/function structure; the
  blueprint_instructions command logs exactly what nodes to add in the editor.

• DIALOG RE-OPEN BUG: _dialog_open guard was getting stuck True when
  _apply() tried to call _run_panel() while the panel was still in its
  finally block. Fixed by posting re-open to _main_queue instead of calling
  directly, ensuring the guard is fully cleared first.

• API KEY NOT SAVED: _dialog_open stuck True meant the config save path
  was never reaching _do_panel on the next call. Now guaranteed to reset.

• SMALLER RELIABLE DIALOGS: Replaced show_object_details_view (broken in
  UE 5.7 for text input) with show_message for info/confirmation dialogs and
  show_text_input_dialog for text entry. Falls back gracefully.

• THREADING (unchanged from v1.5.0): HTTP fetch on daemon thread, Blueprint
  commands posted to _main_queue executed on game thread via Slate tick.

REOPEN AT ANY TIME
──────────────────
  import mcp_ui; mcp_ui.show()

CONSOLE SHORTCUTS
─────────────────
  mcp_ui.set_key('sk-or-v1-...')   # save API key
  mcp_ui.run('Make a fly component')  # skip the dialog
  mcp_ui.status()                  # check current config
  mcp_ui.list_models()             # list all models
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

# ─────────────────────────────────────────────────────────────────────────────
# System prompt — HONEST about UE 5.7 Python limitations
#
# The UE 5.7 Python API CANNOT add nodes or wire pins programmatically.
# BlueprintEditorLibrary only exposes:
#   create_blueprint_asset_with_parent, find_event_graph, find_graph,
#   add_function_graph, add_member_variable, compile_blueprint.
#
# So the AI generates:
#   1. create_blueprint  — creates the asset
#   2. add_variable      — adds member variables
#   3. add_function      — creates named function stubs
#   4. blueprint_instructions — logs what nodes/wiring to add manually
#   5. compile_blueprint — final compile
#
# The blueprint_instructions field gives the user step-by-step guidance on
# what to wire inside the Blueprint editor. This is honest and useful.
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are an Unreal Engine 5.7 Blueprint scaffolding assistant.

The UE 5.7 Python API cannot add nodes or wire pins — only create the asset,
add variables, and add function stubs. You will generate the Blueprint structure
plus detailed instructions for what the user must wire manually in the editor.

Respond with ONLY a valid JSON object. No markdown, no explanation, no code fences.

SUPPORTED ACTIONS (use only these):
  create_blueprint   — {"action":"create_blueprint","name":"BP_Name","parent_class":"Actor"}
  add_variable       — {"action":"add_variable","blueprint":"BP_Name","variable_name":"Speed","variable_type":"Float","default_value":"600.0"}
  add_function       — {"action":"add_function","blueprint":"BP_Name","function_name":"ActivateFlight"}
  blueprint_instructions — {"action":"blueprint_instructions","blueprint":"BP_Name","instructions":"Step-by-step wiring guide"}
  compile_blueprint  — {"action":"compile_blueprint","name":"BP_Name"}

VARIABLE TYPES: Boolean, Integer, Float, String, Vector, Rotator, Transform

PARENT CLASSES:
  Actor, Character, Pawn, ActorComponent, SceneComponent,
  GameModeBase, PlayerController, AIController, UserWidget, GameInstance

NAMING: BP_ prefix, PascalCase. compile_blueprint must be last.

EXAMPLE — fly component:
{
  "blueprint_name": "BP_FlyComponent",
  "commands": [
    {"action":"create_blueprint","name":"BP_FlyComponent","parent_class":"ActorComponent"},
    {"action":"add_variable","blueprint":"BP_FlyComponent","variable_name":"FlySpeed","variable_type":"Float","default_value":"600.0"},
    {"action":"add_variable","blueprint":"BP_FlyComponent","variable_name":"IsFlying","variable_type":"Boolean","default_value":"false"},
    {"action":"add_function","blueprint":"BP_FlyComponent","function_name":"ActivateFlight"},
    {"action":"add_function","blueprint":"BP_FlyComponent","function_name":"DeactivateFlight"},
    {"action":"blueprint_instructions","blueprint":"BP_FlyComponent","instructions":"EVENT GRAPH — ReceiveBeginPlay:\\n  No setup needed.\\n\\nFUNCTION: ActivateFlight\\n  1. Set IsFlying = True\\n  2. Get Owner → Cast To Character → Get Character Movement → Set Movement Mode = Flying\\n  3. Set Max Fly Speed = FlySpeed\\n\\nFUNCTION: DeactivateFlight\\n  1. Set IsFlying = False\\n  2. Get Owner → Cast To Character → Get Character Movement → Set Movement Mode = Walking\\n\\nTO ADD THIS TO YOUR CHARACTER:\\n  1. Open your Character Blueprint\\n  2. Add Component → search 'BP_FlyComponent'\\n  3. In Input events: call ActivateFlight / DeactivateFlight on key press"},
    {"action":"compile_blueprint","name":"BP_FlyComponent"}
  ]
}

Generate a complete, useful blueprint_instructions with exact node names the user needs to add.
Return ONLY the JSON."""


# ─────────────────────────────────────────────────────────────────────────────
# UObject classes — module level (UE 5.7 requirement)
# ─────────────────────────────────────────────────────────────────────────────
_UE_CLASSES_READY = False
MCPMenuScript     = None


def _init_ue_classes():
    global _UE_CLASSES_READY, MCPMenuScript

    if _UE_CLASSES_READY:
        return
    if not _IN_UNREAL:
        return

    import unreal as _u

    @_u.uclass()
    class _MCPMenuEntry(_u.ToolMenuEntryScript):
        @_u.ufunction(override=True)
        def execute(self, context):
            try:
                _enqueue_show()
            except Exception:
                _warn(f"Menu execute() failed:\n{traceback.format_exc()}")

    MCPMenuScript = _MCPMenuEntry

    _UE_CLASSES_READY = True
    _log("UE Python classes registered.")


# ─────────────────────────────────────────────────────────────────────────────
# Dialog helpers
#
# UE 5.7 dialog APIs that reliably work:
#   EditorDialog.show_message(title, body, msg_type, ret_type, category)
#   EditorDialog.show_text_input_dialog(title, message, default_value)  [sometimes]
#
# show_object_details_view can sometimes work for structured input but is
# unreliable for simple text entry in UE 5.7.
# ─────────────────────────────────────────────────────────────────────────────

def _show_message(title, body, msg_type=None, default_ret=None, category=None):
    """Show a modal message dialog. Returns AppReturnType."""
    import unreal as _u
    mt  = msg_type   if msg_type   is not None else _u.AppMsgType.OK
    ret = default_ret if default_ret is not None else _u.AppReturnType.OK
    cat = category   if category   is not None else _u.AppMsgCategory.INFO
    try:
        return _u.EditorDialog.show_message(title, body, mt, ret, cat)
    except Exception as e:
        _warn(f"show_message failed: {e}")
        return ret


def _show_input(title, message, default_value=""):
    """
    Show a text input dialog. Returns the entered string, or None on cancel.
    In UE 5.7, show_text_input_dialog is the only reliable API but doesn't
    support min size. We use show_object_details_view with a uobject for
    any input that needs more space (multi-line message).
    """
    import unreal as _u

    # For short single-field inputs: show_text_input_dialog
    # For multi-line prompts (model selection, blueprint description): use details view
    use_details = len(message) > 200

    if not use_details and hasattr(_u.EditorDialog, "show_text_input_dialog"):
        try:
            result = _u.EditorDialog.show_text_input_dialog(
                title=title,
                message=message,
                default_value=str(default_value),
            )
            return result
        except Exception as e:
            _warn(f"show_text_input_dialog failed: {e}")

    # show_object_details_view for larger inputs
    try:
        @_u.uclass()
        class _InputObj(_u.Object):
            value = _u.uproperty(str, meta=dict(DisplayName="Your Input", MultiLine=True))

        obj = _u.new_object(_InputObj)
        obj.set_editor_property("value", str(default_value))

        opts = _u.EditorDialogLibraryObjectDetailsViewOptions()
        opts.show_object_name = False
        opts.allow_resizing   = True
        opts.min_width        = 900
        opts.min_height       = 600

        ok_pressed = _u.EditorDialog.show_object_details_view(
            f"{title}\n\n{message}", obj, opts
        )
        if ok_pressed:
            return obj.get_editor_property("value")
        return None
    except Exception as e:
        _warn(f"show_object_details_view failed: {e}")

    _log(f"No dialog available. Use: import mcp_ui; mcp_ui.run('your prompt')")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Panel state
# ─────────────────────────────────────────────────────────────────────────────
_dialog_open = False


def _enqueue_show():
    """Thread-safe: post show() to main queue."""
    _main_queue.put(_open_panel_safe)


def _open_panel_safe():
    """Called from main queue drain — guaranteed on game thread."""
    global _dialog_open
    if _dialog_open:
        _log("Panel already open.")
        return
    _dialog_open = True
    try:
        _do_panel()
    except Exception:
        _err(f"Panel error:\n{traceback.format_exc()}")
    finally:
        _dialog_open = False


# ─────────────────────────────────────────────────────────────────────────────
# Main panel flow
# ─────────────────────────────────────────────────────────────────────────────

def _do_panel():
    """
    Three-step flow: API key → model selection → blueprint description.
    Each step uses a reliable dialog. After generation, panel re-opens via queue.
    """
    import unreal as _u

    # ── STEP 1: API key ───────────────────────────────────────────────────────
    saved_key = _get("api_key", "")
    if not saved_key:
        _log("No API key found — opening setup dialog.")

        # Show info message first
        ret = _show_message(
            "MCP Blueprint Generator — Setup",
            (
                "Welcome to MCP Blueprint Generator!\n\n"
                "You need a FREE OpenRouter API key:\n"
                "  1. Go to  https://openrouter.ai/keys\n"
                "  2. Create account + click Create Key\n"
                "  3. Copy it (starts with sk-or-v1-)\n\n"
                "Click OK to enter your key."
            ),
            _u.AppMsgType.OK_CANCEL,
            _u.AppReturnType.OK,
            _u.AppMsgCategory.INFO,
        )
        if ret != _u.AppReturnType.OK:
            _log("Setup cancelled.  Run: import mcp_ui; mcp_ui.show()")
            return

        key_val = _show_input(
            title="API Key",
            message="Paste your OpenRouter API key (starts with sk-or-v1-):",
            default_value="sk-or-v1-",
        )

        if not key_val or not key_val.strip() or key_val.strip() == "sk-or-v1-":
            _show_message(
                "MCP Blueprint Generator",
                "No API key entered.\n\nConsole fallback:\n  import mcp_ui; mcp_ui.set_key('sk-or-v1-...')\n  mcp_ui.run('your blueprint description')",
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

    model_list = "\n".join(
        f"  {'>' if i == cur_idx else ' '} {i+1:>2}. {label}"
        for i, label in enumerate(MODEL_LABELS)
    )
    model_msg = (
        f"Current model: [{cur_idx+1}] {MODEL_LABELS[cur_idx]}\n\n"
        f"Type a number 1-{len(MODELS)} to change, or press OK to keep current:\n\n"
        f"{model_list}"
    )

    model_input = _show_input(
        title="Select AI Model",
        message=model_msg,
        default_value=str(cur_idx + 1),
    )

    if model_input is None:
        _log("Model selection cancelled.")
        return

    if model_input.strip().isdigit():
        idx = int(model_input.strip()) - 1
        if 0 <= idx < len(MODEL_IDS):
            cur_idx = idx

    model_id    = MODEL_IDS[cur_idx]
    model_label = MODEL_LABELS[cur_idx].split("[")[0].strip()
    _set("model", model_id)
    _log(f"Model: {model_id}")

    # ── STEP 3: Blueprint description ─────────────────────────────────────────
    prompt_msg = (
        f"Model: {model_label}\n\n"
        "Describe the Blueprint you want in plain English.\n\n"
        "Examples:\n"
        "  Create an actor component that allows the player to fly\n"
        "  Create an enemy AI that chases the player and has 100 HP\n"
        "  Create a door that opens when the player walks near it\n"
        "  Create a health pickup that gives 25 HP on overlap\n"
        "  Create a turret that rotates toward the player every tick\n\n"
        "Watch the Output Log for progress. The Blueprint appears in /Game/MCP/"
    )

    prompt_val = _show_input(
        title="Describe Your Blueprint",
        message=prompt_msg,
        default_value="Create an actor component that allows the player to fly",
    )

    if not prompt_val or not prompt_val.strip():
        _log("No prompt entered — cancelled.")
        # Re-open panel (safe because _dialog_open will be False by then)
        _main_queue.put(_open_panel_safe)
        return

    prompt = prompt_val.strip()
    _log("=" * 60)
    _log(f"Prompt : {prompt}")
    _log(f"Model  : {model_id}")
    _log("Generating… Blueprint will appear in /Game/MCP/")
    _log("=" * 60)

    _generate(prompt, saved_key, model_id)


# ─────────────────────────────────────────────────────────────────────────────
# Blueprint generation
# ─────────────────────────────────────────────────────────────────────────────

def _generate(prompt, api_key, model_id):
    """Kick off AI fetch + Blueprint creation on a daemon thread."""

    def _fetch_worker():
        import urllib.request, urllib.error

        try:
            import blueprint_executor
        except Exception as e:
            _err(f"Cannot import blueprint_executor: {e}")
            _main_queue.put(_open_panel_safe)
            return

        try:
            _log(f"Calling {model_id}…")
            payload = json.dumps({
                "model":       model_id,
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

        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode(errors="replace")[:400]
            except Exception:
                pass
            _err(f"HTTP {e.code}: {body}")
            _main_queue.put(_open_panel_safe)
            return
        except Exception:
            _err(f"Network error:\n{traceback.format_exc()}")
            _main_queue.put(_open_panel_safe)
            return

        # Parse response
        try:
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            _err(f"Unexpected API response structure: {e}")
            _main_queue.put(_open_panel_safe)
            return

        # Strip markdown fences if model added them
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(
                line for line in lines
                if not line.startswith("```")
            ).strip()

        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            _err(f"AI returned invalid JSON: {e}\nContent: {content[:300]}")
            _main_queue.put(_open_panel_safe)
            return

        commands = result.get("commands", [])
        bp_name  = result.get("blueprint_name", "BP_Generated")

        _log(f"AI returned {len(commands)} commands for {bp_name}")

        if not commands:
            _err("No commands in AI response. Try rephrasing your prompt.")
            _main_queue.put(_open_panel_safe)
            return

        # Post Blueprint creation to main thread
        def _apply():
            try:
                import unreal as _u
                batch = blueprint_executor.execute_batch(commands)

                succeeded = batch.get("succeeded", 0)
                failed    = batch.get("failed", 0)
                total     = batch.get("total", 0)

                # Log summary
                _log(f"{'OK' if failed == 0 else 'PARTIAL'}: {bp_name} — {succeeded}/{total} commands ok")
                if succeeded > 0:
                    _log(f"Find it: Content Browser → /Game/MCP/{bp_name}")

                # Log any real failures (not warnings)
                for r in batch.get("results", []):
                    if not r.get("success") and not r.get("warning"):
                        _warn(f"  FAIL: {r.get('message','?')}")

                # Try to focus Content Browser on the new asset
                try:
                    _u.EditorAssetLibrary.sync_browser_to_objects(
                        [f"/Game/MCP/{bp_name}"]
                    )
                except Exception:
                    pass

                # NOTE: Do NOT call AssetEditorSubsystem().open_editor_for_assets()
                # from within a Slate tick callback — it crashes UE 5.7 on macOS
                # via FMRUList::AddMRUItem. User can double-click in Content Browser.

                # Show result notification
                if succeeded > 0:
                    msg = (
                        f"Blueprint created: {bp_name}\n"
                        f"Location: /Game/MCP/{bp_name}\n"
                        f"Commands: {succeeded} ok, {failed} failed\n\n"
                        f"Double-click {bp_name} in the Content Browser to open it.\n"
                        f"Check the Output Log for wiring instructions — filter by:\n"
                        f"  MCPBlueprint\n\n"
                        f"Click OK to generate another Blueprint."
                    )
                    _show_message(
                        "Blueprint Created!",
                        msg,
                        _u.AppMsgType.OK, _u.AppReturnType.OK, _u.AppMsgCategory.INFO,
                    )
                else:
                    _show_message(
                        "Blueprint Error",
                        f"Blueprint {bp_name} had errors.\nCheck Output Log for details.\n\nClick OK to try again.",
                        _u.AppMsgType.OK, _u.AppReturnType.OK, _u.AppMsgCategory.WARNING,
                    )

            except Exception:
                _err(f"Blueprint apply failed:\n{traceback.format_exc()}")

            # Re-open panel (safe — _dialog_open is False here since we're
            # called from queue drain, not from within _open_panel_safe)
            _main_queue.put(_open_panel_safe)

        _main_queue.put(_apply)
        _log("Blueprint commands queued for main-thread execution…")

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
        menus    = _u.ToolMenus.get()
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
        _log("'MCP AI' menu registered. Click MCP AI → Generate Blueprint with AI...")

        # After menu registration succeeds, also try to add a toolbar button
        # so the panel is accessible even when the menu bar is crowded
        try:
            toolbar = menus.find_menu("LevelEditor.LevelEditorToolBar.PlayToolBar")
            if not toolbar:
                toolbar = menus.find_menu("LevelEditor.LevelEditorToolBar.AssetsToolBar")
            if toolbar:
                toolbar_entry = _u.new_object(MCPMenuScript)
                toolbar_entry.init_entry(
                    "MCPBlueprintPlugin",
                    toolbar.get_name(),
                    "MCPToolbarSection",
                    "MCPToolbarButton",
                    "🤖 MCP AI",
                    "Generate Blueprint with AI",
                )
                toolbar_entry.register_menu_entry()
                _u.ToolMenus.get().refresh_all_widgets()
                _log("MCP AI toolbar button added.")
        except Exception as e:
            _warn(f"Toolbar button failed (non-critical): {e}")

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
    A) Drains _main_queue on the game thread every frame.
    B) On startup: registers menu, opens startup panel once.
    """
    global _startup_done, _menu_done, _tick_count

    # Always drain queue
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
        _warn("Startup timed out after 900 ticks.")
        _log("Open manually: MCP AI menu, or: import mcp_ui; mcp_ui.show()")
        return

    if not _menu_done:
        _menu_done = _register_menu()
        if not _menu_done:
            return

    # Menu is up — open startup panel on next tick
    _startup_done = True
    _log(f"Editor ready (tick {_tick_count}). Opening MCP Blueprint Generator…")
    _main_queue.put(_open_panel_safe)


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
        _warn("register_slate_post_tick_callback not available — trying sync startup.")
    except Exception as e:
        _warn(f"Slate tick registration failed: {e} — trying sync startup.")

    _register_menu()
    try:
        _open_panel_safe()
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
    _enqueue_show()


def set_key(key: str):
    """Save your OpenRouter API key.
    Usage: mcp_ui.set_key('sk-or-v1-...')
    """
    _set("api_key", key.strip())
    _log(f"API key saved (ends: …{key.strip()[-8:]})")


def set_model(model: str):
    """Select a model by label or ID.
    Usage: mcp_ui.set_model('gpt-4o')
    """
    for label, mid in MODELS:
        if model.lower() in label.lower() or model == mid:
            _set("model", mid)
            _log(f"Model set: {mid}")
            return
    _warn(f"Unknown model '{model}'. Run mcp_ui.list_models() to see options.")


def run(prompt: str, model: str = ""):
    """Generate a Blueprint without the dialog.
    Usage: mcp_ui.run('Create an enemy AI that chases the player')
    """
    if not _IN_UNREAL:
        print("[MCPBlueprint] Not running inside Unreal Engine.")
        return
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
    _log(f"Config: {_CFG}")
    _log(f"API key : {'...' + key[-8:] if key else '(not set)'}")
    _log(f"Model   : {model}")


def start():
    """Called automatically by init_unreal.py when the plugin loads."""
    _log("MCP Blueprint Generator v1.7.1 starting…")

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
        _log("Fallback: import mcp_ui; mcp_ui.set_key('sk-or-v1-...')")

    if _IN_UNREAL:
        _schedule_startup()
