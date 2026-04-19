"""
init_unreal.py — MCP Blueprint Generator v1.3.0
Auto-runs when Unreal loads the MCPBlueprint plugin.

This file intentionally does NOT use:
  - unreal.call_on_game_thread  (does not exist in UE 5.7)
  - unreal.ToolMenuEntryScript subclassing at startup (fails in UE 5.7)
  - Qt / PySide6 / Tkinter (not available in stock UE Python)
  - threading with delayed calls (unreliable on macOS)

The UI opens via a registered slate tick callback in mcp_ui.start(),
which fires once after the editor finishes its startup sequence.

To reopen the UI at any time:
  import mcp_ui; mcp_ui.show()
"""
import sys
import os

# Add this plugin's Python folder to the module search path
_dir = os.path.dirname(__file__)
if _dir not in sys.path:
    sys.path.insert(0, _dir)

# Import and start the UI
import mcp_ui
mcp_ui.start()
