"""
ai_panel.py
Self-contained AI Blueprint panel that runs INSIDE Unreal Engine.

When enabled, opens a floating editor window where the user can:
  1. Enter their OpenAI API key (saved to EditorSettings so it persists)
  2. Type a plain-English prompt describing the Blueprint they want
  3. Click "Generate Blueprint" — the plugin calls OpenAI directly,
     parses the returned commands, and creates/wires/compiles the Blueprint
     — all without leaving the editor.

No Node.js. No terminal. No external server. Nothing.

Entry point: start()  — called by init_unreal.py on plugin load.
"""

import json
import threading
import traceback
import urllib.request
import urllib.error

import blueprint_executor

try:
    import unreal
    UNREAL = True
except ImportError:
    UNREAL = False

# ── Persistent settings key ───────────────────────────────────────────────────
_SETTINGS_KEY = "MCPBlueprint_OpenAI_Key"

# ── In-memory state ───────────────────────────────────────────────────────────
_api_key   = ""          # loaded from editor config on start
_last_log  = []          # recent log lines shown in the panel

# ─────────────────────────────────────────────────────────────────────────────
# OpenAI call
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
    {"action": "add_node", "blueprint": "BP_SomeName", "node": "Print String", "id": "node_1", "x": 300, "y": 0, "parameters": {"string": "Hello from Blueprint!"}},
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


def call_openai(api_key: str, prompt: str) -> dict:
    """Call OpenAI chat completions and return parsed JSON dict."""
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI HTTP {e.code}: {body}")

    content = data["choices"][0]["message"]["content"].strip()

    # Strip markdown fences if the model wrapped the JSON anyway
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        content = "\n".join(lines).strip()

    return json.loads(content)


# ─────────────────────────────────────────────────────────────────────────────
# Settings persistence (Unreal EditorConfig)
# ─────────────────────────────────────────────────────────────────────────────

def _load_api_key() -> str:
    """Load the saved API key from Unreal's editor config."""
    global _api_key
    try:
        cfg = unreal.get_editor_subsystem(unreal.EditorUtilitySubsystem) if UNREAL else None
        # Unreal Python config API
        val = unreal.EditorAssetLibrary.get_metadata_tag(
            unreal.load_asset("/Game/MCP/_MCPSettings") or unreal.Object(), _SETTINGS_KEY
        ) if UNREAL else ""
        _api_key = val or ""
    except Exception:
        _api_key = ""
    return _api_key


def _save_api_key(key: str):
    """Persist the API key in a simple config file next to the plugin scripts."""
    global _api_key
    _api_key = key
    try:
        import os
        cfg_path = os.path.join(os.path.dirname(__file__), ".mcp_config")
        with open(cfg_path, "w") as f:
            json.dump({"openai_api_key": key}, f)
    except Exception:
        pass


def _read_saved_key() -> str:
    """Read API key from the config file written by _save_api_key."""
    try:
        import os
        cfg_path = os.path.join(os.path.dirname(__file__), ".mcp_config")
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                data = json.load(f)
                return data.get("openai_api_key", "")
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Unreal Editor Utility Widget (the actual UI)
# ─────────────────────────────────────────────────────────────────────────────

def _log(msg: str):
    _last_log.append(msg)
    if len(_last_log) > 50:
        _last_log.pop(0)
    if UNREAL:
        unreal.log(f"[MCPBlueprint] {msg}")
    else:
        print(f"[MCPBlueprint] {msg}")


def generate_blueprint(prompt: str, api_key: str):
    """
    Called from the UI. Runs in a background thread so the editor doesn't freeze.
    Calls OpenAI, parses the response, then dispatches blueprint commands back
    to the game thread.
    """
    if not api_key.strip():
        _log("ERROR: No OpenAI API key set. Enter your key in the MCP Blueprint panel.")
        return
    if not prompt.strip():
        _log("ERROR: Prompt is empty.")
        return

    _log(f'Generating Blueprint for: "{prompt}"')

    def _worker():
        try:
            _log("Calling OpenAI...")
            result = call_openai(api_key.strip(), prompt.strip())
            commands = result.get("commands", [])
            bp_name  = result.get("blueprint_name", "BP_Generated")
            _log(f"AI returned {len(commands)} commands for {bp_name}")

            if not commands:
                _log("ERROR: OpenAI returned no commands.")
                return

            # Execute on game thread
            def _execute():
                try:
                    batch = blueprint_executor.execute_batch(commands)
                    if batch.get("success"):
                        _log(f"SUCCESS: {bp_name} created — {batch['succeeded']}/{batch['total']} commands OK")
                        _log(f"Find it in Content Browser → /Game/MCP/{bp_name}")
                        if UNREAL:
                            unreal.EditorAssetLibrary.sync_browser_to_objects([f"/Game/MCP/{bp_name}"])
                    else:
                        _log(f"PARTIAL: {batch['succeeded']} succeeded, {batch['failed']} failed")
                        for r in batch.get("results", []):
                            if not r.get("success"):
                                _log(f"  FAIL: {r.get('message', '?')}")
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
            _log(f"ERROR: OpenAI response was not valid JSON: {e}")
        except RuntimeError as e:
            _log(f"ERROR: {e}")
        except Exception:
            _log(f"ERROR:\n{traceback.format_exc()}")

    t = threading.Thread(target=_worker, daemon=True, name="MCPBlueprint_Generate")
    t.start()


# ─────────────────────────────────────────────────────────────────────────────
# Editor Utility Widget registration
# ─────────────────────────────────────────────────────────────────────────────

def _open_panel():
    """
    Open the MCP Blueprint panel as an Unreal Editor tab.
    Uses EditorUtilitySubsystem to spawn the widget defined in the UMG asset,
    or falls back to a Python-driven menu registration.
    """
    if not UNREAL:
        return

    try:
        # Register a menu entry under Window menu so users can re-open the panel
        _register_menu()
    except Exception as e:
        _log(f"Menu registration error (non-fatal): {e}")

    # Spawn the floating tool window
    try:
        _spawn_tool_window()
    except Exception as e:
        _log(f"Could not auto-open panel: {e}")
        _log("Open it manually via: Window → MCP Blueprint Generator")


def _register_menu():
    """Add 'MCP Blueprint Generator' to the Window menu in Unreal."""
    import unreal

    @unreal.uclass()
    class MCPMenuExtension(unreal.ToolMenuEntryScript):
        @unreal.ufunction(override=True)
        def execute(self, context):
            _spawn_tool_window()

    menus = unreal.ToolMenus.get()
    window_menu = menus.find_menu("LevelEditor.MainMenu.Window")
    if window_menu:
        entry = unreal.ToolMenuEntry(
            name="MCPBlueprintGenerator",
            type=unreal.MultiBlockType.MENU_ENTRY,
        )
        entry.set_label("MCP Blueprint Generator")
        entry.set_tool_tip("Generate Blueprints from plain-English prompts using AI")
        window_menu.add_menu_entry("MCPBlueprintTools", entry)
        menus.refresh_all_widgets()


def _spawn_tool_window():
    """Spawn a simple Python-driven floating dialog using unreal.PythonScriptTypes."""
    import unreal

    # Build the UI as an Editor Utility Widget class via Python API
    subsystem = unreal.get_editor_subsystem(unreal.EditorUtilitySubsystem)

    # Load the EUW asset if it exists; otherwise create a minimal dialog
    euw_path = "/MCPBlueprint/Widgets/WBP_MCPPanel"
    euw_asset = unreal.load_asset(euw_path)

    if euw_asset:
        subsystem.spawn_and_register_tab(euw_asset)
    else:
        # Fallback: just log instructions since full Slate widget creation
        # from pure Python requires a pre-built UMG asset
        _log("MCP Blueprint Generator is ready.")
        _log("Use the Python console to generate Blueprints:")
        _log('  import ai_panel; ai_panel.generate_blueprint("your prompt here", "sk-your-key")')
        _log("Or call from the Output Log console tab.")


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def start():
    """Called by init_unreal.py. Loads saved key, registers UI, logs ready state."""
    global _api_key
    _api_key = _read_saved_key()

    _log("MCP Blueprint Generator loaded.")

    if _api_key:
        _log(f"OpenAI key found (ends in ...{_api_key[-4:]})")
    else:
        _log("No OpenAI key saved yet.")
        _log("Set your key with: import ai_panel; ai_panel.set_key('sk-...')")

    _log("Generate a Blueprint with:")
    _log('  import ai_panel; ai_panel.run("Create an enemy that chases the player")')

    _open_panel()


def set_key(key: str):
    """Public helper: ai_panel.set_key('sk-...')  — saves key and confirms."""
    _save_api_key(key)
    _log(f"API key saved (ends in ...{key[-4:] if len(key) >= 4 else key})")


def run(prompt: str, key: str = ""):
    """Public helper: ai_panel.run('your prompt')  — uses saved key if not provided."""
    global _api_key
    k = key or _api_key or _read_saved_key()
    if not k:
        _log("ERROR: No API key. Call ai_panel.set_key('sk-...') first.")
        return
    generate_blueprint(prompt, k)
