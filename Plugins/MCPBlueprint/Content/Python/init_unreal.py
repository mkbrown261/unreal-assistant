"""
init_unreal.py — MCP Blueprint Generator v1.4.0
Auto-runs when Unreal Engine loads the MCPBlueprint plugin.

Compatible with UE 5.7.4 on macOS (Python 3.11).

Does NOT use:
  - unreal.call_on_game_thread  (does not exist in UE 5.7)
  - ToolMenuEntryScript subclassing at import time (use start() instead)
  - Qt / PySide6 / Tkinter (not available in stock UE Python)

The plugin registers a slate post-tick callback in mcp_ui.start(),
which fires once the editor is fully loaded. At that point:
  1. The ToolMenuEntryScript subclass is instantiated and registered —
     this adds 'MCP AI → Generate Blueprint with AI...' to the menu bar.
  2. The startup dialog opens automatically.

To reopen the dialog at any time:
  import mcp_ui; mcp_ui.show()

To generate without the dialog:
  import mcp_ui; mcp_ui.run("Create an enemy AI that chases the player")
"""
import sys
import os

# Add this plugin's Python folder to the module search path
_plugin_python_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_python_dir not in sys.path:
    sys.path.insert(0, _plugin_python_dir)

# Import and start the plugin
import mcp_ui
mcp_ui.start()
