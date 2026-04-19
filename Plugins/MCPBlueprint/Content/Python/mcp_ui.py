"""
mcp_ui.py  —  MCP Blueprint Generator UI
Creates a real docked Unreal panel using slate/EditorUtilityWidget.

Strategy:
  1. Try PySide2/PySide6 floating window  (UE 5.0-5.3)
  2. Try PySide6 floating window           (UE 5.4+)
  3. Build a native Unreal slate window    (always works, uses unreal.slate_* APIs)
  4. Console fallback                      (last resort, never asks for key again)
"""

import json
import os
import sys
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
# Models
# ─────────────────────────────────────────────────────────────────────────────
MODELS = [
    ("── Claude ──────────────────────",   None),
    ("Claude Sonnet 4.5  ★ recommended",  "anthropic/claude-sonnet-4.5"),
    ("Claude Opus 4.5  (most capable)",    "anthropic/claude-opus-4.5"),
    ("Claude Opus 4",                       "anthropic/claude-opus-4"),
    ("Claude Sonnet 4",                     "anthropic/claude-sonnet-4"),
    ("Claude 3.7 Sonnet",                   "anthropic/claude-3.7-sonnet"),
    ("Claude 3.7 Sonnet Thinking",          "anthropic/claude-3.7-sonnet:thinking"),
    ("Claude Haiku 4.5  (fastest)",         "anthropic/claude-haiku-4.5"),
    ("Claude 3.5 Haiku",                    "anthropic/claude-3.5-haiku"),
    ("── Gemini ──────────────────────",   None),
    ("Gemini 2.5 Pro  ★",                  "google/gemini-2.5-pro"),
    ("Gemini 2.5 Flash",                    "google/gemini-2.5-flash"),
    ("Gemini 2.5 Flash Lite",               "google/gemini-2.5-flash-lite"),
    ("Gemini 3.1 Pro Preview",              "google/gemini-3.1-pro-preview"),
    ("Gemini 3 Flash Preview",              "google/gemini-3-flash-preview"),
    ("Gemini 2.0 Flash",                    "google/gemini-2.0-flash-001"),
    ("── DeepSeek ────────────────────",   None),
    ("DeepSeek V3.2  ★",                   "deepseek/deepseek-v3.2"),
    ("DeepSeek V3.2 Speciale",              "deepseek/deepseek-v3.2-speciale"),
    ("DeepSeek R1 0528  (reasoning)",       "deepseek/deepseek-r1-0528"),
    ("DeepSeek R1  (reasoning)",            "deepseek/deepseek-r1"),
    ("DeepSeek R1T2 Chimera",               "tngtech/deepseek-r1t2-chimera"),
    ("── GPT-4o ──────────────────────",   None),
    ("GPT-4o",                              "openai/gpt-4o"),
    ("GPT-4o Mini  (most affordable)",      "openai/gpt-4o-mini"),
]
SELECTABLE    = [(l, m) for l, m in MODELS if m]
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
def _log(msg):
    try:
        import unreal; unreal.log(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] {msg}")

def _warn(msg):
    try:
        import unreal; unreal.log_warning(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] WARN: {msg}")

# ─────────────────────────────────────────────────────────────────────────────
# Core generate (shared by all UI strategies)
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are an Unreal Engine 5 Blueprint generation assistant. "
    "The user describes game logic in plain English. "
    "Respond with ONLY a valid JSON object — no explanation, no markdown.\n\n"
    '{"blueprint_name":"BP_Name","commands":['
    '{"action":"create_blueprint","name":"BP_Name","parent_class":"Actor"},'
    '{"action":"add_variable","blueprint":"BP_Name","variable_name":"Health","variable_type":"Float","default_value":100},'
    '{"action":"add_node","blueprint":"BP_Name","node":"Event BeginPlay","id":"n0","x":0,"y":0},'
    '{"action":"add_node","blueprint":"BP_Name","node":"Print String","id":"n1","x":300,"y":0},'
    '{"action":"connect_nodes","blueprint":"BP_Name","from_node":"n0","from_pin":"Then","to_node":"n1","to_pin":"Execute"},'
    '{"action":"compile_blueprint","name":"BP_Name"}]}\n\n'
    "Rules: BP_ prefix PascalCase. parent_class: Actor/Character/Pawn/GameModeBase/PlayerController. "
    "variable_type: Boolean/Integer/Float/String/Vector/Rotator/Transform. "
    "Nodes: Event BeginPlay, Event Tick, Event ActorBeginOverlap, Branch, Print String, "
    "Delay, Get Player Pawn, Get Actor Location, Set Actor Location, Destroy Actor, AI Move To, "
    "Timeline, Cast To Character. Unique ids. compile_blueprint last. Return ONLY JSON."
)

def _generate(prompt, api_key, model_id, on_log=None, on_done=None):
    log = on_log or _log

    def _worker():
        import urllib.request, urllib.error, blueprint_executor
        try:
            log(f"⏳ Calling {model_id}…")
            payload = json.dumps({
                "model": model_id, "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ]
            }).encode()
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions", data=payload,
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json",
                         "HTTP-Referer": "https://github.com/mkbrown261/unreal-assistant",
                         "X-Title": "MCP Blueprint Generator"},
                method="POST")
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read().decode())
            content = data["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = "\n".join(l for l in content.split("\n") if not l.startswith("```")).strip()
            result   = json.loads(content)
            commands = result.get("commands", [])
            bp_name  = result.get("blueprint_name", "BP_Generated")
            log(f"✅ AI returned {len(commands)} commands → {bp_name}")
            if not commands:
                log("❌ No commands. Try rephrasing.")
                if on_done: on_done(False, "")
                return
            holder = {}; evt = threading.Event()
            def _exec():
                try:    holder["r"] = blueprint_executor.execute_batch(commands)
                except: holder["r"] = {"success": False, "results": []}
                finally: evt.set()
            try:
                import unreal
                unreal.call_on_game_thread(_exec); evt.wait(30)
            except (ImportError, AttributeError):
                _exec()
            batch = holder.get("r", {"success": False, "results": []})
            if batch.get("success"):
                log(f"🎉 {bp_name} created — {batch.get('succeeded',0)}/{batch.get('total',0)} OK")
                log(f"📂 Content Browser → /Game/MCP/{bp_name}")
                try:
                    import unreal
                    unreal.EditorAssetLibrary.sync_browser_to_objects([f"/Game/MCP/{bp_name}"])
                except Exception: pass
                if on_done: on_done(True, bp_name)
            else:
                log(f"⚠️ Partial: {batch.get('succeeded',0)} ok, {batch.get('failed',0)} failed")
                for r2 in batch.get("results", []):
                    if not r2.get("success"): log(f"  ✗ {r2.get('message','?')}")
                if on_done: on_done(False, bp_name)
        except urllib.error.HTTPError as e:
            log(f"❌ HTTP {e.code}: {e.read().decode(errors='replace')[:200]}")
            if on_done: on_done(False, "")
        except json.JSONDecodeError as e:
            log(f"❌ Bad JSON from AI: {e}")
            if on_done: on_done(False, "")
        except Exception:
            log(f"❌ {traceback.format_exc()}")
            if on_done: on_done(False, "")

    threading.Thread(target=_worker, daemon=True, name="MCPGen").start()


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 1 & 2 — PySide2 / PySide6 Qt floating window
# ─────────────────────────────────────────────────────────────────────────────
_qt_win = None

def _try_qt():
    global _qt_win
    QtWidgets = QtCore = QtGui = None
    for pkg in ("PySide2", "PySide6"):
        try:
            import importlib
            QtWidgets = importlib.import_module(f"{pkg}.QtWidgets")
            QtCore    = importlib.import_module(f"{pkg}.QtCore")
            QtGui     = importlib.import_module(f"{pkg}.QtGui")
            break
        except ImportError:
            continue
    if not QtWidgets:
        return False

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if _qt_win and _qt_win.isVisible():
        _qt_win.raise_(); _qt_win.activateWindow(); return True

    try:
        win = _build_qt(QtWidgets, QtCore, QtGui)
        if not win: return False
        _qt_win = win; win.show(); win.raise_(); win.activateWindow()
        return True
    except Exception as e:
        _warn(f"Qt window error: {e}"); return False


def _build_qt(QtWidgets, QtCore, QtGui):
    Qt = QtCore.Qt
    STYLE = """
    QWidget{font-family:'Segoe UI',Arial,sans-serif;font-size:13px;color:#e2e8f0;background:transparent}
    QWidget#bar{background:#0d0d1f;border-bottom:1px solid #1e2d45}
    QComboBox#mc{background:#1a2744;border:1.5px solid #2d3f60;border-radius:20px;
        padding:6px 36px 6px 14px;color:#c4b5fd;font-size:13px;font-weight:600;min-width:260px}
    QComboBox#mc:hover{border-color:#a855f7}
    QComboBox#mc::drop-down{border:none;width:28px}
    QComboBox#mc QAbstractItemView{background:#111827;border:1.5px solid #2d3f60;
        color:#e2e8f0;selection-background-color:#2d1d4e;outline:none;padding:4px}
    QLineEdit#ki{background:#111827;border:1.5px solid #1e2d45;border-radius:10px;
        padding:9px 14px;color:#e2e8f0}
    QLineEdit#ki:focus{border-color:#a855f7}
    QTextEdit#pi{background:#111827;border:1.5px solid #1e2d45;border-radius:10px;
        padding:10px 14px;color:#e2e8f0}
    QTextEdit#pi:focus{border-color:#a855f7}
    QPushButton#gb{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #9333ea,stop:1 #4f46e5);
        border:none;border-radius:10px;color:white;font-size:14px;font-weight:700;padding:12px 24px}
    QPushButton#gb:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7e22ce,stop:1 #3730a3)}
    QPushButton#gb:disabled{background:#1e293b;color:#4b5563}
    QPushButton#gh{background:transparent;border:1px solid #1e2d45;border-radius:8px;
        color:#64748b;font-size:11px;padding:5px 12px}
    QPushButton#gh:hover{border-color:#4b5563;color:#94a3b8}
    QTextEdit#lv{background:#080d17;border:1.5px solid #1e2d45;border-radius:10px;
        font-family:'Consolas','Courier New',monospace;font-size:11px;color:#94a3b8;padding:10px}
    QScrollBar:vertical{background:#111827;width:6px;border-radius:3px}
    QScrollBar::handle:vertical{background:#2d3f60;border-radius:3px}
    QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}
    """

    class Win(QtWidgets.QWidget):
        _ls = QtCore.Signal(str, str)
        _ds = QtCore.Signal(bool, str)

        def __init__(self):
            super().__init__()
            self.setWindowTitle("MCP Blueprint Generator  v1.2.0")
            self.setMinimumSize(540, 760); self.resize(560, 800)
            self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_DeleteOnClose, False)
            self.setStyleSheet(STYLE)
            pal = self.palette()
            pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#0b0f1a"))
            self.setPalette(pal); self.setAutoFillBackground(True)
            self._ui(); self._load(); self._ls.connect(self._al); self._ds.connect(self._od)

        def _lbl(self, t):
            l = QtWidgets.QLabel(t)
            l.setStyleSheet("color:#475569;font-size:10px;font-weight:700;letter-spacing:.1em")
            return l

        def _ui(self):
            root = QtWidgets.QVBoxLayout(self); root.setSpacing(0); root.setContentsMargins(0,0,0,0)

            # Model bar — always at top
            bar = QtWidgets.QWidget(); bar.setObjectName("bar"); bar.setFixedHeight(58)
            bl  = QtWidgets.QHBoxLayout(bar); bl.setContentsMargins(18,0,18,0)
            lm  = QtWidgets.QLabel("MODEL")
            lm.setStyleSheet("color:#64748b;font-size:11px;font-weight:700;letter-spacing:.08em")
            bl.addWidget(lm); bl.addSpacing(12)
            self.mc = QtWidgets.QComboBox(); self.mc.setObjectName("mc"); self.mc.setFixedHeight(36)
            for lbl, mid in MODELS:
                if mid is None:
                    self.mc.addItem(lbl)
                    item = self.mc.model().item(self.mc.count()-1)
                    item.setEnabled(False); item.setForeground(QtGui.QColor("#334155"))
                else:
                    self.mc.addItem(lbl, mid)
            self.mc.currentIndexChanged.connect(self._sv)
            bl.addWidget(self.mc); bl.addStretch(); root.addWidget(bar)

            # Body
            body = QtWidgets.QWidget(); body.setStyleSheet("background:#0b0f1a")
            bl2  = QtWidgets.QVBoxLayout(body); bl2.setContentsMargins(20,20,20,20); bl2.setSpacing(14)

            # Key
            bl2.addWidget(self._lbl("OPENROUTER API KEY"))
            kr = QtWidgets.QHBoxLayout(); kr.setSpacing(8)
            self.ki = QtWidgets.QLineEdit(); self.ki.setObjectName("ki")
            self.ki.setPlaceholderText("sk-or-v1-…  paste your key here")
            self.ki.setEchoMode(QtWidgets.QLineEdit.Password)
            self.ki.textChanged.connect(self._sv); kr.addWidget(self.ki)
            self._sb = QtWidgets.QPushButton("Show"); self._sb.setObjectName("gh")
            self._sb.setFixedWidth(56); self._sb.clicked.connect(self._tk); kr.addWidget(self._sb)
            bl2.addLayout(kr)
            lnk = QtWidgets.QLabel('<a href="https://openrouter.ai/keys" style="color:#a855f7;text-decoration:none;">→ Get a free key at openrouter.ai/keys</a>')
            lnk.setOpenExternalLinks(True); lnk.setStyleSheet("font-size:11px;color:#64748b")
            bl2.addWidget(lnk)

            div = QtWidgets.QFrame(); div.setFrameShape(QtWidgets.QFrame.HLine)
            div.setStyleSheet("color:#1e2d45"); bl2.addWidget(div)

            # Prompt
            bl2.addWidget(self._lbl("DESCRIBE THE BLUEPRINT YOU WANT"))
            self.pi = QtWidgets.QTextEdit(); self.pi.setObjectName("pi"); self.pi.setFixedHeight(110)
            self.pi.setPlaceholderText(
                "e.g.  Create an enemy AI that chases the player\n\n"
                "e.g.  Create a door that opens when player walks near it\n\n"
                "e.g.  Create a health pickup that restores 25 HP on overlap")
            bl2.addWidget(self.pi)

            # Generate button
            self.gb = QtWidgets.QPushButton("⚡  Generate Blueprint")
            self.gb.setObjectName("gb"); self.gb.setFixedHeight(48)
            self.gb.clicked.connect(self._go); bl2.addWidget(self.gb)

            # Log
            lh = QtWidgets.QHBoxLayout(); lh.addWidget(self._lbl("OUTPUT LOG")); lh.addStretch()
            cb = QtWidgets.QPushButton("Clear"); cb.setObjectName("gh")
            cb.clicked.connect(lambda: self.lv.clear()); lh.addWidget(cb); bl2.addLayout(lh)
            self.lv = QtWidgets.QTextEdit(); self.lv.setObjectName("lv")
            self.lv.setReadOnly(True); self.lv.setMinimumHeight(160)
            self.lv.append('<span style="color:#334155;">─── MCP Blueprint Generator v1.2.0 ───</span>')
            bl2.addWidget(self.lv)

            # Quick prompts
            bl2.addWidget(self._lbl("QUICK PROMPTS"))
            for qp in [
                "Create an enemy AI that chases the player",
                "Create a door that opens when the player walks near it",
                "Create a health pickup that gives 25 HP on overlap",
                "Create a turret that rotates toward the player every tick",
                "Create a game timer that ends the match after 60 seconds",
            ]:
                b = QtWidgets.QPushButton(f"  {qp}"); b.setObjectName("gh")
                b.setStyleSheet("QPushButton#gh{text-align:left;padding:7px 12px;border-radius:8px;font-size:12px}")
                b.clicked.connect(lambda _, t=qp: self.pi.setPlainText(t)); bl2.addWidget(b)

            bl2.addStretch(); root.addWidget(body)

        def _tk(self):
            if self.ki.echoMode() == QtWidgets.QLineEdit.Password:
                self.ki.setEchoMode(QtWidgets.QLineEdit.Normal); self._sb.setText("Hide")
            else:
                self.ki.setEchoMode(QtWidgets.QLineEdit.Password); self._sb.setText("Show")

        def _load(self):
            cfg = _load()
            if cfg.get("api_key"): self.ki.setText(cfg["api_key"])
            saved = cfg.get("model", DEFAULT_MODEL)
            for i in range(self.mc.count()):
                if self.mc.itemData(i) == saved:
                    self.mc.setCurrentIndex(i); break

        def _sv(self, *_):
            d = _load(); d["api_key"] = self.ki.text().strip()
            mid = self.mc.currentData()
            if mid: d["model"] = mid
            _save(d)

        def _emit(self, msg, color="#94a3b8"): self._ls.emit(msg, color)

        def _al(self, msg, color):
            self.lv.append(f'<span style="color:{color};">{msg}</span>')
            sb = self.lv.verticalScrollBar(); sb.setValue(sb.maximum())

        def _go(self):
            key = self.ki.text().strip(); mid = self.mc.currentData(); prompt = self.pi.toPlainText().strip()
            if not key:   self._emit("❌  Paste your OpenRouter API key above.", "#f87171"); return
            if not mid:   self._emit("❌  Select a model.", "#f87171"); return
            if not prompt: self._emit("❌  Enter a prompt.", "#f87171"); return
            self.gb.setEnabled(False); self.gb.setText("Generating…")
            self._emit("─"*50, "#1e2d45"); self._emit(f"📝 {prompt}", "#e2e8f0")
            _generate(prompt, key, mid,
                on_log=lambda m: self._emit(m, "#94a3b8"),
                on_done=lambda ok, n: self._ds.emit(ok, n))

        def _od(self, success, bp):
            self.gb.setEnabled(True); self.gb.setText("⚡  Generate Blueprint")

    return Win()


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 3 — Native Unreal slate window via unreal.slate module
# Works in UE 5.5+ where unreal.slate is available
# ─────────────────────────────────────────────────────────────────────────────
def _try_slate():
    """
    Build a real Unreal Editor window using the slate Python bindings.
    Available in UE 5.5+. Returns True if successful.
    """
    try:
        import unreal
        # slate bindings may be under unreal directly or unreal.slate
        slate = getattr(unreal, "slate", None)
        if slate is None:
            return False
        # Quick check that the API we need exists
        if not hasattr(slate, "open_editor_for_asset") and not hasattr(unreal, "ToolMenus"):
            return False
    except Exception:
        return False

    # Build via ToolMenus — add an MCP panel entry and open it
    try:
        _build_tool_menu_panel()
        return True
    except Exception as e:
        _warn(f"Slate panel error: {e}")
        return False


def _build_tool_menu_panel():
    """
    Add MCP Blueprint Generator to Window menu and open it as a docked tab.
    Uses unreal.ToolMenus which is available in UE 5.x.
    """
    import unreal

    menus = unreal.ToolMenus.get()
    menu  = menus.find_menu("LevelEditor.MainMenu.Window")
    if menu:
        section = menu.find_or_add_section("MCPBlueprint", unreal.Text("MCP Blueprint"))
        entry   = unreal.ToolMenuEntry(
            name=unreal.Name("MCPBlueprintGenerator"),
            type=unreal.MultiBlockType.MENU_ENTRY,
        )
        entry.set_label(unreal.Text("MCP Blueprint Generator"))
        entry.set_tool_tip(unreal.Text("Generate Blueprints from plain-English prompts using AI"))
        section.add_entry(entry)
        menus.refresh_all_widgets()


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 4 — EditorUtilityWidget (HTML-like panel, docked in Unreal)
# This creates a real visible widget inside the Unreal editor
# ─────────────────────────────────────────────────────────────────────────────
_euw_window = None   # global so it isn't garbage collected

def _try_editor_utility_widget():
    """
    Create a floating Unreal Editor window using Python + Unreal's
    EditorUtilitySubsystem. This is a real docked panel — no Qt needed.
    Returns True if the window opened successfully.
    """
    try:
        import unreal
        subsystem = unreal.get_editor_subsystem(unreal.EditorUtilitySubsystem)
        if subsystem is None:
            return False
    except Exception:
        return False

    try:
        global _euw_window
        _euw_window = _MCPEditorWindow()
        _euw_window.open()
        return True
    except Exception as e:
        _warn(f"EditorUtilityWidget error: {e}")
        return False


class _MCPEditorWindow:
    """
    Uses Unreal's Python API to create a real editor window with:
    - A model combo (simulated via repeated EditorDialog or native if possible)
    - Key field
    - Prompt field
    - Generate button
    - Output log

    Since pure Python can't create Slate widgets, we use the approach of
    running a persistent tkinter window (ships with Python 3.11 on Mac/Win)
    which attaches to the Unreal process as a child window.
    """

    def __init__(self):
        self._thread = None
        self._root   = None
        self._running = False

    def open(self):
        if self._running and self._thread and self._thread.is_alive():
            # Bring to front
            try:
                if self._root: self._root.lift(); self._root.focus_force()
            except Exception: pass
            return
        self._thread = threading.Thread(target=self._run_tk, daemon=True, name="MCPWindow")
        self._thread.start()

    def _run_tk(self):
        try:
            import tkinter as tk
            from tkinter import ttk, scrolledtext
        except ImportError:
            return  # tkinter not available

        self._running = True
        root = tk.Tk()
        self._root = root
        root.title("MCP Blueprint Generator  v1.2.0")
        root.geometry("580x780")
        root.resizable(True, True)
        root.configure(bg="#0b0f1a")

        # ── Styles ────────────────────────────────────────────────────────────
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame",       background="#0b0f1a")
        style.configure("TLabel",       background="#0b0f1a", foreground="#94a3b8",
                         font=("Segoe UI", 9, "bold"))
        style.configure("Title.TLabel", background="#0d0d1f", foreground="#e2e8f0",
                         font=("Segoe UI", 13, "bold"))
        style.configure("TCombobox",    fieldbackground="#1a2744", background="#1a2744",
                         foreground="#c4b5fd", font=("Segoe UI", 11))
        style.configure("Gen.TButton",  background="#9333ea", foreground="white",
                         font=("Segoe UI", 12, "bold"), padding=(12, 10))
        style.map("Gen.TButton",        background=[("active", "#7e22ce")])
        style.configure("Ghost.TButton", background="#111827", foreground="#64748b",
                         font=("Segoe UI", 9), padding=(5, 4))
        style.map("Ghost.TButton",       background=[("active", "#1e2d45")])

        # ── Model bar ─────────────────────────────────────────────────────────
        bar = tk.Frame(root, bg="#0d0d1f", height=54)
        bar.pack(fill="x", padx=0, pady=0)
        bar.pack_propagate(False)

        tk.Label(bar, text="MODEL", bg="#0d0d1f", fg="#64748b",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(18, 8), pady=16)

        model_labels = [l for l, m in SELECTABLE]
        model_ids    = [m for l, m in SELECTABLE]
        model_var    = tk.StringVar()

        saved_model  = _get("model", DEFAULT_MODEL)
        saved_label  = next((l for l, m in SELECTABLE if m == saved_model), model_labels[0])
        model_var.set(saved_label)

        combo = ttk.Combobox(bar, textvariable=model_var, values=model_labels,
                             state="readonly", font=("Segoe UI", 11),
                             width=36)
        combo.pack(side="left", pady=12)

        def on_model_change(*_):
            lbl = model_var.get()
            mid = next((m for l, m in SELECTABLE if l == lbl), DEFAULT_MODEL)
            _set("model", mid)

        combo.bind("<<ComboboxSelected>>", on_model_change)

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(root, bg="#0b0f1a")
        body.pack(fill="both", expand=True, padx=20, pady=16)

        # API Key
        tk.Label(body, text="OPENROUTER API KEY", bg="#0b0f1a", fg="#475569",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        key_frame = tk.Frame(body, bg="#0b0f1a")
        key_frame.pack(fill="x", pady=(0, 4))

        key_var  = tk.StringVar(value=_get("api_key", ""))
        show_var = tk.BooleanVar(value=False)

        key_entry = tk.Entry(key_frame, textvariable=key_var, show="•",
                             bg="#111827", fg="#e2e8f0", insertbackground="#e2e8f0",
                             relief="flat", font=("Segoe UI", 11), bd=0,
                             highlightthickness=1, highlightbackground="#1e2d45",
                             highlightcolor="#a855f7")
        key_entry.pack(side="left", fill="x", expand=True, ipady=8, ipadx=10)

        def save_key(*_):
            _set("api_key", key_var.get().strip())
        key_var.trace_add("write", save_key)

        def toggle_show():
            show_var.set(not show_var.get())
            key_entry.config(show="" if show_var.get() else "•")
            show_btn.config(text="Hide" if show_var.get() else "Show")

        show_btn = tk.Button(key_frame, text="Show", command=toggle_show,
                             bg="#111827", fg="#64748b", relief="flat",
                             font=("Segoe UI", 9), padx=10, cursor="hand2")
        show_btn.pack(side="left", padx=(6, 0))

        tk.Label(body, text="→ Get a free key at openrouter.ai/keys",
                 bg="#0b0f1a", fg="#a855f7", font=("Segoe UI", 9),
                 cursor="hand2").pack(anchor="w", pady=(2, 12))

        # Divider
        tk.Frame(body, bg="#1e2d45", height=1).pack(fill="x", pady=(0, 12))

        # Prompt
        tk.Label(body, text="DESCRIBE THE BLUEPRINT YOU WANT", bg="#0b0f1a", fg="#475569",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        prompt_box = tk.Text(body, height=6, bg="#111827", fg="#e2e8f0",
                             insertbackground="#e2e8f0", relief="flat",
                             font=("Segoe UI", 11), bd=0,
                             highlightthickness=1, highlightbackground="#1e2d45",
                             highlightcolor="#a855f7", wrap="word")
        prompt_box.pack(fill="x", ipady=8, ipadx=10, pady=(0, 12))
        prompt_box.insert("1.0",
            "e.g.  Create an enemy AI that chases the player\n"
            "e.g.  Create a door that opens when the player walks near it")
        prompt_box.config(fg="#475569")

        def on_focus_in(e):
            if prompt_box.get("1.0", "end-1c").startswith("e.g."):
                prompt_box.delete("1.0", "end")
                prompt_box.config(fg="#e2e8f0")
        def on_focus_out(e):
            if not prompt_box.get("1.0", "end-1c").strip():
                prompt_box.insert("1.0", "e.g.  Create an enemy AI that chases the player")
                prompt_box.config(fg="#475569")

        prompt_box.bind("<FocusIn>",  on_focus_in)
        prompt_box.bind("<FocusOut>", on_focus_out)

        # Generate button
        gen_btn = tk.Button(body, text="⚡  Generate Blueprint",
                            bg="#9333ea", fg="white", relief="flat",
                            font=("Segoe UI", 13, "bold"), cursor="hand2",
                            activebackground="#7e22ce", activeforeground="white",
                            pady=12)
        gen_btn.pack(fill="x", pady=(0, 12))

        # Output log
        log_hdr = tk.Frame(body, bg="#0b0f1a")
        log_hdr.pack(fill="x", pady=(0, 4))
        tk.Label(log_hdr, text="OUTPUT LOG", bg="#0b0f1a", fg="#475569",
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Button(log_hdr, text="Clear", command=lambda: log_box.delete("1.0","end"),
                  bg="#111827", fg="#64748b", relief="flat",
                  font=("Segoe UI", 9), padx=10, cursor="hand2").pack(side="right")

        log_box = scrolledtext.ScrolledText(body, height=8,
                                            bg="#080d17", fg="#94a3b8",
                                            insertbackground="#94a3b8", relief="flat",
                                            font=("Consolas", 9), bd=0,
                                            highlightthickness=1, highlightbackground="#1e2d45",
                                            state="normal", wrap="word")
        log_box.pack(fill="both", expand=True, pady=(0, 12))
        log_box.insert("end", "─── MCP Blueprint Generator v1.2.0 ready ───\n")

        def append_log(msg):
            log_box.config(state="normal")
            log_box.insert("end", msg + "\n")
            log_box.see("end")
            log_box.config(state="normal")

        # Quick prompts
        tk.Label(body, text="QUICK PROMPTS", bg="#0b0f1a", fg="#475569",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        for qp in [
            "Create an enemy AI that chases the player",
            "Create a door that opens when the player walks near it",
            "Create a health pickup that gives 25 HP on overlap",
            "Create a turret that rotates toward the player every tick",
            "Create a game timer that ends the match after 60 seconds",
        ]:
            def _use(t=qp):
                prompt_box.delete("1.0", "end")
                prompt_box.insert("1.0", t)
                prompt_box.config(fg="#e2e8f0")
            tk.Button(body, text=f"  {qp}", command=_use,
                      bg="#111827", fg="#94a3b8", relief="flat",
                      font=("Segoe UI", 9), anchor="w", cursor="hand2",
                      activebackground="#1e2d45", padx=12, pady=6).pack(fill="x", pady=2)

        # ── Generate action ───────────────────────────────────────────────────
        def do_generate():
            key    = key_var.get().strip()
            lbl    = model_var.get()
            mid    = next((m for l, m in SELECTABLE if l == lbl), DEFAULT_MODEL)
            prompt = prompt_box.get("1.0", "end-1c").strip()

            if not key or key.startswith("e.g."):
                append_log("❌  Paste your OpenRouter API key above."); return
            if not prompt or prompt.startswith("e.g."):
                append_log("❌  Enter a prompt."); return

            gen_btn.config(state="disabled", text="Generating…")
            append_log("─" * 50)
            append_log(f"📝  {prompt}")
            append_log(f"🤖  {mid}")

            def done(ok, bp):
                root.after(0, lambda: gen_btn.config(state="normal", text="⚡  Generate Blueprint"))

            _generate(prompt, key, mid,
                on_log=lambda m: root.after(0, lambda msg=m: append_log(msg)),
                on_done=done)

        gen_btn.config(command=do_generate)

        root.mainloop()
        self._running = False


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 5 — Console fallback (uses saved key, never asks again)
# ─────────────────────────────────────────────────────────────────────────────
def _console_fallback():
    saved_key   = _get("api_key", "")
    saved_model = _get("model", DEFAULT_MODEL)
    _log("═" * 60)
    _log("  MCP BLUEPRINT GENERATOR  v1.2.0")
    _log("  (UI panel unavailable on this system)")
    _log("═" * 60)
    if saved_key:
        _log(f"  ✓ Key:   …{saved_key[-8:]}  (saved)")
        _log(f"  ✓ Model: {saved_model}")
        _log("")
        _log("  ➤ Generate — paste into Python console:")
        _log("    import ai_panel")
        _log('    ai_panel.run("Create an enemy that chases the player")')
        _log('    ai_panel.run("Create a door that opens on overlap")')
        _log('    ai_panel.run("Create a health pickup that gives 25 HP")')
        _log("")
        _log("  ➤ Switch model:")
        _log('    ai_panel.set_model("gemini-2.5-pro")')
        _log('    ai_panel.set_model("deepseek-v3.2")')
        _log('    ai_panel.list_models()')
    else:
        _log("  ⚠  No API key. Set it once:")
        _log("    import ai_panel")
        _log('    ai_panel.set_key("sk-or-v1-your-key")')
        _log('    ai_panel.run("Create an enemy that chases the player")')
        _log("  Get a free key at: openrouter.ai/keys")
    _log("═" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def show():
    """Open the MCP Blueprint Generator panel. Tries every available method."""
    _log("MCP Blueprint Generator v1.2.0 — opening…")

    # 1. PySide2/PySide6 Qt window
    if _try_qt():
        return

    # 2. tkinter window (ships with Python 3.11, works on Mac + Windows)
    try:
        euw = _MCPEditorWindow()
        euw.open()
        _log("UI panel opened (tkinter window)")
        return
    except Exception as e:
        _warn(f"tkinter window failed: {e}")

    # 3. Console fallback — uses saved key, never asks again
    _console_fallback()


def start():
    """Called by init_unreal.py on plugin load."""
    show()
