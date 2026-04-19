"""
mcp_ui.py — MCP Blueprint Generator v2.0.0
Registers the "MCP AI" toolbar/menu entry in the Unreal Editor.
Opens the chat UI in the system browser at http://localhost:8080/chat.

The entire chat interface lives in the browser — no modal dialogs,
no Output Log instructions. This module's only job is to keep the
menu entry registered and open the browser on demand.
"""

import webbrowser

CHAT_URL = "http://localhost:8080/chat"

# Tick handle for Slate post-tick callback
_tick_handle    = None
_menu_registered = False
_ready           = False       # True once editor fully loaded


# ---------------------------------------------------------------------------
# Open the chat panel in the system browser
# ---------------------------------------------------------------------------

def show():
    """Open the MCP chat UI in the system browser."""
    webbrowser.open(CHAT_URL)


# ---------------------------------------------------------------------------
# Menu / toolbar registration
# ---------------------------------------------------------------------------

def _register_menu():
    """Register 'MCP AI' in the Level Editor menu bar (runs once)."""
    global _menu_registered
    if _menu_registered:
        return
    try:
        import unreal

        class _MCPMenuEntry(unreal.ToolMenuEntryScript):
            @unreal.ufunction(override=True)
            def execute(self, context):
                show()

            @unreal.ufunction(override=True)
            def get_label(self, context):
                return "🤖 MCP AI"

            @unreal.ufunction(override=True)
            def get_tool_tip(self, context):
                return "Open MCP Blueprint Generator chat panel"

        menus = unreal.ToolMenus.get()
        menu  = menus.find_menu("LevelEditor.MainMenu")
        if menu:
            entry = unreal.ToolMenuEntry(
                name="MCP_AI",
                type=unreal.MultiBlockType.MENU_ENTRY,
            )
            entry.set_label("🤖 MCP AI")
            entry.set_tool_tip("Open MCP Blueprint Generator")
            menu.add_menu_entry("MCP", entry)
            menus.refresh_all_widgets()

        # Also add a toolbar button
        toolbar = menus.find_menu("LevelEditor.LevelEditorToolBar.PlayToolBar")
        if not toolbar:
            toolbar = menus.find_menu("LevelEditor.LevelEditorToolBar")
        if toolbar:
            tb_entry = unreal.ToolMenuEntry(
                name="MCP_AI_ToolBar",
                type=unreal.MultiBlockType.TOOL_BAR_BUTTON,
            )
            tb_entry.set_label("🤖 MCP AI")
            tb_entry.set_tool_tip("Open MCP Blueprint Generator")
            toolbar.add_menu_entry("MCP", tb_entry)
            menus.refresh_all_widgets()

        _menu_registered = True
    except Exception as e:
        print(f"[MCPBlueprint] Menu registration warning: {e}")


# ---------------------------------------------------------------------------
# Editor tick — waits for editor ready, then registers menu + opens browser
# ---------------------------------------------------------------------------

_frame_counter = 0
_browser_opened = False


def _on_tick(delta):
    """Per-frame callback. Runs registration once editor is fully loaded."""
    global _frame_counter, _ready, _browser_opened

    _frame_counter += 1

    # Wait ~90 frames (~3 seconds at 30fps) before doing anything
    # so the editor is fully initialised.
    if _frame_counter < 90:
        return True

    if not _menu_registered:
        _register_menu()

    if not _browser_opened:
        _browser_opened = True
        try:
            # Brief delay so the server is definitely up before opening the tab
            import threading
            import time
            def _open_later():
                time.sleep(1.5)
                show()
            threading.Thread(target=_open_later, daemon=True).start()
        except Exception as e:
            print(f"[MCPBlueprint] Could not open browser: {e}")

    return True


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def start():
    """Called from init_unreal.py on plugin load. Installs the tick callback."""
    global _tick_handle
    try:
        import unreal
        if _tick_handle is None:
            _tick_handle = unreal.register_slate_post_tick_callback(_on_tick)
        print("[MCPBlueprint] UI module ready.")
    except ImportError:
        print("[MCPBlueprint] Running outside Unreal — UI tick not registered.")
