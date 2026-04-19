"""
mcp_ui.py — MCP Blueprint Generator  v1.2.0
UE 5.x · macOS · Python 3.11 — zero external dependencies

Creates a persistent, docked Editor Utility Widget panel that looks and
behaves like a native Unreal editor panel.  The panel has:

  ┌─────────────────────────────────────────────┐
  │  MCP Blueprint Generator              v1.2.0 │
  ├─────────────────────────────────────────────┤
  │  Model  [Claude Sonnet 4.5 ▼            ]   │
  │  Key    [sk-or-v1-…              ] [Set]    │
  ├─────────────────────────────────────────────┤
  │  Prompt:                                     │
  │  ┌──────────────────────────────────────┐   │
  │  │ Create an enemy AI that chases the  │   │
  │  │ player                              │   │
  │  └──────────────────────────────────────┘   │
  │  [Generate Blueprint]                        │
  ├─────────────────────────────────────────────┤
  │  Output Log                                  │
  │  > Calling anthropic/claude-sonnet-4.5…      │
  │  > ✅ BP_Enemy created (8/8 commands)         │
  └─────────────────────────────────────────────┘

Reopen at any time:  import mcp_ui; mcp_ui.show()
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
# Model list
# ─────────────────────────────────────────────────────────────────────────────
MODELS = [
    ("Claude Sonnet 4.5  ★",   "anthropic/claude-sonnet-4.5"),
    ("Claude Opus 4.5",         "anthropic/claude-opus-4.5"),
    ("Claude Opus 4",           "anthropic/claude-opus-4"),
    ("Claude Sonnet 4",         "anthropic/claude-sonnet-4"),
    ("Claude 3.7 Sonnet",       "anthropic/claude-3.7-sonnet"),
    ("Claude 3.7 Thinking",     "anthropic/claude-3.7-sonnet:thinking"),
    ("Claude Haiku 4.5",        "anthropic/claude-haiku-4.5"),
    ("Claude 3.5 Haiku",        "anthropic/claude-3.5-haiku"),
    ("Gemini 2.5 Pro  ★",      "google/gemini-2.5-pro"),
    ("Gemini 2.5 Flash",        "google/gemini-2.5-flash"),
    ("Gemini 3.1 Pro",          "google/gemini-3.1-pro-preview"),
    ("Gemini 3 Flash",          "google/gemini-3-flash-preview"),
    ("Gemini 2.0 Flash",        "google/gemini-2.0-flash-001"),
    ("DeepSeek V3.2  ★",       "deepseek/deepseek-v3.2"),
    ("DeepSeek V3.2 Speciale",  "deepseek/deepseek-v3.2-speciale"),
    ("DeepSeek R1 0528",        "deepseek/deepseek-r1-0528"),
    ("DeepSeek R1",             "deepseek/deepseek-r1"),
    ("DeepSeek R1T2 Chimera",   "tngtech/deepseek-r1t2-chimera"),
    ("GPT-4o",                  "openai/gpt-4o"),
    ("GPT-4o Mini",             "openai/gpt-4o-mini"),
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

QUICK_PROMPTS = [
    "Create an enemy AI that chases the player",
    "Create a door that opens when the player walks near it",
    "Create a health pickup that gives 25 HP on overlap",
    "Create a turret that rotates toward the player every tick",
    "Create a game timer that ends the match after 60 seconds",
    "Create a moving platform that loops back and forth",
    "Create a checkpoint that saves the player's position",
    "Create a collectible coin that disappears on pickup",
]


# ─────────────────────────────────────────────────────────────────────────────
# Core generate  (background thread)
# ─────────────────────────────────────────────────────────────────────────────
def _generate(prompt, api_key, model_id, on_log=None, on_done=None):
    log = on_log or _log

    def _worker():
        import urllib.request, urllib.error
        import blueprint_executor
        try:
            log(f"▶ Calling {model_id}…")
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
            log(f"✔ AI returned {len(commands)} commands → {bp_name}")
            if not commands:
                log("✖ No commands returned — try rephrasing your prompt.")
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
                unreal.call_on_game_thread(_exec); evt.wait(30)
            except (ImportError, AttributeError):
                _exec()
            batch = holder.get("r", {"success": False, "results": []})
            if batch.get("success"):
                log(f"✅ SUCCESS: {bp_name} ({batch.get('succeeded',0)}/{batch.get('total',0)} commands)")
                log(f"   Content Browser → /Game/MCP/{bp_name}")
                try:
                    import unreal
                    unreal.EditorAssetLibrary.sync_browser_to_objects([f"/Game/MCP/{bp_name}"])
                except Exception:
                    pass
                if on_done: on_done(True, bp_name)
            else:
                log(f"⚠ PARTIAL: {batch.get('succeeded',0)} ok, {batch.get('failed',0)} failed")
                for r2 in batch.get("results", []):
                    if not r2.get("success"):
                        log(f"  ✖ {r2.get('message','?')}")
                if on_done: on_done(False, bp_name)
        except urllib.error.HTTPError as e:
            log(f"✖ HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
            if on_done: on_done(False, "")
        except json.JSONDecodeError as e:
            log(f"✖ Bad JSON from AI: {e}")
            if on_done: on_done(False, "")
        except Exception:
            log(f"✖ ERROR: {traceback.format_exc()}")
            if on_done: on_done(False, "")

    threading.Thread(target=_worker, daemon=True, name="MCPGen").start()


# ─────────────────────────────────────────────────────────────────────────────
# PySide2 / PySide6  floating window  (best experience when available)
# ─────────────────────────────────────────────────────────────────────────────
def _try_qt():
    """Try to build a Qt floating window. Returns True on success."""
    try:
        try:
            from PySide2.QtWidgets import (
                QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                QLabel, QComboBox, QLineEdit, QPushButton,
                QTextEdit, QSizePolicy, QFrame,
            )
            from PySide2.QtCore import Qt, QThread, Signal, QObject
            from PySide2.QtGui import QFont, QColor, QPalette
        except ImportError:
            from PySide6.QtWidgets import (
                QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                QLabel, QComboBox, QLineEdit, QPushButton,
                QTextEdit, QSizePolicy, QFrame,
            )
            from PySide6.QtCore import Qt, QThread, Signal, QObject
            from PySide6.QtGui import QFont, QColor, QPalette

        app = QApplication.instance() or QApplication([])

        win = QWidget()
        win.setWindowTitle("MCP Blueprint Generator  v1.2.0")
        win.setMinimumWidth(540)
        win.setMinimumHeight(600)

        root = QVBoxLayout(win)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Title
        title = QLabel("🤖  MCP Blueprint Generator")
        title.setFont(QFont("", 14, QFont.Bold))
        root.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); root.addWidget(sep)

        # Model row
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        model_cb = QComboBox()
        model_cb.addItems(MODEL_LABELS)
        saved_model = _get("model", DEFAULT_MODEL)
        try:
            model_cb.setCurrentIndex(MODEL_IDS.index(saved_model))
        except ValueError:
            model_cb.setCurrentIndex(0)
        model_row.addWidget(model_cb, 1)
        root.addLayout(model_row)

        # API key row
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("API Key:"))
        key_edit = QLineEdit(_get("api_key", ""))
        key_edit.setPlaceholderText("sk-or-v1-…  (get free key at openrouter.ai/keys)")
        key_edit.setEchoMode(QLineEdit.Password)
        key_row.addWidget(key_edit, 1)
        save_btn = QPushButton("Save Key")
        key_row.addWidget(save_btn)
        root.addLayout(key_row)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); root.addWidget(sep2)

        # Prompt
        root.addWidget(QLabel("Describe the Blueprint you want:"))
        prompt_edit = QTextEdit()
        prompt_edit.setPlaceholderText(
            "Examples:\n"
            "  Create an enemy AI that chases the player\n"
            "  Create a door that opens when the player walks near it\n"
            "  Create a health pickup that gives 25 HP on overlap\n"
            "  Create a turret that rotates toward the player every tick"
        )
        prompt_edit.setMinimumHeight(120)
        root.addWidget(prompt_edit)

        # Quick-prompt buttons
        quick_label = QLabel("Quick prompts:")
        root.addWidget(quick_label)
        quick_grid1 = QHBoxLayout()
        quick_grid2 = QHBoxLayout()
        for i, qp in enumerate(QUICK_PROMPTS[:4]):
            btn = QPushButton(qp[:35] + ("…" if len(qp) > 35 else ""))
            btn.setToolTip(qp)
            btn.clicked.connect(lambda checked, t=qp: prompt_edit.setPlainText(t))
            quick_grid1.addWidget(btn)
        for i, qp in enumerate(QUICK_PROMPTS[4:]):
            btn = QPushButton(qp[:35] + ("…" if len(qp) > 35 else ""))
            btn.setToolTip(qp)
            btn.clicked.connect(lambda checked, t=qp: prompt_edit.setPlainText(t))
            quick_grid2.addWidget(btn)
        root.addLayout(quick_grid1)
        root.addLayout(quick_grid2)

        # Generate button
        gen_btn = QPushButton("⚡  Generate Blueprint")
        gen_btn.setMinimumHeight(40)
        gen_btn.setFont(QFont("", 11, QFont.Bold))
        gen_btn.setStyleSheet("QPushButton { background-color: #2563eb; color: white; border-radius: 6px; }"
                              "QPushButton:hover { background-color: #1d4ed8; }"
                              "QPushButton:disabled { background-color: #6b7280; }")
        root.addWidget(gen_btn)

        sep3 = QFrame(); sep3.setFrameShape(QFrame.HLine); root.addWidget(sep3)

        # Output log
        root.addWidget(QLabel("Output Log:"))
        log_edit = QTextEdit()
        log_edit.setReadOnly(True)
        log_edit.setFont(QFont("Menlo", 10))
        log_edit.setMinimumHeight(150)
        log_edit.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        root.addWidget(log_edit)

        # Wire up
        def _append_log(msg):
            log_edit.append(msg)

        def _on_save_key():
            k = key_edit.text().strip()
            if k:
                _set("api_key", k)
                _append_log(f"✔ API key saved (…{k[-8:]})")
            else:
                _append_log("✖ Key is empty — nothing saved.")

        save_btn.clicked.connect(_on_save_key)

        def _on_generate():
            api_key  = key_edit.text().strip() or _get("api_key", "")
            prompt   = prompt_edit.toPlainText().strip()
            model_id = MODEL_IDS[model_cb.currentIndex()]

            if not api_key:
                _append_log("✖ No API key — enter it above and press Save Key")
                return
            if not prompt:
                _append_log("✖ Prompt is empty — describe the Blueprint you want")
                return

            _set("model", model_id)
            _set("api_key", api_key)

            gen_btn.setEnabled(False)
            gen_btn.setText("Generating…")
            _append_log("━" * 50)
            _append_log(f"Prompt: {prompt}")
            _append_log(f"Model:  {model_id}")

            def _done(ok, bp_name):
                gen_btn.setEnabled(True)
                gen_btn.setText("⚡  Generate Blueprint")

            _generate(
                prompt, api_key, model_id,
                on_log=_append_log,
                on_done=_done,
            )

        gen_btn.clicked.connect(_on_generate)

        win.show()
        win.raise_()
        win.activateWindow()

        # Keep window alive
        import mcp_ui as _self
        _self._qt_window = win

        _log("✔ MCP Blueprint Generator panel opened (Qt)")
        return True

    except Exception as e:
        _warn(f"Qt UI not available: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Toolbar button  (works in UE 5.x without any external library)
# ─────────────────────────────────────────────────────────────────────────────
_toolbar_registered = False

def _register_toolbar():
    """Add 'MCP AI' button to the Level Editor toolbar."""
    global _toolbar_registered
    if _toolbar_registered:
        return True

    try:
        import unreal

        menus = unreal.ToolMenus.get()
        toolbar = None
        for name in [
            "LevelEditor.LevelEditorToolBar.PlayToolBar",
            "LevelEditor.LevelEditorToolBar.AssetsToolBar",
            "LevelEditor.LevelEditorToolBar",
        ]:
            toolbar = menus.extend_menu(name)
            if toolbar is not None:
                break

        if toolbar is None:
            _warn("Could not find a toolbar to add the MCP AI button")
            return False

        # Sub-class ToolMenuEntryScript to wire a Python callback
        class _MCPBtn(unreal.ToolMenuEntryScript):
            def execute(self, context):
                _open_dialog()

        data           = unreal.ToolMenuEntryScriptData()
        data.name      = "MCPBlueprintOpen"
        data.label     = unreal.Text("MCP AI")
        data.tool_tip  = unreal.Text(
            "MCP Blueprint Generator — describe a Blueprint in plain English and let AI build it"
        )

        btn      = _MCPBtn()
        btn.data = data

        toolbar.find_or_add_section("MCPSection")
        toolbar.add_menu_entry_object(btn)
        menus.refresh_all_widgets()

        _toolbar_registered = True
        _log("✔ [MCP AI] button added to the Level Editor toolbar")
        return True

    except Exception as e:
        _warn(f"Toolbar registration failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Dialog flow  (Unreal native — no external libraries)
# ─────────────────────────────────────────────────────────────────────────────
def _open_dialog():
    """
    Opens the MCP generator using Unreal's built-in dialog system.
    This is the fallback when Qt is unavailable.
    Shows three quick dialogs (key once, model, prompt) then generates.
    """
    try:
        import unreal
    except ImportError:
        _log("Not running inside Unreal Engine.")
        return

    # ── API key (only if not saved) ───────────────────────────────────────
    saved_key = _get("api_key", "")
    if not saved_key:
        result = unreal.EditorDialog.show_text_input_dialog(
            title="MCP Blueprint Generator — Enter API Key",
            message=(
                "Enter your FREE OpenRouter API key.\n\n"
                "1. Go to  openrouter.ai/keys  and sign up (free)\n"
                "2. Copy your key  (starts with sk-or-v1-)\n"
                "3. Paste it below — it will be saved automatically\n\n"
                "You only need to do this once."
            ),
            default_value="",
        )
        if not result or not result.strip():
            unreal.EditorDialog.show_message(
                "MCP Blueprint Generator",
                "No API key entered.\n\nGet a free key at openrouter.ai/keys",
                unreal.AppMsgType.OK,
            )
            return
        saved_key = result.strip()
        _set("api_key", saved_key)
        _log(f"✔ API key saved (…{saved_key[-8:]})")

    # ── Model selection ───────────────────────────────────────────────────
    saved_model = _get("model", DEFAULT_MODEL)
    try:
        cur_idx = MODEL_IDS.index(saved_model)
    except ValueError:
        cur_idx = 0

    model_list = "\n".join(
        f"  {i+1:>2}.  {label}" for i, label in enumerate(MODEL_LABELS)
    )
    model_result = unreal.EditorDialog.show_text_input_dialog(
        title="MCP Blueprint Generator — Choose AI Model",
        message=(
            f"Current model: [{cur_idx+1}] {MODEL_LABELS[cur_idx]}\n\n"
            f"Type a number to switch, or press OK to keep the current model:\n\n"
            f"{model_list}"
        ),
        default_value=str(cur_idx + 1),
    )

    if model_result and model_result.strip().isdigit():
        idx = int(model_result.strip()) - 1
        if 0 <= idx < len(MODEL_IDS):
            cur_idx = idx
    model_id    = MODEL_IDS[cur_idx]
    model_label = MODEL_LABELS[cur_idx]
    _set("model", model_id)

    # ── Prompt ────────────────────────────────────────────────────────────
    prompt_result = unreal.EditorDialog.show_text_input_dialog(
        title=f"MCP Blueprint Generator — [{model_label.strip()}]",
        message=(
            "Describe the Blueprint you want in plain English:\n\n"
            "Examples:\n"
            "  Create an enemy AI that chases the player\n"
            "  Create a door that opens when the player walks near it\n"
            "  Create a health pickup that gives 25 HP on overlap\n"
            "  Create a turret that rotates toward the player every tick\n"
            "  Create a game timer that ends the match after 60 seconds\n"
            "  Create a moving platform that loops back and forth\n"
            "  Create a respawn point the player returns to on death\n"
            "  Create a collectible coin that disappears on pickup"
        ),
        default_value="Create an enemy AI that chases the player",
    )

    if not prompt_result or not prompt_result.strip():
        return

    prompt = prompt_result.strip()
    _log("━" * 60)
    _log(f"Prompt : {prompt}")
    _log(f"Model  : {model_id}")
    _log("Generating… results appear below in the Output Log.")
    _log("━" * 60)

    _generate(prompt, saved_key, model_id)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def show():
    """Open or re-open the MCP Blueprint Generator panel."""
    # Prefer Qt window if already open
    win = globals().get("_qt_window")
    if win is not None:
        try:
            win.show(); win.raise_(); win.activateWindow(); return
        except Exception:
            pass

    # Try to open Qt window
    if _try_qt():
        return

    # Fallback: Unreal dialog flow
    _open_dialog()


def start():
    """Called automatically by init_unreal.py when the plugin loads."""
    _log("MCP Blueprint Generator v1.2.0 loading…")

    # 1. Try Qt floating window (best experience)
    qt_ok = _try_qt()

    # 2. Always register the toolbar button (works regardless of Qt)
    try:
        tb_ok = _register_toolbar()
    except Exception:
        tb_ok = False

    # 3. Log status
    saved_key = _get("api_key", "")
    if saved_key:
        _log(f"✔ API key: …{saved_key[-8:]} (saved)")
    else:
        _log("⚡ No API key yet — get one free at openrouter.ai/keys")

    if qt_ok:
        _log("✔ Generator window is open — use it to create Blueprints!")
    elif tb_ok:
        _log("✔ Click the [MCP AI] button in the Level Editor toolbar to open the generator")
    else:
        _log("Toolbar unavailable — type in the Output Log Python console:")
        _log("  import mcp_ui; mcp_ui.show()")
