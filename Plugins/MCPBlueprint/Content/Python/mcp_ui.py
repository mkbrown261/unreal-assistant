"""
mcp_ui.py  —  MCP Blueprint Generator UI
Tries three strategies in order:
  1. PySide2 floating Qt window (UE5.0–5.3 standard)
  2. PySide6 floating Qt window (UE5.4+)
  3. Unreal EditorDialog / built-in UI fallback
  4. Interactive console menu (always works)

Reopen any time:
    import mcp_ui; mcp_ui.show()
"""

import json
import os
import threading
import traceback

# ─────────────────────────────────────────────────────────────────────────────
# Config persistence
# ─────────────────────────────────────────────────────────────────────────────
_CFG_PATH = os.path.join(os.path.dirname(__file__), ".mcp_config")

def _load_cfg():
    try:
        if os.path.exists(_CFG_PATH):
            with open(_CFG_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_cfg(data):
    try:
        with open(_CFG_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def _cfg_get(key, default=""):
    return _load_cfg().get(key, default)

def _cfg_set(key, value):
    cfg = _load_cfg()
    cfg[key] = value
    _save_cfg(cfg)

# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────
MODELS = [
    ("── Claude ──────────────────────────",  None),
    ("Claude Sonnet 4.5  ★  (recommended)",  "anthropic/claude-sonnet-4.5"),
    ("Claude Opus 4.5  (most capable)",       "anthropic/claude-opus-4.5"),
    ("Claude Opus 4",                          "anthropic/claude-opus-4"),
    ("Claude Sonnet 4",                        "anthropic/claude-sonnet-4"),
    ("Claude 3.7 Sonnet",                      "anthropic/claude-3.7-sonnet"),
    ("Claude 3.7 Sonnet (Thinking)",           "anthropic/claude-3.7-sonnet:thinking"),
    ("Claude Haiku 4.5  (fastest)",            "anthropic/claude-haiku-4.5"),
    ("Claude 3.5 Haiku",                       "anthropic/claude-3.5-haiku"),
    ("── Gemini ──────────────────────────",  None),
    ("Gemini 2.5 Pro  ★",                     "google/gemini-2.5-pro"),
    ("Gemini 2.5 Flash",                       "google/gemini-2.5-flash"),
    ("Gemini 2.5 Flash Lite",                  "google/gemini-2.5-flash-lite"),
    ("Gemini 3.1 Pro Preview",                 "google/gemini-3.1-pro-preview"),
    ("Gemini 3 Flash Preview",                 "google/gemini-3-flash-preview"),
    ("Gemini 2.0 Flash",                       "google/gemini-2.0-flash-001"),
    ("── DeepSeek ────────────────────────",  None),
    ("DeepSeek V3.2  ★",                      "deepseek/deepseek-v3.2"),
    ("DeepSeek V3.2 Speciale",                 "deepseek/deepseek-v3.2-speciale"),
    ("DeepSeek R1 0528  (reasoning)",          "deepseek/deepseek-r1-0528"),
    ("DeepSeek R1  (reasoning)",               "deepseek/deepseek-r1"),
    ("DeepSeek R1T2 Chimera",                  "tngtech/deepseek-r1t2-chimera"),
    ("── GPT-4o ──────────────────────────",  None),
    ("GPT-4o",                                 "openai/gpt-4o"),
    ("GPT-4o Mini  (most affordable)",         "openai/gpt-4o-mini"),
]

# Flat list for menu navigation
SELECTABLE = [(label, mid) for label, mid in MODELS if mid is not None]
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
def _log(msg):
    try:
        import unreal
        unreal.log(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] {msg}")

def _log_warn(msg):
    try:
        import unreal
        unreal.log_warning(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] WARNING: {msg}")

def _log_error(msg):
    try:
        import unreal
        unreal.log_error(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] ERROR: {msg}")

# ─────────────────────────────────────────────────────────────────────────────
# OpenRouter + Blueprint execution (shared)
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are an Unreal Engine 5 Blueprint generation assistant. "
    "The user describes game logic in plain English. "
    "Respond with ONLY a valid JSON object — no explanation, no markdown, no code fences.\n\n"
    'JSON: {"blueprint_name":"BP_Name","commands":['
    '{"action":"create_blueprint","name":"BP_Name","parent_class":"Actor"},'
    '{"action":"add_variable","blueprint":"BP_Name","variable_name":"Health","variable_type":"Float","default_value":100},'
    '{"action":"add_node","blueprint":"BP_Name","node":"Event BeginPlay","id":"node_0","x":0,"y":0},'
    '{"action":"add_node","blueprint":"BP_Name","node":"Print String","id":"node_1","x":300,"y":0},'
    '{"action":"connect_nodes","blueprint":"BP_Name","from_node":"node_0","from_pin":"Then","to_node":"node_1","to_pin":"Execute"},'
    '{"action":"compile_blueprint","name":"BP_Name"}]}\n\n'
    "Rules: blueprint_name starts with BP_ PascalCase. "
    "parent_class: Actor/Character/Pawn/GameModeBase/PlayerController/ActorComponent. "
    "variable_type: Boolean/Integer/Float/String/Vector/Rotator/Transform. "
    "node types: Event BeginPlay, Event Tick, Event ActorBeginOverlap, Branch, Print String, "
    "Delay, Get Player Pawn, Get Actor Location, Set Actor Location, Destroy Actor, AI Move To, "
    "Timeline, Cast To Character. Every add_node needs unique id. compile_blueprint must be last. "
    "Return ONLY the JSON."
)

def _call_openrouter(api_key, model_id, prompt):
    import urllib.request, urllib.error
    payload = json.dumps({
        "model": model_id,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ]
    }).encode("utf-8")
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
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = "\n".join(l for l in content.split("\n") if not l.startswith("```")).strip()
    return json.loads(content)


def _run_generate(prompt, api_key, model_id, on_log=None, on_done=None):
    """Background thread: call OpenRouter, execute Blueprint commands."""
    log = on_log or _log

    def _worker():
        import urllib.error
        try:
            log(f"⏳ Calling OpenRouter ({model_id})…")
            result   = _call_openrouter(api_key, model_id, prompt)
            commands = result.get("commands", [])
            bp_name  = result.get("blueprint_name", "BP_Generated")
            log(f"✅ AI returned {len(commands)} commands → {bp_name}")

            if not commands:
                log("❌ No commands returned. Try rephrasing.")
                if on_done: on_done(False, "")
                return

            holder     = {}
            done_event = threading.Event()

            def _execute():
                import blueprint_executor
                try:
                    holder["r"] = blueprint_executor.execute_batch(commands)
                except Exception:
                    holder["r"] = {"success": False, "results": [], "error": traceback.format_exc()}
                finally:
                    done_event.set()

            try:
                import unreal
                unreal.call_on_game_thread(_execute)
                done_event.wait(timeout=30)
            except (ImportError, AttributeError):
                _execute()

            batch = holder.get("r", {"success": False, "results": []})
            if batch.get("success"):
                ok  = batch.get("succeeded", 0)
                tot = batch.get("total", 0)
                log(f"🎉 {bp_name} created — {ok}/{tot} commands OK")
                log(f"📂 Content Browser → /Game/MCP/{bp_name}")
                try:
                    import unreal
                    unreal.EditorAssetLibrary.sync_browser_to_objects([f"/Game/MCP/{bp_name}"])
                except Exception:
                    pass
                if on_done: on_done(True, bp_name)
            else:
                ok  = batch.get("succeeded", 0)
                bad = batch.get("failed", 0)
                log(f"⚠️ Partial: {ok} ok, {bad} failed")
                for r in batch.get("results", []):
                    if not r.get("success"):
                        log(f"  ✗ {r.get('message','?')}")
                if on_done: on_done(False, bp_name)

        except Exception as e:
            log(f"❌ Error: {e}")
            if on_done: on_done(False, "")

    threading.Thread(target=_worker, daemon=True, name="MCPGen").start()


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 1 & 2 — PySide2 / PySide6 Qt window
# ─────────────────────────────────────────────────────────────────────────────
_qt_window = None

def _try_qt():
    """Try to open a PySide2 or PySide6 floating window. Returns True if opened."""
    global _qt_window

    QtWidgets = QtCore = QtGui = None
    for mod in ("PySide2", "PySide6"):
        try:
            import importlib
            qw = importlib.import_module(f"{mod}.QtWidgets")
            qc = importlib.import_module(f"{mod}.QtCore")
            qg = importlib.import_module(f"{mod}.QtGui")
            QtWidgets, QtCore, QtGui = qw, qc, qg
            break
        except ImportError:
            continue

    if QtWidgets is None:
        return False

    app = QtWidgets.QApplication.instance()
    if app is None:
        try:
            app = QtWidgets.QApplication([])
        except Exception:
            return False

    if _qt_window is not None and _qt_window.isVisible():
        _qt_window.raise_()
        _qt_window.activateWindow()
        return True

    try:
        win = _build_qt_window(QtWidgets, QtCore, QtGui)
        if win is None:
            return False
        _qt_window = win
        win.show()
        win.raise_()
        win.activateWindow()
        return True
    except Exception as e:
        _log_warn(f"Qt window failed to open: {e}")
        return False


def _build_qt_window(QtWidgets, QtCore, QtGui):
    Qt = QtCore.Qt

    STYLE = """
    QWidget { font-family:'Segoe UI',Arial,sans-serif; font-size:13px; color:#e2e8f0; background:transparent; }
    QWidget#modelBar { background:#0d0d1f; border-bottom:1px solid #1e2d45; }
    QComboBox#modelCombo {
        background:#1a2744; border:1.5px solid #2d3f60; border-radius:20px;
        padding:6px 36px 6px 14px; color:#c4b5fd; font-size:13px; font-weight:600; min-width:260px;
    }
    QComboBox#modelCombo:hover { border-color:#a855f7; }
    QComboBox#modelCombo::drop-down { border:none; width:28px; }
    QComboBox#modelCombo QAbstractItemView {
        background:#111827; border:1.5px solid #2d3f60; color:#e2e8f0;
        selection-background-color:#2d1d4e; outline:none; padding:4px;
    }
    QLineEdit#keyInput {
        background:#111827; border:1.5px solid #1e2d45; border-radius:10px;
        padding:9px 14px; color:#e2e8f0; font-size:13px;
    }
    QLineEdit#keyInput:focus { border-color:#a855f7; }
    QTextEdit#promptInput {
        background:#111827; border:1.5px solid #1e2d45; border-radius:10px;
        padding:10px 14px; color:#e2e8f0; font-size:13px;
    }
    QTextEdit#promptInput:focus { border-color:#a855f7; }
    QPushButton#genBtn {
        background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #9333ea,stop:1 #4f46e5);
        border:none; border-radius:10px; color:white; font-size:14px; font-weight:700; padding:12px 24px;
    }
    QPushButton#genBtn:hover { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7e22ce,stop:1 #3730a3); }
    QPushButton#genBtn:disabled { background:#1e293b; color:#4b5563; }
    QPushButton#ghostBtn {
        background:transparent; border:1px solid #1e2d45; border-radius:8px;
        color:#64748b; font-size:11px; padding:5px 12px;
    }
    QPushButton#ghostBtn:hover { border-color:#4b5563; color:#94a3b8; }
    QTextEdit#logView {
        background:#080d17; border:1.5px solid #1e2d45; border-radius:10px;
        font-family:'Consolas','Courier New',monospace; font-size:11px; color:#94a3b8; padding:10px;
    }
    QScrollBar:vertical { background:#111827; width:6px; border-radius:3px; }
    QScrollBar::handle:vertical { background:#2d3f60; border-radius:3px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
    """

    class MCPWindow(QtWidgets.QWidget):
        _log_sig  = QtCore.Signal(str, str)
        _done_sig = QtCore.Signal(bool, str)

        def __init__(self):
            super().__init__()
            self.setWindowTitle("MCP Blueprint Generator  v1.2.0")
            self.setMinimumSize(540, 740)
            self.resize(560, 780)
            self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_DeleteOnClose, False)
            self.setStyleSheet(STYLE)
            pal = self.palette()
            pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#0b0f1a"))
            self.setPalette(pal)
            self.setAutoFillBackground(True)
            self._build_ui()
            self._load_settings()
            self._log_sig.connect(self._append_log)
            self._done_sig.connect(self._on_done)

        def _lbl(self, text):
            l = QtWidgets.QLabel(text)
            l.setStyleSheet("color:#475569;font-size:10px;font-weight:700;letter-spacing:.1em;")
            return l

        def _build_ui(self):
            root = QtWidgets.QVBoxLayout(self)
            root.setSpacing(0)
            root.setContentsMargins(0, 0, 0, 0)

            # ── Model bar (always at top) ─────────────────────────────────────
            bar = QtWidgets.QWidget(); bar.setObjectName("modelBar"); bar.setFixedHeight(58)
            bl  = QtWidgets.QHBoxLayout(bar); bl.setContentsMargins(18, 0, 18, 0)
            lbl = QtWidgets.QLabel("MODEL")
            lbl.setStyleSheet("color:#64748b;font-size:11px;font-weight:700;letter-spacing:.08em;")
            bl.addWidget(lbl); bl.addSpacing(12)

            self.model_combo = QtWidgets.QComboBox()
            self.model_combo.setObjectName("modelCombo")
            self.model_combo.setFixedHeight(36)
            for label, mid in MODELS:
                if mid is None:
                    self.model_combo.addItem(label)
                    idx  = self.model_combo.count() - 1
                    item = self.model_combo.model().item(idx)
                    item.setEnabled(False)
                    item.setForeground(QtGui.QColor("#334155"))
                else:
                    self.model_combo.addItem(label, mid)
            self.model_combo.currentIndexChanged.connect(self._save_settings)
            bl.addWidget(self.model_combo); bl.addStretch()
            root.addWidget(bar)

            # ── Body ──────────────────────────────────────────────────────────
            body = QtWidgets.QWidget(); body.setStyleSheet("background:#0b0f1a;")
            blay = QtWidgets.QVBoxLayout(body); blay.setContentsMargins(20,20,20,20); blay.setSpacing(14)

            # API key
            blay.addWidget(self._lbl("OPENROUTER API KEY"))
            kr = QtWidgets.QHBoxLayout(); kr.setSpacing(8)
            self.key_input = QtWidgets.QLineEdit()
            self.key_input.setObjectName("keyInput")
            self.key_input.setPlaceholderText("sk-or-v1-…  paste your key here")
            self.key_input.setEchoMode(QtWidgets.QLineEdit.Password)
            self.key_input.textChanged.connect(self._save_settings)
            kr.addWidget(self.key_input)
            self._show_btn = QtWidgets.QPushButton("Show")
            self._show_btn.setObjectName("ghostBtn"); self._show_btn.setFixedWidth(56)
            self._show_btn.clicked.connect(self._toggle_key)
            kr.addWidget(self._show_btn); blay.addLayout(kr)

            link = QtWidgets.QLabel('<a href="https://openrouter.ai/keys" style="color:#a855f7;text-decoration:none;">→ Get a free key at openrouter.ai/keys</a>')
            link.setOpenExternalLinks(True)
            link.setStyleSheet("font-size:11px;color:#64748b;")
            blay.addWidget(link)

            div = QtWidgets.QFrame(); div.setFrameShape(QtWidgets.QFrame.HLine)
            div.setStyleSheet("color:#1e2d45;"); blay.addWidget(div)

            # Prompt
            blay.addWidget(self._lbl("DESCRIBE THE BLUEPRINT YOU WANT"))
            self.prompt_input = QtWidgets.QTextEdit()
            self.prompt_input.setObjectName("promptInput"); self.prompt_input.setFixedHeight(110)
            self.prompt_input.setPlaceholderText(
                "e.g.  Create an enemy AI that chases the player\n\n"
                "e.g.  Create a door that opens when the player walks near it\n\n"
                "e.g.  Create a health pickup that gives 25 health on overlap"
            )
            blay.addWidget(self.prompt_input)

            # Generate button
            self.gen_btn = QtWidgets.QPushButton("⚡  Generate Blueprint")
            self.gen_btn.setObjectName("genBtn"); self.gen_btn.setFixedHeight(48)
            self.gen_btn.clicked.connect(self._on_generate)
            blay.addWidget(self.gen_btn)

            # Log
            lh = QtWidgets.QHBoxLayout(); lh.addWidget(self._lbl("OUTPUT LOG")); lh.addStretch()
            cb = QtWidgets.QPushButton("Clear"); cb.setObjectName("ghostBtn")
            cb.clicked.connect(lambda: self.log_view.clear()); lh.addWidget(cb)
            blay.addLayout(lh)
            self.log_view = QtWidgets.QTextEdit()
            self.log_view.setObjectName("logView"); self.log_view.setReadOnly(True)
            self.log_view.setMinimumHeight(160)
            self.log_view.append('<span style="color:#334155;">─── MCP Blueprint Generator v1.2.0 ready ───</span>')
            blay.addWidget(self.log_view)

            # Quick prompts
            blay.addWidget(self._lbl("QUICK PROMPTS"))
            for qp in [
                "Create an enemy AI that chases the player",
                "Create a door that opens when the player walks near it",
                "Create a health pickup that gives 25 health on overlap",
                "Create a turret that rotates toward the player every tick",
                "Create a game timer that ends the match after 60 seconds",
            ]:
                btn = QtWidgets.QPushButton(f"  {qp}")
                btn.setObjectName("ghostBtn")
                btn.setStyleSheet("QPushButton#ghostBtn{text-align:left;padding:7px 12px;border-radius:8px;font-size:12px;}")
                btn.clicked.connect(lambda _, t=qp: self.prompt_input.setPlainText(t))
                blay.addWidget(btn)

            blay.addStretch()
            root.addWidget(body)

        def _toggle_key(self):
            if self.key_input.echoMode() == QtWidgets.QLineEdit.Password:
                self.key_input.setEchoMode(QtWidgets.QLineEdit.Normal)
                self._show_btn.setText("Hide")
            else:
                self.key_input.setEchoMode(QtWidgets.QLineEdit.Password)
                self._show_btn.setText("Show")

        def _load_settings(self):
            cfg = _load_cfg()
            if cfg.get("api_key"): self.key_input.setText(cfg["api_key"])
            saved = cfg.get("model", DEFAULT_MODEL)
            for i in range(self.model_combo.count()):
                if self.model_combo.itemData(i) == saved:
                    self.model_combo.setCurrentIndex(i); break

        def _save_settings(self, *_):
            cfg = _load_cfg()
            cfg["api_key"] = self.key_input.text().strip()
            mid = self.model_combo.currentData()
            if mid: cfg["model"] = mid
            _save_cfg(cfg)

        def _emit(self, msg, color="#94a3b8"):
            self._log_sig.emit(msg, color)

        def _append_log(self, msg, color):
            self.log_view.append(f'<span style="color:{color};">{msg}</span>')
            sb = self.log_view.verticalScrollBar(); sb.setValue(sb.maximum())

        def _on_generate(self):
            api_key  = self.key_input.text().strip()
            model_id = self.model_combo.currentData()
            prompt   = self.prompt_input.toPlainText().strip()
            if not api_key:  self._emit("❌  Paste your OpenRouter API key above.", "#f87171"); return
            if not model_id: self._emit("❌  Select a model from the dropdown at the top.", "#f87171"); return
            if not prompt:   self._emit("❌  Enter a prompt.", "#f87171"); return
            self.gen_btn.setEnabled(False); self.gen_btn.setText("Generating…")
            self._emit("─" * 50, "#1e2d45")
            self._emit(f"📝  {prompt}", "#e2e8f0")
            self._emit(f"🤖  {model_id}", "#a855f7")
            _run_generate(prompt, api_key, model_id,
                on_log=lambda m: self._emit(m, "#94a3b8"),
                on_done=lambda ok, name: self._done_sig.emit(ok, name))

        def _on_done(self, success, bp_name):
            self.gen_btn.setEnabled(True); self.gen_btn.setText("⚡  Generate Blueprint")

    return MCPWindow()


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 3 — intentionally skipped (removed dialog popups that were annoying)
# ─────────────────────────────────────────────────────────────────────────────
def _try_unreal_dialog():
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 4 — Console menu (always works in the Output Log Python console)
# ─────────────────────────────────────────────────────────────────────────────
def _console_menu():
    """
    Prints ready-to-use instructions to the Output Log.
    Uses the already-saved key and model — asks for nothing.
    """
    saved_key   = _cfg_get("api_key", "")
    saved_model = _cfg_get("model", DEFAULT_MODEL)

    _log("═" * 60)
    _log("  MCP BLUEPRINT GENERATOR  v1.2.0")
    _log("  (Qt window unavailable — use the Python console below)")
    _log("═" * 60)

    if saved_key:
        _log(f"  ✓ API key: …{saved_key[-8:]}  (already saved)")
        _log(f"  ✓ Model:   {saved_model}")
        _log("")
        _log("  ➤ Generate a Blueprint — copy/paste into Python console:")
        _log('    import ai_panel')
        _log('    ai_panel.run("Create an enemy that chases the player")')
        _log('    ai_panel.run("Create a door that opens when player walks near")')
        _log('    ai_panel.run("Create a health pickup that gives 25 HP")')
        _log("")
        _log("  ➤ Switch model:")
        _log('    ai_panel.set_model("gemini-2.5-pro")')
        _log('    ai_panel.set_model("deepseek-v3.2")')
        _log('    ai_panel.set_model("gpt-4o")')
        _log('    ai_panel.list_models()   # see all options')
    else:
        _log("  ⚠  No API key found. Set it once:")
        _log('    import ai_panel')
        _log('    ai_panel.set_key("sk-or-v1-your-key-here")')
        _log('    ai_panel.run("Create an enemy that chases the player")')
        _log("")
        _log("  Get a free key at: openrouter.ai/keys")

    _log("═" * 60)
    _log("  Switch the Output Log dropdown to PYTHON, then paste a command above.")
    _log("═" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def show():
    """
    Open the MCP Blueprint Generator.
    Tries Qt window first, then EditorDialog, then console instructions.
    """
    _log("MCP Blueprint Generator v1.2.0 — opening…")

    if _try_qt():
        return

    _log_warn("Qt/PySide2 window not available — trying Unreal built-in dialogs…")
    if _try_unreal_dialog():
        return

    # Final fallback — console instructions always work
    _console_menu()


def start():
    """Called by init_unreal.py when the plugin loads."""
    show()
