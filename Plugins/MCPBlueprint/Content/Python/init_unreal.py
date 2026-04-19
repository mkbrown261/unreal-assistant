"""
init_unreal.py
Auto-executed by Unreal Engine when the MCPBlueprint plugin is enabled.

Opens a floating Qt window with:
  - Model switcher dropdown (Claude / Gemini / DeepSeek / GPT-4o)
  - API key input (auto-saved)
  - Prompt field + Generate button
  - Live output log

Reopen the window any time:
    import mcp_ui; mcp_ui.show()

Or use the Python console:
    import ai_panel
    ai_panel.set_key("sk-or-v1-...")
    ai_panel.run("Create an enemy that chases the player")
"""

import mcp_ui

mcp_ui.start()
