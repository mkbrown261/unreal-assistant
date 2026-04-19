"""
mcp_ui.py
Floating Qt UI panel for MCP Blueprint Generator — runs inside Unreal Engine 5.

Features:
  - Model switcher dropdown (Claude / Gemini / DeepSeek / GPT-4o)
    always visible at the top like Genspark AI Developer
  - API key field with show/hide toggle — auto-saved
  - Chat-style prompt input + Generate button
  - Live output log with colored messages
  - Auto-opens when the plugin loads; reopen any time:
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

# ─────────────────────────────────────────────────────────────────────────────
# Model list — grouped for the dropdown
# Each entry: (display_label, openrouter_model_id or None for separator)
# ─────────────────────────────────────────────────────────────────────────────
MODELS = [
    # ── Claude ──────────────────────────────────────────────────────────────
    ("── Claude ──────────────────────────",  None),
    ("Claude Sonnet 4.5  ★  (recommended)",  "anthropic/claude-sonnet-4.5"),
    ("Claude Opus 4.5  (most capable)",       "anthropic/claude-opus-4.5"),
    ("Claude Opus 4",                          "anthropic/claude-opus-4"),
    ("Claude Sonnet 4",                        "anthropic/claude-sonnet-4"),
    ("Claude 3.7 Sonnet",                      "anthropic/claude-3.7-sonnet"),
    ("Claude 3.7 Sonnet (Thinking)",           "anthropic/claude-3.7-sonnet:thinking"),
    ("Claude Haiku 4.5  (fastest)",            "anthropic/claude-haiku-4.5"),
    ("Claude 3.5 Haiku",                       "anthropic/claude-3.5-haiku"),
    # ── Gemini ───────────────────────────────────────────────────────────────
    ("── Gemini ──────────────────────────",  None),
    ("Gemini 2.5 Pro  ★",                     "google/gemini-2.5-pro"),
    ("Gemini 2.5 Flash",                       "google/gemini-2.5-flash"),
    ("Gemini 2.5 Flash Lite",                  "google/gemini-2.5-flash-lite"),
    ("Gemini 3.1 Pro Preview",                 "google/gemini-3.1-pro-preview"),
    ("Gemini 3 Flash Preview",                 "google/gemini-3-flash-preview"),
    ("Gemini 2.0 Flash",                       "google/gemini-2.0-flash-001"),
    ("Gemini 2.0 Flash Lite",                  "google/gemini-2.0-flash-lite-001"),
    # ── DeepSeek ─────────────────────────────────────────────────────────────
    ("── DeepSeek ────────────────────────",  None),
    ("DeepSeek V3.2  ★",                      "deepseek/deepseek-v3.2"),
    ("DeepSeek V3.2 Speciale",                 "deepseek/deepseek-v3.2-speciale"),
    ("DeepSeek V3.1",                          "deepseek/deepseek-chat-v3.1"),
    ("DeepSeek R1 0528  (reasoning)",          "deepseek/deepseek-r1-0528"),
    ("DeepSeek R1  (reasoning)",               "deepseek/deepseek-r1"),
    ("DeepSeek R1 Llama 70B",                 "deepseek/deepseek-r1-distill-llama-70b"),
    ("DeepSeek R1T2 Chimera",                  "tngtech/deepseek-r1t2-chimera"),
    # ── GPT-4o ───────────────────────────────────────────────────────────────
    ("── GPT-4o ──────────────────────────",  None),
    ("GPT-4o",                                 "openai/gpt-4o"),
    ("GPT-4o Mini  (most affordable)",         "openai/gpt-4o-mini"),
]

DEFAULT_MODEL_ID = "anthropic/claude-sonnet-4.5"

# ── Global window reference (prevents garbage collection) ─────────────────────
_window = None


# ─────────────────────────────────────────────────────────────────────────────
# Qt window builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_window():
    """Construct and return the MCPWindow Qt widget."""
    # Try PySide2 (ships with UE5), fall back to PySide6
    try:
        from PySide2 import QtWidgets, QtCore, QtGui
        Qt = QtCore.Qt
    except ImportError:
        try:
            from PySide6 import QtWidgets, QtCore, QtGui
            Qt = QtCore.Qt
        except ImportError:
            return None

    import urllib.request, urllib.error
    import blueprint_executor

    SYSTEM_PROMPT = (
        "You are an Unreal Engine 5 Blueprint generation assistant.\n"
        "The user describes game logic in plain English.\n"
        "Respond with ONLY a valid JSON object — no explanation, no markdown, no code fences.\n\n"
        "JSON structure:\n"
        "{\n"
        '  "blueprint_name": "BP_SomeName",\n'
        '  "commands": [\n'
        '    {"action": "create_blueprint", "name": "BP_SomeName", "parent_class": "Actor"},\n'
        '    {"action": "add_variable", "blueprint": "BP_SomeName", "variable_name": "Health", "variable_type": "Float", "default_value": 100},\n'
        '    {"action": "add_node", "blueprint": "BP_SomeName", "node": "Event BeginPlay", "id": "node_0", "x": 0, "y": 0},\n'
        '    {"action": "add_node", "blueprint": "BP_SomeName", "node": "Print String", "id": "node_1", "x": 300, "y": 0},\n'
        '    {"action": "connect_nodes", "blueprint": "BP_SomeName", "from_node": "node_0", "from_pin": "Then", "to_node": "node_1", "to_pin": "Execute"},\n'
        '    {"action": "compile_blueprint", "name": "BP_SomeName"}\n'
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- blueprint_name starts with BP_, PascalCase\n"
        "- parent_class: Actor, Character, Pawn, GameModeBase, PlayerController, ActorComponent\n"
        "- variable_type: Boolean, Integer, Float, String, Vector, Rotator, Transform\n"
        "- node types: Event BeginPlay, Event Tick, Event ActorBeginOverlap, Branch, Print String, "
        "Delay, Get Player Pawn, Get Actor Location, Set Actor Location, Destroy Actor, AI Move To, "
        "Timeline, Cast To Character\n"
        "- Every add_node must have a unique 'id' string\n"
        "- compile_blueprint must always be the last command\n"
        "- Return ONLY the JSON — nothing else"
    )

    # ── Stylesheet ─────────────────────────────────────────────────────────────
    STYLE = """
        QWidget {
            font-family: 'Segoe UI', 'SF Pro Display', Arial, sans-serif;
            font-size: 13px;
            color: #e2e8f0;
            background: transparent;
        }
        /* ── Top model-bar ── */
        QWidget#modelBar {
            background: #0d0d1f;
            border-bottom: 1px solid #1e2d45;
        }
        QLabel#modelBarLabel {
            color: #64748b;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        /* ── Model combo ── */
        QComboBox#modelCombo {
            background: #1a2744;
            border: 1.5px solid #2d3f60;
            border-radius: 20px;
            padding: 6px 36px 6px 14px;
            color: #c4b5fd;
            font-size: 13px;
            font-weight: 600;
            min-width: 240px;
        }
        QComboBox#modelCombo:hover {
            border-color: #a855f7;
            background: #1e2d5a;
        }
        QComboBox#modelCombo::drop-down {
            border: none;
            width: 28px;
        }
        QComboBox#modelCombo::down-arrow {
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid #a855f7;
            margin-right: 10px;
        }
        QComboBox#modelCombo QAbstractItemView {
            background: #111827;
            border: 1.5px solid #2d3f60;
            border-radius: 10px;
            color: #e2e8f0;
            selection-background-color: #2d1d4e;
            outline: none;
            padding: 4px;
        }
        /* ── Section labels ── */
        QLabel.section {
            color: #94a3b8;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }
        /* ── API key input ── */
        QLineEdit#keyInput {
            background: #111827;
            border: 1.5px solid #1e2d45;
            border-radius: 10px;
            padding: 9px 14px;
            color: #e2e8f0;
            font-size: 13px;
        }
        QLineEdit#keyInput:focus { border-color: #a855f7; }
        /* ── Prompt input ── */
        QTextEdit#promptInput {
            background: #111827;
            border: 1.5px solid #1e2d45;
            border-radius: 10px;
            padding: 10px 14px;
            color: #e2e8f0;
            font-size: 13px;
            line-height: 1.6;
        }
        QTextEdit#promptInput:focus { border-color: #a855f7; }
        /* ── Generate button ── */
        QPushButton#genBtn {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #9333ea, stop:1 #4f46e5);
            border: none;
            border-radius: 10px;
            color: white;
            font-size: 14px;
            font-weight: 700;
            padding: 12px 24px;
            letter-spacing: 0.03em;
        }
        QPushButton#genBtn:hover {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #7e22ce, stop:1 #3730a3);
        }
        QPushButton#genBtn:disabled {
            background: #1e293b;
            color: #4b5563;
        }
        /* ── Ghost buttons ── */
        QPushButton#ghostBtn {
            background: transparent;
            border: 1px solid #1e2d45;
            border-radius: 8px;
            color: #64748b;
            font-size: 11px;
            padding: 5px 12px;
        }
        QPushButton#ghostBtn:hover {
            border-color: #4b5563;
            color: #94a3b8;
        }
        /* ── Output log ── */
        QTextEdit#logView {
            background: #080d17;
            border: 1.5px solid #1e2d45;
            border-radius: 10px;
            font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;
            font-size: 11px;
            color: #94a3b8;
            padding: 10px;
        }
        /* ── Scrollbars ── */
        QScrollBar:vertical {
            background: #111827;
            width: 6px;
            border-radius: 3px;
        }
        QScrollBar::handle:vertical {
            background: #2d3f60;
            border-radius: 3px;
        }
        QScrollBar::handle:vertical:hover { background: #a855f7; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    """

    # ── Main window class ──────────────────────────────────────────────────────
    class MCPWindow(QtWidgets.QWidget):
        _log_sig  = QtCore.Signal(str, str)   # (html_fragment, raw_for_scroll)
        _done_sig = QtCore.Signal(bool, str)  # (success, bp_name)

        def __init__(self):
            super().__init__()
            self.setWindowTitle("MCP Blueprint Generator")
            self.setMinimumSize(540, 720)
            self.resize(560, 760)
            self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_DeleteOnClose, False)
            self.setStyleSheet(STYLE)

            # dark background for entire window
            pal = self.palette()
            pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#0b0f1a"))
            self.setPalette(pal)
            self.setAutoFillBackground(True)

            self._build_ui()
            self._load_settings()
            self._log_sig.connect(self._append_log)
            self._done_sig.connect(self._on_done)

        # ── UI construction ────────────────────────────────────────────────────
        def _build_ui(self):
            root = QtWidgets.QVBoxLayout(self)
            root.setSpacing(0)
            root.setContentsMargins(0, 0, 0, 0)

            # ── 1. Top model-switcher bar ─────────────────────────────────────
            model_bar = QtWidgets.QWidget()
            model_bar.setObjectName("modelBar")
            model_bar.setFixedHeight(58)
            mb_lay = QtWidgets.QHBoxLayout(model_bar)
            mb_lay.setContentsMargins(18, 0, 18, 0)

            lbl_model = QtWidgets.QLabel("MODEL")
            lbl_model.setObjectName("modelBarLabel")
            mb_lay.addWidget(lbl_model)

            mb_lay.addSpacing(12)

            self.model_combo = QtWidgets.QComboBox()
            self.model_combo.setObjectName("modelCombo")
            self.model_combo.setFixedHeight(36)
            self.model_combo.setSizeAdjustPolicy(
                QtWidgets.QComboBox.AdjustToContents
            )

            for label, model_id in MODELS:
                if model_id is None:
                    # Separator / section header — disabled item
                    self.model_combo.addItem(label)
                    idx = self.model_combo.count() - 1
                    item = self.model_combo.model().item(idx)
                    item.setEnabled(False)
                    item.setForeground(QtGui.QColor("#334155"))
                else:
                    self.model_combo.addItem(label, model_id)

            self.model_combo.currentIndexChanged.connect(self._save_settings)
            mb_lay.addWidget(self.model_combo)
            mb_lay.addStretch()
            root.addWidget(model_bar)

            # ── 2. Body (scrollable content area) ─────────────────────────────
            body = QtWidgets.QWidget()
            body.setStyleSheet("background: #0b0f1a;")
            b_lay = QtWidgets.QVBoxLayout(body)
            b_lay.setContentsMargins(20, 20, 20, 20)
            b_lay.setSpacing(16)

            # ── API Key ────────────────────────────────────────────────────────
            b_lay.addWidget(self._section_label("OPENROUTER API KEY"))

            key_row = QtWidgets.QHBoxLayout()
            key_row.setSpacing(8)
            self.key_input = QtWidgets.QLineEdit()
            self.key_input.setObjectName("keyInput")
            self.key_input.setPlaceholderText("sk-or-v1-…  (paste your key here)")
            self.key_input.setEchoMode(QtWidgets.QLineEdit.Password)
            self.key_input.textChanged.connect(self._save_settings)
            key_row.addWidget(self.key_input)

            self._show_btn = QtWidgets.QPushButton("Show")
            self._show_btn.setObjectName("ghostBtn")
            self._show_btn.setFixedWidth(56)
            self._show_btn.clicked.connect(self._toggle_key)
            key_row.addWidget(self._show_btn)
            b_lay.addLayout(key_row)

            link = QtWidgets.QLabel(
                '<a href="https://openrouter.ai/keys" '
                'style="color:#a855f7;text-decoration:none;">'
                '→ Get a free key at openrouter.ai/keys</a>'
            )
            link.setOpenExternalLinks(True)
            link.setStyleSheet("font-size:11px; color:#64748b;")
            b_lay.addWidget(link)

            # ── Divider ────────────────────────────────────────────────────────
            div = QtWidgets.QFrame()
            div.setFrameShape(QtWidgets.QFrame.HLine)
            div.setStyleSheet("color: #1e2d45;")
            b_lay.addWidget(div)

            # ── Prompt ────────────────────────────────────────────────────────
            b_lay.addWidget(self._section_label("DESCRIBE THE BLUEPRINT YOU WANT"))
            self.prompt_input = QtWidgets.QTextEdit()
            self.prompt_input.setObjectName("promptInput")
            self.prompt_input.setFixedHeight(120)
            self.prompt_input.setPlaceholderText(
                "e.g.  Create an enemy AI that chases the player and has 100 health\n\n"
                "e.g.  Create a door that opens when the player walks near it\n\n"
                "e.g.  Create a health pickup that gives 25 health on overlap"
            )
            b_lay.addWidget(self.prompt_input)

            # ── Generate button ────────────────────────────────────────────────
            self.gen_btn = QtWidgets.QPushButton("⚡  Generate Blueprint")
            self.gen_btn.setObjectName("genBtn")
            self.gen_btn.setFixedHeight(48)
            self.gen_btn.clicked.connect(self._on_generate)
            b_lay.addWidget(self.gen_btn)

            # ── Output log ────────────────────────────────────────────────────
            log_hdr = QtWidgets.QHBoxLayout()
            log_hdr.addWidget(self._section_label("OUTPUT LOG"))
            log_hdr.addStretch()
            clr = QtWidgets.QPushButton("Clear")
            clr.setObjectName("ghostBtn")
            clr.clicked.connect(lambda: self.log_view.clear())
            log_hdr.addWidget(clr)
            b_lay.addLayout(log_hdr)

            self.log_view = QtWidgets.QTextEdit()
            self.log_view.setObjectName("logView")
            self.log_view.setReadOnly(True)
            self.log_view.setMinimumHeight(180)
            self.log_view.append(
                '<span style="color:#334155;">─── MCP Blueprint Generator ready ───</span>'
            )
            b_lay.addWidget(self.log_view)

            # ── Quick prompts ──────────────────────────────────────────────────
            b_lay.addWidget(self._section_label("QUICK PROMPTS"))
            qp_wrap = QtWidgets.QWidget()
            qp_wrap.setStyleSheet("background:transparent;")
            qp_lay = QtWidgets.QVBoxLayout(qp_wrap)
            qp_lay.setContentsMargins(0, 0, 0, 0)
            qp_lay.setSpacing(6)

            quick_prompts = [
                "Create an enemy AI that chases the player",
                "Create a door that opens when the player walks near it",
                "Create a health pickup that gives 25 health on overlap",
                "Create a turret that rotates toward the player every tick",
                "Create a timer that ends the game after 60 seconds",
            ]
            for qp in quick_prompts:
                btn = QtWidgets.QPushButton(f"  {qp}")
                btn.setObjectName("ghostBtn")
                btn.setStyleSheet(
                    btn.styleSheet() +
                    "QPushButton#ghostBtn { text-align: left; padding: 7px 12px; "
                    "border-radius: 8px; font-size: 12px; }"
                )
                btn.clicked.connect(lambda checked, t=qp: self.prompt_input.setPlainText(t))
                qp_lay.addWidget(btn)

            b_lay.addWidget(qp_wrap)
            b_lay.addStretch()
            root.addWidget(body)

        # ── Helpers ────────────────────────────────────────────────────────────
        @staticmethod
        def _section_label(text):
            lbl = QtWidgets.QLabel(text)
            lbl.setProperty("class", "section")
            lbl.setStyleSheet(
                "color: #475569; font-size: 10px; font-weight: 700; "
                "letter-spacing: 0.1em;"
            )
            return lbl

        def _toggle_key(self):
            if self.key_input.echoMode() == QtWidgets.QLineEdit.Password:
                self.key_input.setEchoMode(QtWidgets.QLineEdit.Normal)
                self._show_btn.setText("Hide")
            else:
                self.key_input.setEchoMode(QtWidgets.QLineEdit.Password)
                self._show_btn.setText("Show")

        # ── Settings persistence ───────────────────────────────────────────────
        def _load_settings(self):
            cfg = _load_cfg()
            key = cfg.get("api_key", "")
            if key:
                self.key_input.setText(key)
            saved = cfg.get("model", DEFAULT_MODEL_ID)
            for i in range(self.model_combo.count()):
                if self.model_combo.itemData(i) == saved:
                    self.model_combo.setCurrentIndex(i)
                    break

        def _save_settings(self, *_):
            cfg = _load_cfg()
            cfg["api_key"] = self.key_input.text().strip()
            mid = self.model_combo.currentData()
            if mid:
                cfg["model"] = mid
            _save_cfg(cfg)

        # ── Log helpers ────────────────────────────────────────────────────────
        def _emit_log(self, msg, color="#94a3b8"):
            self._log_sig.emit(msg, color)

        def _append_log(self, msg, color):
            self.log_view.append(f'<span style="color:{color};">{msg}</span>')
            sb = self.log_view.verticalScrollBar()
            sb.setValue(sb.maximum())

        # ── Generate ────────────────────────────────────────────────────────────
        def _on_generate(self):
            api_key  = self.key_input.text().strip()
            model_id = self.model_combo.currentData()
            prompt   = self.prompt_input.toPlainText().strip()

            if not api_key:
                self._emit_log("❌  No API key — paste your OpenRouter key above.", "#f87171")
                return
            if not model_id:
                self._emit_log("❌  Select a model from the dropdown at the top.", "#f87171")
                return
            if not prompt:
                self._emit_log("❌  Enter a prompt describing the Blueprint.", "#f87171")
                return

            self.gen_btn.setEnabled(False)
            self.gen_btn.setText("Generating…")

            self._emit_log("─" * 54, "#1e2d45")
            self._emit_log(f"📝  {prompt}", "#e2e8f0")
            self._emit_log(f"🤖  {model_id}", "#a855f7")
            self._emit_log("⏳  Calling OpenRouter…", "#64748b")

            threading.Thread(
                target=self._worker,
                args=(api_key, model_id, prompt),
                daemon=True,
                name="MCPBlueprint_Generate",
            ).start()

        def _worker(self, api_key, model_id, prompt):
            import urllib.request, urllib.error

            try:
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
                    raw = resp.read().decode("utf-8")

                data    = json.loads(raw)
                content = data["choices"][0]["message"]["content"].strip()

                # Strip markdown fences if model wrapped anyway
                if content.startswith("```"):
                    lines   = [l for l in content.split("\n") if not l.startswith("```")]
                    content = "\n".join(lines).strip()

                result   = json.loads(content)
                commands = result.get("commands", [])
                bp_name  = result.get("blueprint_name", "BP_Generated")

                self._emit_log(
                    f"✅  AI returned {len(commands)} commands → {bp_name}",
                    "#34d399",
                )

                if not commands:
                    self._emit_log("❌  No commands returned. Try rephrasing.", "#f87171")
                    self._done_sig.emit(False, "")
                    return

                # Execute on game thread
                holder     = {}
                done_event = threading.Event()

                def _execute():
                    try:
                        holder["r"] = blueprint_executor.execute_batch(commands)
                    except Exception:
                        holder["r"] = {
                            "success": False,
                            "error":   traceback.format_exc(),
                            "results": [],
                        }
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
                    self._emit_log(f"🎉  {bp_name} created — {ok}/{tot} commands OK", "#34d399")
                    self._emit_log(f"📂  Content Browser → /Game/MCP/{bp_name}", "#a855f7")
                    try:
                        import unreal
                        unreal.EditorAssetLibrary.sync_browser_to_objects(
                            [f"/Game/MCP/{bp_name}"]
                        )
                    except Exception:
                        pass
                else:
                    ok  = batch.get("succeeded", 0)
                    bad = batch.get("failed", 0)
                    self._emit_log(f"⚠️  Partial: {ok} ok, {bad} failed", "#fbbf24")
                    for r in batch.get("results", []):
                        if not r.get("success"):
                            self._emit_log(f"   ✗ {r.get('message', '?')}", "#f87171")

                self._done_sig.emit(batch.get("success", False), bp_name)

            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                self._emit_log(f"❌  HTTP {e.code}: {body[:300]}", "#f87171")
                self._done_sig.emit(False, "")
            except json.JSONDecodeError as exc:
                self._emit_log(f"❌  AI response not valid JSON: {exc}", "#f87171")
                self._done_sig.emit(False, "")
            except Exception:
                self._emit_log(f"❌  Error:\n{traceback.format_exc()}", "#f87171")
                self._done_sig.emit(False, "")

        def _on_done(self, success, bp_name):
            self.gen_btn.setEnabled(True)
            self.gen_btn.setText("⚡  Generate Blueprint")

    win = MCPWindow()
    return win


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def show():
    """
    Open (or bring to front) the MCP Blueprint Generator floating panel.
    Call from anywhere:
        import mcp_ui; mcp_ui.show()
    """
    global _window
    try:
        from PySide2 import QtWidgets
    except ImportError:
        try:
            from PySide6 import QtWidgets
        except ImportError:
            _fallback_log("PySide2/PySide6 not available in this Unreal installation.")
            _fallback_log("Use the Python console instead:")
            _fallback_log("  import ai_panel")
            _fallback_log("  ai_panel.set_key('sk-or-v1-...')")
            _fallback_log("  ai_panel.run('Create an enemy that chases the player')")
            return

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    if _window is None or not _window.isVisible():
        _window = _build_window()
        if _window:
            _window.show()
            _window.raise_()
            _window.activateWindow()
    else:
        _window.raise_()
        _window.activateWindow()


def _fallback_log(msg):
    try:
        import unreal
        unreal.log(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] {msg}")


def start():
    """Called automatically by init_unreal.py when the plugin loads."""
    _fallback_log("MCP Blueprint Generator v1.2.0 — opening UI panel…")
    show()
