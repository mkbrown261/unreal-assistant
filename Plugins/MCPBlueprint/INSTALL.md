# MCP Blueprint Generator v1.4.0 — Installation Guide

## Requirements
- Unreal Engine **5.7.4** (tested on UE 5.7.4 / macOS / Apple Silicon)
- A FREE OpenRouter API key — get one at **https://openrouter.ai/keys**

---

## Step 1 — Copy the plugin into your project

1. Find your Unreal project folder (where your `.uproject` file is).
2. Create a `Plugins/` folder inside it if one doesn't already exist.
3. Copy the entire `MCPBlueprint` folder into `Plugins/`.

```
YourGame/
├── YourGame.uproject
└── Plugins/
    └── MCPBlueprint/         ← put it here
        ├── MCPBlueprint.uplugin
        ├── INSTALL.md
        └── Content/Python/
            ├── init_unreal.py
            ├── mcp_ui.py
            ├── blueprint_executor.py
            └── ai_panel.py
```

---

## Step 2 — Enable the plugin in Unreal

1. Open your project in Unreal Engine.
2. Go to **Edit → Plugins**, search for **"MCP Blueprint Generator"**, enable it.
3. Restart the editor when prompted.

---

## Step 3 — What to expect after restart

After restarting the editor, wait **3–5 seconds** for the editor to finish loading.

You will see in the **Output Log**:
```
[MCPBlueprint] MCP Blueprint Generator v1.4.0 starting...
[MCPBlueprint] Slate tick callback registered — menu will appear shortly.
[MCPBlueprint] ✔ 'MCP AI' menu registered in Level Editor menu bar.
[MCPBlueprint] Editor ready at tick N. Opening MCP Blueprint Generator...
```

A new **"MCP AI"** menu appears in the **Level Editor menu bar** (between Help and other menus).

A **native modal dialog** also opens automatically on startup. If you have a saved API key, it skips straight to model/prompt selection.

---

## Step 4 — Using the MCP AI menu

After the editor loads, you can open the generator any time by clicking:

**MCP AI → Generate Blueprint with AI...**

This button works **every time** — not just at startup.

The dialog walks you through three steps:
1. **API key** — paste your OpenRouter key (first time only, saved permanently).
2. **Model selection** — type a number 1–16 to pick an AI model, or press OK for the default (Claude Sonnet 4.5 ⭐).
3. **Blueprint description** — describe what you want in plain English, click OK.

Your Blueprint appears in the **Content Browser → `/Game/MCP/`** within seconds.

---

## Step 5 — Reopening the dialog

Three ways to open it:

| Method | How |
|--------|-----|
| Menu click | **MCP AI → Generate Blueprint with AI...** in the Level Editor |
| Python console | `import mcp_ui; mcp_ui.show()` |
| Direct generate | `import mcp_ui; mcp_ui.run("your description here")` |

---

## Console commands (power users)

In the **Output Log** Python console (switch to Python mode):

```python
import mcp_ui

# Set or change your API key
mcp_ui.set_key("sk-or-v1-your-key-here")

# Generate directly without the dialog
mcp_ui.run("Create an enemy AI that chases the player")
mcp_ui.run("Create a door that opens on overlap", model="gpt-4o")

# List all available models
mcp_ui.list_models()

# Check current settings
mcp_ui.status()
```

---

## Available AI Models

| # | Name | Best For |
|---|------|----------|
| 1 | Claude Sonnet 4.5 ⭐ | Best overall (recommended) |
| 2 | Claude Opus 4.5 | Most capable |
| 7 | Claude Haiku 4.5 | Fastest / cheapest Claude |
| 9 | Gemini 2.5 Pro | Google alternative |
| 10 | Gemini 2.5 Flash | Fast & cheap |
| 14 | GPT-4o | OpenAI option |
| 15 | GPT-4o Mini | Most affordable |

---

## Example prompts

```python
mcp_ui.run("Create an enemy AI that chases the player and has 100 health")
mcp_ui.run("Create a door that opens when the player walks near it")
mcp_ui.run("Create a health pickup that restores 25 health on overlap")
mcp_ui.run("Create an enemy that patrols between two points")
mcp_ui.run("Create a game mode that ends after 60 seconds")
mcp_ui.run("Create a moving platform that loops back and forth")
mcp_ui.run("Create a collectible coin that disappears when picked up")
```

---

## Troubleshooting

**MCP AI menu shows but clicking does nothing**
→ This was the v1.3.0 bug. v1.4.0 fixes it by using a `ToolMenuEntryScript` subclass
  with an `execute()` override — the only reliable way to trigger Python from a menu in UE 5.7.

**Dialog doesn't appear on startup**
→ Wait 5–10 seconds after the editor finishes loading.
→ If still nothing, click  **MCP AI → Generate Blueprint with AI...**  in the menu bar.
→ Or run in the Python console:  `import mcp_ui; mcp_ui.show()`

**"Incompatible plugin" warning**
→ v1.4.0 sets `EngineVersion` to `5.7.0` — this warning should not appear on UE 5.7.4.

**No API key error**
→ Run: `import mcp_ui; mcp_ui.set_key("sk-or-v1-your-key")`

**HTTP 401 error**
→ Your key is invalid or expired. Create a new one at https://openrouter.ai/keys

**Blueprint not in Content Browser**
→ Check the Output Log for Python errors.
→ The `/Game/MCP/` folder is created automatically on first use.

**Need help?**
→ https://github.com/mkbrown261/unreal-assistant/issues
