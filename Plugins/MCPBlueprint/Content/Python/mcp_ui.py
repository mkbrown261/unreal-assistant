"""
mcp_ui.py — MCP Blueprint Generator v3.0.0
Registers the "MCP AI" toolbar/menu entry in the Unreal Editor.

v3 behaviour:
  - The chat UI is now a DOCKED TAB inside Unreal Engine (SWebBrowser at localhost:8080/chat)
    registered by the C++ plugin as the "MCPBlueprintChat" tab.
  - show() invokes FGlobalTabmanager::TryInvokeTab via a console command.
  - Falls back to opening a system browser if the C++ plugin is not loaded.

The C++ module registers the tab and opens it automatically on startup.
This Python module just keeps the menu/toolbar entry so the user can re-open
the tab from the menus.
"""

import webbrowser

CHAT_URL = "http://localhost:8080/chat"

# Tab name registered in C++ (FMCPBlueprintModule::ChatTabName)
CPP_TAB_NAME = "MCPBlueprintChat"

_tick_handle     = None
_menu_registered = False
_ready           = False


# ---------------------------------------------------------------------------
# Open the docked chat tab (or fall back to system browser)
# ---------------------------------------------------------------------------

def show():
    """
    Open/focus the docked MCP chat tab inside Unreal Engine.
    Uses Python→C++ bridge via unreal.SystemLibrary.execute_console_command
    if available; otherwise opens the system browser as a fallback.
    """
    try:
        import unreal
        # The C++ plugin exposes OpenChatTab via a console command registered at startup.
        # If the C++ module is loaded the tab is already registered with FGlobalTabmanager
        # and this will focus (or create) it.
        unreal.SystemLibrary.execute_console_command(None, "MCPBlueprint.OpenChat")
        return
    except Exception:
        pass

    # Second try: invoke via Python if execute_console_command is unavailable
    try:
        import unreal
        # Try to find the subsystem that can invoke tabs (UE 5.4+)
        tab_manager = getattr(unreal, "GlobalTabmanager", None)
        if tab_manager:
            tab_manager.get().try_invoke_tab(CPP_TAB_NAME)
            return
    except Exception:
        pass

    # Final fallback: open in the system browser
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

        menus = unreal.ToolMenus.get()
        menu  = menus.find_menu("LevelEditor.MainMenu")
        if menu:
            entry = unreal.ToolMenuEntry(
                name="MCP_AI",
                type=unreal.MultiBlockType.MENU_ENTRY,
            )
            entry.set_label("🤖 MCP AI")
            entry.set_tool_tip("Open MCP Blueprint Generator (docked chat tab)")
            menu.add_menu_entry("MCP", entry)
            menus.refresh_all_widgets()

        # Also try to add a toolbar button
        toolbar = menus.find_menu("LevelEditor.LevelEditorToolBar.PlayToolBar")
        if not toolbar:
            toolbar = menus.find_menu("LevelEditor.LevelEditorToolBar")
        if toolbar:
            tb_entry = unreal.ToolMenuEntry(
                name="MCP_AI_ToolBar",
                type=unreal.MultiBlockType.TOOL_BAR_BUTTON,
            )
            tb_entry.set_label("🤖 MCP AI")
            tb_entry.set_tool_tip("Open MCP Blueprint Generator chat panel")
            toolbar.add_menu_entry("MCP", tb_entry)
            menus.refresh_all_widgets()

        _menu_registered = True
    except Exception as e:
        print(f"[MCPBlueprint] Menu registration warning: {e}")


# ---------------------------------------------------------------------------
# Editor tick — waits for editor ready, then registers menu
# (tab opening is handled by the C++ plugin automatically on startup)
# ---------------------------------------------------------------------------

_frame_counter = 0


def _on_tick(delta):
    """Per-frame callback. Runs registration once editor is fully loaded."""
    global _frame_counter, _ready

    _frame_counter += 1

    # Wait ~90 frames (~3 seconds at 30fps) before doing anything
    if _frame_counter < 90:
        return True

    if not _menu_registered:
        _register_menu()

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
        print("[MCPBlueprint] UI module ready (docked tab mode).")
    except ImportError:
        print("[MCPBlueprint] Running outside Unreal — UI tick not registered.")
