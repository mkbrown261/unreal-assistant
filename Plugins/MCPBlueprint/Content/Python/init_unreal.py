"""
init_unreal.py — MCP Blueprint Generator v2.0.0
Auto-runs when Unreal Engine loads the MCPBlueprint plugin.

On load:
  1. Adds the plugin Python directory to sys.path
  2. Starts the HTTP server on port 8080  (mcp_server.start)
  3. Registers the editor menu / toolbar entry  (mcp_ui.start)
  4. After ~3 seconds, opens  http://localhost:8080/chat  in the system browser

No Output Log walls of text. The chat panel is the entire UI.

Useful console commands while developing:
  python init_unreal.py            -- reload everything
  import mcp_ui; mcp_ui.show()    -- re-open the browser tab
  import mcp_server; mcp_server.stop(); mcp_server.start()  -- restart server
"""

import sys
import os

# ---- Ensure this directory is on sys.path --------------------------------
_plugin_python_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_python_dir not in sys.path:
    sys.path.insert(0, _plugin_python_dir)

# ---- Start HTTP server ---------------------------------------------------
import mcp_server
mcp_server.start()

# ---- Register menu entry + open browser tab after editor is ready -------
import mcp_ui
mcp_ui.start()
