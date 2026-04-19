# MCP Blueprint Generator — Installation Guide
## Version 1.7.0 · UE 5.7.4 · macOS (Apple Silicon)

---

## Requirements
- Unreal Engine **5.3 – 5.7.4** (tested on 5.7.4 / macOS / Apple M4)
- A **free** OpenRouter API key → https://openrouter.ai/keys

---

## Install

1. **Delete** any old `MCPBlueprint` folder from `Plugins/` first.

2. **Copy** the `MCPBlueprint` folder into your project's `Plugins/` directory:
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

3. In Unreal Editor: **Edit → Plugins → search "MCP"** → Enable → **Restart**.

4. After restart, look for **"MCP AI"** in the Level Editor menu bar (give it 5–10 s).

---

## First-time Setup

1. Click **MCP AI → Generate Blueprint with AI…**
2. A dialog asks for your **OpenRouter API key**:
   - Go to https://openrouter.ai/keys, create a free account, click **Create Key**.
   - Paste it (starts with `sk-or-v1-`).
3. Select an AI model (default: Claude Sonnet 4.5).
4. Describe your Blueprint in plain English.
5. Wait ~10–30 s — the Blueprint appears in **`/Game/MCP/`** in the Content Browser.
6. **Read the Output Log** for step-by-step wiring instructions.

---

## What's New in v1.7.0 — The Honest Fix

### Root Cause
Previous versions (v1.5.0, v1.6.0) generated `add_node` and `connect_nodes`
commands because those *sound* like they should work. **They don't exist** in
the UE 5.7 Python API. The `BlueprintEditorLibrary` has no node-placement
functions. Every `add_node`/`connect_nodes` call silently returned a warning
(not an error), so the batch reported "success" while the Blueprint stayed empty.

### What Changed
- **System prompt rewritten**: The AI now generates only commands that UE 5.7
  Python can actually execute:
  - `create_blueprint` — creates the Blueprint asset
  - `add_variable` — adds member variables with types and defaults
  - `add_function` — creates named function stubs (appear in My Blueprint panel)
  - `blueprint_instructions` — logs step-by-step wiring guidance to Output Log
  - `compile_blueprint` — compiles and saves

- **blueprint_instructions**: After generation, check the Output Log
  (Window → Output Log, filter by `MCPBlueprint`) for exact node names and
  wiring steps to implement in the Blueprint editor.

- **Dialog re-open bug fixed**: The `_dialog_open` flag was getting stuck `True`
  when the completion handler tried to re-open the panel from inside the panel's
  own `finally` block. Fixed by posting re-opens to `_main_queue`.

- **API key persistence fixed**: Related to the above — the panel was skipping
  the key-check step when `_dialog_open` was stuck. Now guaranteed to reset.

- **No more "EventGraph not found" errors**: Those errors were from the old
  `get_graphs()` calls which don't exist in UE 5.7. Removed entirely.

---

## What the Plugin Creates

For a prompt like *"Create an actor component that allows the player to fly"*:

**In the Content Browser (`/Game/MCP/`):**
- `BP_FlyComponent` — ActorComponent Blueprint with:
  - `FlySpeed` (Float) variable, default 600.0
  - `IsFlying` (Boolean) variable, default false
  - `ActivateFlight()` function stub
  - `DeactivateFlight()` function stub

**In the Output Log:**
```
[MCPBlueprint] ======================================================================
[MCPBlueprint]   WIRING INSTRUCTIONS FOR: BP_FlyComponent
[MCPBlueprint] ======================================================================
[MCPBlueprint]   Double-click the Blueprint in /Game/MCP/ to open it.
[MCPBlueprint]   FUNCTION: ActivateFlight
[MCPBlueprint]     1. Set IsFlying = True
[MCPBlueprint]     2. Get Owner → Cast To Character → Get Character Movement
[MCPBlueprint]     3. Set Movement Mode = Flying
[MCPBlueprint]     4. Set Max Fly Speed = FlySpeed
[MCPBlueprint]   FUNCTION: DeactivateFlight
[MCPBlueprint]     1. Set IsFlying = False
[MCPBlueprint]     2. Get Owner → Cast To Character → Get Character Movement
[MCPBlueprint]     3. Set Movement Mode = Walking
[MCPBlueprint]   TO ADD TO YOUR CHARACTER:
[MCPBlueprint]     1. Open your Character Blueprint
[MCPBlueprint]     2. Add Component → search 'BP_FlyComponent'
[MCPBlueprint]     3. Call ActivateFlight / DeactivateFlight on key press
[MCPBlueprint] ======================================================================
```

---

## Console Commands

Open **Window → Output Log → Python console** and run:

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
| `MCP AI` menu not visible | Wait 5–10 s, then run `import mcp_ui; mcp_ui.show()` |
| Dialog doesn't appear | Run `import mcp_ui; mcp_ui.show()` in the Python console |
| API key asked every time | Run `mcp_ui.status()` to check config path; key is at `~/.mcp_blueprint_config.json` |
| Blueprint not in Content Browser | Check Output Log — run `mcp_ui.run("same prompt")` to retry |
| Blueprint has no nodes | This is expected! Python cannot add nodes. Follow wiring instructions in Output Log. |
| HTTP 401 error | Regenerate key at https://openrouter.ai/keys → `mcp_ui.set_key("sk-or-v1-...")` |
| ZenLoader crash | Fixed in v1.5.0. If still occurring, restart UE and try again. |
| `does_directory_exist` error | Plugin auto-creates `/Game/MCP`; if it still fails, create it manually in Content Browser |

---

## Support
- Issues: https://github.com/mkbrown261/unreal-assistant/issues
- GitHub: https://github.com/mkbrown261/unreal-assistant
