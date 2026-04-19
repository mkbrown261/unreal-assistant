"""
init_unreal.py — MCP Blueprint Generator v1.7.0
Auto-runs when Unreal Engine loads the MCPBlueprint plugin.

Compatible with UE 5.7.4 on macOS (Python 3.11).

What happens on load:
  1. This file is executed by the Unreal Python plugin.
  2. mcp_ui.start() is called.
  3. start() registers UE Python classes (ToolMenuEntryScript subclass).
  4. A permanent Slate post-tick callback is installed.
  5. The callback waits for the editor to fully load, then:
       a. Registers 'MCP AI' in the Level Editor menu bar.
       b. Opens the startup dialog (API key → model → prompt).
  6. The tick callback also drains the main-thread work queue every frame,
     ensuring Blueprint asset creation runs on the game thread (not the
     background HTTP thread) — no ZenLoader crashes.

To reopen the dialog:
  import mcp_ui; mcp_ui.show()

To generate without the dialog:
  import mcp_ui; mcp_ui.run("Create an enemy AI that chases the player")

To set your API key from the console:
  import mcp_ui; mcp_ui.set_key("sk-or-v1-...")

To check current configuration:
  import mcp_ui; mcp_ui.status()
"""

import sys
import os

# Ensure this plugin's Python directory is on the module search path
_plugin_python_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_python_dir not in sys.path:
    sys.path.insert(0, _plugin_python_dir)

# Start the plugin
import mcp_ui
mcp_ui.start()
