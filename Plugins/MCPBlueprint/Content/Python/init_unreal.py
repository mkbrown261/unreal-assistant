"""
init_unreal.py
Unreal Engine automatically executes this file when the MCPBlueprint plugin is enabled.
(Any file named init_unreal.py inside a plugin's Content/Python/ folder is auto-run.)

This is the ONLY entry point. It starts the self-contained AI panel which:
  - Calls OpenAI directly from inside Unreal (no external server needed)
  - Lets the user type a prompt and generates a fully wired Blueprint
  - Saves the OpenAI API key locally so you only enter it once
"""

import ai_panel

# Start the AI panel — registers the Window menu entry and loads saved settings
ai_panel.start()
