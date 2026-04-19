# MCP Blueprint Generator — Installation

## Requirements
- Unreal Engine 5.0 or later
- An OpenAI API key (get one free at https://platform.openai.com/api-keys)

---

## Step 1 — Copy the plugin folder into your project

Find your Unreal project folder (where your `.uproject` file is).
Inside it, create a folder called `Plugins` if one doesn't exist.
Copy the entire `MCPBlueprint` folder into `Plugins/`.

Result:
```
MyGame/
├── MyGame.uproject
└── Plugins/
    └── MCPBlueprint/         ← paste here
        ├── MCPBlueprint.uplugin
        └── Content/Python/
```

---

## Step 2 — Enable the plugin in Unreal

Open your project in Unreal Engine.
Go to **Edit → Plugins**, search for **"MCP Blueprint Generator"**, enable it, and restart the editor.

After restart, open the **Output Log** (Window → Output Log).
You should see:
```
[MCPBlueprint] MCP Blueprint Generator loaded.
[MCPBlueprint] No OpenAI key saved yet.
[MCPBlueprint] Set your key with: import ai_panel; ai_panel.set_key('sk-...')
```

---

## Step 3 — Enter your OpenAI key (once)

Open the **Output Log** panel → click the input box at the bottom (the Python console).
Type this, replacing the key with your real one:

```python
import ai_panel; ai_panel.set_key("sk-your-real-key-here")
```

Press Enter. The key is saved locally — you never need to enter it again.

---

## Step 4 — Generate a Blueprint

In the same Python console, type:

```python
import ai_panel; ai_panel.run("Create an enemy AI that chases the player and has 100 health")
```

Watch the Output Log. Within a few seconds:
- The Blueprint appears in your Content Browser under `/Game/MCP/`
- It is fully wired and compiled
- The Content Browser scrolls to it automatically

---

## Example prompts

```python
ai_panel.run("Create a door that opens when the player walks near it")
ai_panel.run("Create a health pickup that restores 25 health on overlap")
ai_panel.run("Create an enemy that patrols between two points")
ai_panel.run("Create a game mode that ends the game after 60 seconds")
```

---

## Troubleshooting

**Plugin doesn't appear in Plugin Browser**
→ Make sure the `MCPBlueprint` folder is directly inside `Plugins/`, not nested inside another folder.

**"No OpenAI key" error**
→ Run `import ai_panel; ai_panel.set_key("sk-...")` in the Python console.

**"OpenAI HTTP 401" error**
→ Your API key is invalid or expired. Generate a new one at https://platform.openai.com/api-keys

**Blueprint not appearing in Content Browser**
→ Check the Output Log for errors. Make sure your project has a `/Game/MCP/` folder (it's created automatically).

**Need help?**
→ Open an issue at https://github.com/mkbrown261/unreal-assistant/issues
