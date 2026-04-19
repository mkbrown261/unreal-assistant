"""
init_unreal.py
Unreal Engine automatically executes this file when the plugin is enabled.
(Any file named init_unreal.py inside a plugin's Python/ folder is auto-run.)

This starts the MCP HTTP server so it's ready as soon as the editor loads.
"""

import mcp_server

# Start the HTTP server on port 8080 automatically
mcp_server.start(8080)
