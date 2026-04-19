# MCP Blueprint Generator — Installation Guide
## Version 1.5.0 · UE 5.7.4 · macOS (Apple Silicon)

---

## Requirements
- Unreal Engine **5.3 – 5.7.4** (tested on 5.7.4 / macOS / Apple M4)
- A **free** OpenRouter API key → https://openrouter.ai/keys

---

## Install

1. **Copy** the entire `MCPBlueprint` folder into your project's `Plugins/` directory:
   ```
   YourGame/
   └── Plugins/
       └── MCPBlueprint/          ← put this here
           ├── MCPBlueprint.uplugin
           └── Content/Python/
               ├── init_unreal.py
               ├── mcp_ui.py
               └── blueprint_executor.py
   ```

2. In Unreal Editor: **Edit → Plugins → search "MCP"** → enable → **Restart**.

3. After restart, look for **"MCP AI"** in the Level Editor menu bar.

---

## First-time Setup

1. Click **MCP AI → Generate Blueprint with AI…**
2. A dialog asks for your **OpenRouter API key**:
   - Go to https://openrouter.ai/keys, create a free key.
   - Paste it (starts with `sk-or-v1-`).
3. Select a model (default: Claude Sonnet 4.5, recommended).
4. Describe your Blueprint in plain English.
5. Wait ~10-30 s — the Blueprint appears under **`/Game/MCP/`**.

---

## What's New in v1.5.0

### Bug Fixes
- **ZenLoader / FlushAsyncLoading crash — FIXED**
  All Unreal asset APIs now run on the **main game thread** via a
  permanent Slate tick queue (`_main_queue`).  Previously, blueprint
  commands were dispatched from a background thread using
  `unreal.call_on_game_thread`, which does **not exist** in UE 5.7.
  Calling editor APIs from the wrong thread caused:
  ```
  RuntimeError: The current loader 'ZenLoader' is unable to
  FlushAsyncLoading from the current thread
  ```
  This is now fixed: the HTTP fetch runs on a daemon thread (so the
  editor stays responsive), then posts the commands to `_main_queue`,
  which the Slate tick drains on the game thread every frame.

- **`/Game/MCP` directory creation — FIXED**
  `create_blueprint` now explicitly calls
  `EditorAssetLibrary.make_directory("/Game/MCP")` before every
  blueprint creation, preventing "package does not exist on disk" errors.

- **Parent class resolution — IMPROVED**
  Added `ActorComponent`, `SceneComponent`, `AIController`, `UserWidget`,
  `GameInstance`, and many more. The AI can now say
  `"parent_class": "ActorComponent"` and it will work.

### Previous Fixes (v1.4.0 — preserved)
- Menu click works reliably via `ToolMenuEntryScript.execute()` override.
- `@unreal.uclass()` classes defined at module level (not inside exec).
- No `unreal.MCPModelEnum` (removed — doesn't exist in any UE version).

---

## Console Commands

Open the **Output Log → Python console** and run any of these:

```python
import mcp_ui

# Open the dialog
mcp_ui.show()

# Set API key (if dialog didn't work)
mcp_ui.set_key("sk-or-v1-...")

# Generate directly without dialog
mcp_ui.run("Create a door that opens when the player walks near it")

# Change model
mcp_ui.set_model("gpt-4o")

# List all models
mcp_ui.list_models()

# Check current key and model
mcp_ui.status()
```

---

## Available AI Models

| # | Label | Model ID |
|---|-------|----------|
| 1 | claude-sonnet-4-5 **[RECOMMENDED]** | anthropic/claude-sonnet-4-5 |
| 2 | claude-opus-4-5 [most capable] | anthropic/claude-opus-4-5 |
| 7 | claude-haiku-4-5 [fastest] | anthropic/claude-haiku-4-5 |
| 9 | gemini-2-5-pro | google/gemini-2.5-pro |
| 13 | deepseek-r1 [reasoning] | deepseek/deepseek-r1 |
| 14 | gpt-4o | openai/gpt-4o |
| 15 | gpt-4o-mini [affordable] | openai/gpt-4o-mini |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `MCP AI` menu not visible | Wait 5-10 s for editor startup, or run `import mcp_ui; mcp_ui.show()` |
| Blueprint not in Content Browser | Check Output Log for errors; try `mcp_ui.run("same prompt")` again |
| HTTP 401 error | Regenerate your key at https://openrouter.ai/keys, then `mcp_ui.set_key("sk-or-v1-...")` |
| All 0 ok / N failed | Restart UE (this resets the Python state) — was the threading bug, fixed in v1.5.0 |
| `does_directory_exist` error | Plugin auto-creates `/Game/MCP`; if it still fails, create the folder manually in Content Browser |
| Dialog doesn't appear | Run in Python console: `import mcp_ui; mcp_ui.show()` |

---

## Support
- Issues: https://github.com/mkbrown261/unreal-assistant/issues
- GitHub: https://github.com/mkbrown261/unreal-assistant
