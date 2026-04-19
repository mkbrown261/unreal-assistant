# MCP Blueprint Generator v1.3.0 — Installation Guide

## Requirements
- Unreal Engine **5.3 or later** (tested on UE 5.7 / macOS / Apple M4)
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

After restarting the editor, wait a few seconds. You will see in the **Output Log**:

```
[MCPBlueprint] MCP Blueprint Generator v1.3.0 ready.
[MCPBlueprint] Editor ready — opening MCP Blueprint Generator...
```

A native **modal dialog** will appear asking for your OpenRouter API key.

**If it's your first time:**
1. Go to **https://openrouter.ai/keys** and create a free account.
2. Click **"Create Key"** and copy it (starts with `sk-or-v1-`).
3. Paste it into the dialog and click **OK**.

Your key is saved permanently — you only enter it once.

---

## Step 4 — Select a model and generate

After entering your key, the dialog walks you through:

1. **Model selection** — type a number (1–20) to pick an AI model, or press OK for the default (Claude Sonnet 4.5).
2. **Describe your Blueprint** — type in plain English what you want.
3. Click **OK** — watch the Output Log for progress.

Your Blueprint appears in the **Content Browser under `/Game/MCP/`** within seconds.

---

## Reopening the UI

To open the generator again at any time, use the **Output Log Python console**:

```python
import mcp_ui; mcp_ui.show()
```

---

## Console commands (power users)

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
| 7 | Claude Haiku 4.5 | Fastest |
| 9 | Gemini 2.5 Pro | Alternative |
| 14 | DeepSeek V3.2 | Cost-efficient |
| 19 | GPT-4o | OpenAI option |
| 20 | GPT-4o Mini | Most affordable |

---

## Example prompts

```python
mcp_ui.run("Create an enemy AI that chases the player and has 100 health")
mcp_ui.run("Create a door that opens when the player walks near it")
mcp_ui.run("Create a health pickup that restores 25 health on overlap")
mcp_ui.run("Create an enemy that patrols between two points")
mcp_ui.run("Create a game mode that ends the game after 60 seconds")
mcp_ui.run("Create a moving platform that loops back and forth")
mcp_ui.run("Create a collectible coin that disappears when picked up")
```

---

## Troubleshooting

**"MCPBlueprint is Incompatible" warning on startup**
→ This warning appeared in v1.2.0 because the plugin declared compatibility with UE 5.0.
  v1.3.0 fixes this — the plugin now declares compatibility with UE 5.3+.

**Dialog doesn't appear after restart**
→ Wait 5–10 seconds after the editor finishes loading.
→ If still no dialog, run in the Python console: `import mcp_ui; mcp_ui.show()`

**"No API key" error**
→ Run: `import mcp_ui; mcp_ui.set_key("sk-or-v1-your-key")`

**HTTP 401 error**
→ Your key is invalid or expired. Create a new one at https://openrouter.ai/keys

**Blueprint not in Content Browser**
→ Check the Output Log for errors.
→ The `/Game/MCP/` folder is created automatically on first use.

**Need help?**
→ https://github.com/mkbrown261/unreal-assistant/issues
