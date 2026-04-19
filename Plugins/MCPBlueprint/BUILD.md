# Building MCPBlueprint C++ Plugin

## Version 3.0.0 · UE 5.7.4 · macOS (Apple Silicon / Intel)

This document explains how to compile the MCPBlueprint C++ plugin.
Compilation is required because the plugin uses `UK2Node_*` C++ APIs
that have no Python bindings — they are the only way to place and wire
Blueprint nodes programmatically inside Unreal Engine.

---

## What the C++ plugin provides

| Feature | Python (v2) | C++ (v3) |
|---------|------------|---------|
| Create Blueprint asset | ✅ | ✅ |
| Add variables | ✅ | ✅ |
| Place nodes in EventGraph | ❌ | ✅ |
| Wire node pins | ❌ | ✅ |
| Chat panel docked inside UE | ❌ (opens browser) | ✅ (SWebBrowser tab) |

---

## Prerequisites

- **Unreal Engine 5.3 – 5.7.4** installed via Epic Games Launcher
- **Xcode 15 or later** (Xcode 26 requires the fix below)
- A C++ Unreal project (not a Blueprint-only project)

---

## Step 1: Fix Xcode version gate (required for Xcode 16+ / 26+)

Epic hard-codes a maximum supported Xcode version. If you have Xcode 16+
or the macOS 26 beta (Xcode 26), you must raise this cap.

Edit:
```
/Users/Shared/Epic\ Games/UE_5.7/Engine/Config/Apple/Apple_SDK.json
```

Find `MaxVersion` and set it to a value higher than your Xcode version:
```json
"MaxVersion": "26.9.0"
```

Then add your Xcode/LLVM version mapping to `AppleVersionToLLVMVersions`:
```json
{ "AppleVersion": "26.0.0", "LLVMVersion": "19.1.4" }
```

---

## Step 2: Add the plugin to a C++ Unreal project

Copy the entire `MCPBlueprint` folder into your project's `Plugins/` directory:

```
YourGame/
├── YourGame.uproject
├── Source/
└── Plugins/
    └── MCPBlueprint/          ← here
        ├── MCPBlueprint.uplugin
        ├── BUILD.md
        ├── Source/
        │   └── MCPBlueprint/
        │       ├── MCPBlueprint.Build.cs
        │       ├── Public/
        │       │   ├── MCPBlueprintModule.h
        │       │   ├── MCPServer.h
        │       │   └── BlueprintCommands.h
        │       └── Private/
        │           ├── MCPBlueprintModule.cpp
        │           ├── MCPServer.cpp
        │           └── BlueprintCommands.cpp
        └── Content/
            └── Python/
                ├── init_unreal.py
                ├── mcp_server.py
                ├── mcp_ui.py
                └── blueprint_executor.py
```

> ⚠️ The project **must** have C++ source (`Source/` folder with a `.Target.cs` file).
> If your project is Blueprint-only, right-click the `.uproject` in Finder and choose
> **"Generate Xcode Project"** — if no C++ source exists, add an empty C++ class first
> via **Tools → New C++ Class** inside the editor.

---

## Step 3: Compile — Option A (Xcode)

```bash
# Generate the Xcode project (from the project folder)
"/Users/Shared/Epic Games/UE_5.7/Engine/Build/BatchFiles/Mac/GenerateProjectFiles.sh" \
    -project="/path/to/YourGame/YourGame.uproject" \
    -game

# Open the generated .xcworkspace and press ⌘B (Build)
open YourGame.xcworkspace
```

---

## Step 3: Compile — Option B (command line, no Xcode GUI)

```bash
"/Users/Shared/Epic Games/UE_5.7/Engine/Build/BatchFiles/Mac/Build.sh" \
    UnrealEditor Mac Development \
    -Project="/path/to/YourGame/YourGame.uproject" \
    -WaitMutex \
    -NoHotReload
```

Replace `/path/to/YourGame/YourGame.uproject` with the actual path to your `.uproject`.

Build output goes to `YourGame/Plugins/MCPBlueprint/Binaries/Mac/`.
Expected output: `libUnrealEditor-MCPBlueprint.dylib`

---

## Step 4: Open the project

1. Double-click `YourGame.uproject` in Finder.
2. Unreal detects the compiled plugin and loads it.
3. The **MCP Blueprint AI** docked tab opens automatically.

If the tab doesn't open automatically, click the **🤖 MCP AI** toolbar button
or use **Window → MCP Blueprint AI**.

---

## Step 5: First-time setup (same as before)

1. The chat panel opens at `http://localhost:8080/chat` inside a docked tab.
2. Click ⚙️ **Settings** and enter your OpenRouter API key (`sk-or-v1-…`).
3. Get a free key at https://openrouter.ai/keys.
4. Type your Blueprint description and press **Send**.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "No viable C++ compiler found" | Install Xcode from App Store + run `xcode-select --install` |
| "Unsupported Apple SDK / Xcode version" | Apply the `Apple_SDK.json` fix in Step 1 |
| Plugin tab doesn't appear | Check Output Log for `[MCPBlueprint]` lines; ensure plugin is enabled in Edit → Plugins |
| TCP server not starting (port 55557 in use) | `lsof -i :55557` and kill the conflicting process |
| Node placement failing | Ensure your project has C++ source compiled; Blueprint-only projects can't load the C++ module |
| `libUnrealEditor-MCPBlueprint.dylib` not found | Run the Build step again; check for compile errors in Xcode |

---

## Reverting to v2 (Python-only, no compilation)

If you don't want to compile, download the v2.0.1 release:
https://github.com/mkbrown261/unreal-assistant/releases/tag/v2.0.1

v2 creates Blueprint shells (variables, function stubs) and provides wiring
instructions in the chat, but cannot place or wire nodes automatically.
