# MCP Blueprint Generator — Claude Desktop Setup

Connect Claude Desktop (or Cursor / Windsurf) to Unreal Engine 5.
Chat with Claude → it builds Blueprints inside your open UE project. No C++ compilation required.

---

## What you need

- Unreal Engine 5.x open with the MCPBlueprint plugin enabled
- Claude Desktop installed (free at claude.ai/download)
- Python 3 (already on Mac: `python3 --version`)
- An OpenRouter API key — free at [openrouter.ai/keys](https://openrouter.ai/keys)

---

## Step 1 — Install the plugin (Python-only version)

Download **MCPBlueprint-v2.0.1.zip** (no C++ compilation needed):
https://github.com/mkbrown261/unreal-assistant/releases/tag/v2.0.1

Extract → drop the `MCPBlueprint` folder into your project's `Plugins/` folder → enable in **Edit → Plugins → MCP Blueprint Generator** → restart UE.

---

## Step 2 — Download the MCP server script

Download `mcp_claude_server.py` from:
https://github.com/mkbrown261/unreal-assistant/releases/latest

Save it somewhere permanent, e.g. `~/Documents/mcp_claude_server.py`

---

## Step 3 — Add to Claude Desktop

Open (or create) the Claude Desktop config file:

**Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add this (replace the path and API key):

```json
{
  "mcpServers": {
    "unreal-blueprint": {
      "command": "python3",
      "args": ["/Users/masonbrown/Documents/mcp_claude_server.py"],
      "env": {
        "OPENROUTER_API_KEY": "sk-or-v1-YOUR_KEY_HERE",
        "UE_HOST": "localhost",
        "UE_PORT": "8080"
      }
    }
  }
}
```

Save the file → **quit and reopen Claude Desktop**.

---

## Step 4 — Use it

1. Open Unreal Engine with your project
2. Make sure the MCPBlueprint plugin is enabled (you should see `[MCPBlueprint] Server started` in the Output Log)
3. Open Claude Desktop — you'll see a 🔧 tools icon in the chat input
4. Ask Claude anything:

> "Create an enemy AI Blueprint that chases the player and has 100 HP"

> "Build a flying component with a FlySpeed variable and ActivateFlight function"

> "Make a door Blueprint that opens when the player walks near it"

Claude calls the UE tools, builds the Blueprint, and tells you what it created.
The Blueprint appears in **Content Browser → /Game/MCP/**.

---

## Choosing a model

Tell Claude which model to use for Blueprint generation:
> "Set the Blueprint model to DeepSeek V3"
> "Use Gemini 2.5 Pro for this Blueprint"

Or configure it once:
> "Set my OpenRouter key to sk-or-v1-... and use Claude Sonnet 4.5"

Available models: Claude Sonnet/Opus/Haiku, Gemini 2.5 Pro/Flash, DeepSeek V3/R1, GPT-4o/Mini, GPT-4.1

---

## Cursor / Windsurf setup

Add to `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "unreal-blueprint": {
      "command": "python3",
      "args": ["/path/to/mcp_claude_server.py"],
      "env": {
        "OPENROUTER_API_KEY": "sk-or-v1-YOUR_KEY_HERE"
      }
    }
  }
}
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Tools icon not showing in Claude Desktop | Quit Claude Desktop fully (Cmd+Q) and reopen |
| "Cannot reach Unreal Engine" | Open UE with the plugin enabled; check Output Log for `[MCPBlueprint] Server started → http://localhost:8080` |
| "No API key configured" | Ask Claude: "Set my OpenRouter key to sk-or-v1-..." |
| Blueprint not appearing in Content Browser | Refresh Content Browser (right-click → Refresh) |
| Port 8080 conflict | Change `UE_PORT` in Claude config to match your plugin's port |
