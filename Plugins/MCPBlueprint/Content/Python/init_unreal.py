"""
init_unreal.py — MCP Blueprint Generator
Auto-runs when Unreal loads the MCPBlueprint plugin.

Opens the MCP Blueprint Generator panel automatically.
The panel can be reopened at any time with:
  import mcp_ui; mcp_ui.show()
"""
import sys
import os

# Make the plugin's Python folder importable
sys.path.insert(0, os.path.dirname(__file__))

import mcp_ui
mcp_ui.start()
