# MCP Blueprint — Installation Guide

## Option A: Install into a specific project (recommended)

1. Download the `MCPBlueprint` folder from GitHub Releases
2. Copy it into your project:
   ```
   YourProject/
   └── Plugins/
       └── MCPBlueprint/        ← paste here
           ├── MCPBlueprint.uplugin
           └── Source/...
   ```
3. Right-click your `.uproject` → **"Generate Visual Studio project files"**
4. Build in Visual Studio (Development Editor / Win64)
5. Open Unreal Editor → **Edit → Plugins → search "MCP Blueprint" → Enable → Restart**

The plugin now shows up in the Plugin Browser under **Developer Tools**.

---

## Option B: Install engine-wide (shows in ALL projects)

Copy the `MCPBlueprint` folder into:
```
C:\Program Files\Epic Games\UE_5.x\Engine\Plugins\Developer\MCPBlueprint\
```
Then rebuild and it appears in every project's Plugin Browser automatically.

---

## Verifying it works

Open the **Output Log** in Unreal Editor and look for:
```
[MCPBlueprint] MCP HTTP server ready → POST http://localhost:8080/unreal/execute
```

Test with:
```bash
curl http://localhost:8080/unreal/status
# → {"status":"ok","server":"MCPBlueprint","version":"1.0.0"}
```

---

## Why does it need compilation?

Unreal C++ plugins ship as source and must be compiled once for your specific engine version and OS.
After compiling, you can zip the folder (including `Binaries/`) and share it — recipients on the
same UE version + OS don't need to compile again.
