"""
blueprint_executor.py — MCP Blueprint Generator v2.0.0
Executes MCP Blueprint commands inside Unreal Engine 5.7+

Key fixes vs v1.7.x:
  - compile_blueprint is called BEFORE add_variable (prevents silent failures)
  - set_member_variable_default_value is attempted safely
  - execute_command() is the single public entry point used by mcp_server.py
  - All results are returned as human-readable strings (shown in chat, not Output Log)

UE 5.7 Python API limitations (documented honestly):
  - uk2node placement (arbitrary node insertion) is NOT exposed in Python
  - Pin wiring is NOT possible from Python
  - This module creates the Blueprint SHELL (asset, variables, function stubs)
  - Wiring instructions are included in the AI's chat reply
"""

import traceback

# ---------------------------------------------------------------------------
# Unreal import (graceful fallback for testing outside the editor)
# ---------------------------------------------------------------------------
try:
    import unreal
    _IN_UNREAL = True
except ImportError:
    unreal = None  # type: ignore
    _IN_UNREAL = False


# ---------------------------------------------------------------------------
# Parent class mapping
# ---------------------------------------------------------------------------

PARENT_CLASS_MAP = {
    "actor":                    "/Script/Engine.Actor",
    "character":                "/Script/Engine.Character",
    "pawn":                     "/Script/Engine.Pawn",
    "gamemodebase":             "/Script/Engine.GameModeBase",
    "gamemode":                 "/Script/Engine.GameModeBase",
    "playercontroller":         "/Script/Engine.PlayerController",
    "actorcomponent":           "/Script/Engine.ActorComponent",
    "scenecomponent":           "/Script/Engine.SceneComponent",
    "gameinstance":             "/Script/Engine.GameInstance",
    "gamestate":                "/Script/Engine.GameState",
    "playerstate":              "/Script/Engine.PlayerState",
    "hud":                      "/Script/Engine.HUD",
    "userwidget":               "/Script/UMG.UserWidget",
    "animinstance":             "/Script/Engine.AnimInstance",
    "blueprintfunctionlibrary": "/Script/Engine.BlueprintFunctionLibrary",
}

# ---------------------------------------------------------------------------
# Variable type helpers
# ---------------------------------------------------------------------------

def _make_pin_type(var_type: str):
    """Return an unreal.EdGraphPinType for the given type string."""
    vt = var_type.lower().strip()
    pc = unreal.PinContainerType.NONE
    pt = unreal.EdGraphPinType()
    pt.container_type = pc
    pt.is_reference    = False
    pt.is_const        = False

    if vt in ("bool", "boolean"):
        pt.pc_type = "bool"
    elif vt in ("int", "integer", "int32"):
        pt.pc_type = "int"
    elif vt in ("float", "double"):
        pt.pc_type = "real"
        pt.pc_sub_category_object = unreal.load_object(None, "/Script/CoreUObject.Float")
    elif vt in ("string", "str", "text"):
        pt.pc_type = "string"
    elif vt in ("name",):
        pt.pc_type = "name"
    elif vt in ("vector", "vec", "vector3"):
        pt.pc_type  = "struct"
        pt.pc_sub_category_object = unreal.load_object(None, "/Script/CoreUObject.Vector")
    elif vt in ("rotator", "rot", "rotation"):
        pt.pc_type  = "struct"
        pt.pc_sub_category_object = unreal.load_object(None, "/Script/CoreUObject.Rotator")
    elif vt in ("transform",):
        pt.pc_type  = "struct"
        pt.pc_sub_category_object = unreal.load_object(None, "/Script/CoreUObject.Transform")
    elif vt in ("object", "obj"):
        pt.pc_type = "object"
        pt.pc_sub_category_object = unreal.load_object(None, "/Script/CoreUObject.Object")
    elif vt in ("class",):
        pt.pc_type = "class"
        pt.pc_sub_category_object = unreal.load_object(None, "/Script/CoreUObject.Object")
    elif vt in ("soft_object", "softobject"):
        pt.pc_type = "softobject"
        pt.pc_sub_category_object = unreal.load_object(None, "/Script/CoreUObject.Object")
    elif vt in ("soft_class", "softclass"):
        pt.pc_type = "softclass"
        pt.pc_sub_category_object = unreal.load_object(None, "/Script/CoreUObject.Object")
    else:
        # Default: float
        pt.pc_type = "real"
        pt.pc_sub_category_object = unreal.load_object(None, "/Script/CoreUObject.Float")

    return pt


# ---------------------------------------------------------------------------
# Individual actions
# ---------------------------------------------------------------------------

def _load_bp(asset_path: str):
    """
    Reliably load a Blueprint asset. UE requires the full object path
    'Package.AssetName' for load_asset to succeed. A bare '/Game/MCP/BP_Foo'
    path causes 'Failed to find object None./Game/MCP/BP_Foo' warnings.
    """
    asset_path = asset_path.rstrip("/")
    # Extract the asset name from the path
    asset_name = asset_path.rsplit("/", 1)[-1]
    # Full object path: /Game/MCP/BP_Foo.BP_Foo
    full_path = f"{asset_path}.{asset_name}"
    bp = unreal.load_asset(full_path)
    if bp is not None:
        return bp
    # Fallback: bare path (works on some UE versions)
    bp = unreal.load_asset(asset_path)
    return bp


def _ensure_dir(path: str):
    try:
        if not unreal.EditorAssetLibrary.does_directory_exist(path):
            unreal.EditorAssetLibrary.make_directory(path)
    except Exception:
        pass


def _create_blueprint(cmd: dict) -> str:
    name        = cmd.get("name", "BP_New")
    path        = cmd.get("path", "/Game/MCP").rstrip("/")
    parent_key  = cmd.get("parent_class", "Actor").lower()
    parent_path = PARENT_CLASS_MAP.get(parent_key,
                  cmd.get("parent_class", "/Script/Engine.Actor"))

    asset_path = f"{path}/{name}"
    _ensure_dir(path)

    # Check if already exists — use full object path to avoid spurious warnings
    existing = _load_bp(asset_path)
    if existing and isinstance(existing, unreal.Blueprint):
        return f"Already exists: {asset_path}"

    parent_class = unreal.load_class(None, parent_path)
    if not parent_class:
        parent_class = unreal.Actor.static_class()

    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", parent_class)

    tools = unreal.AssetToolsHelpers.get_asset_tools()
    bp = tools.create_asset(name, path, unreal.Blueprint, factory)
    if not bp:
        raise RuntimeError(f"Failed to create Blueprint at {asset_path}")

    # Initial compile so the asset is in a valid state for variable addition
    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    except Exception as e:
        pass  # Non-fatal; some setups require a save first
    unreal.EditorAssetLibrary.save_asset(asset_path)
    return f"Created {asset_path}"


def _compile_blueprint(cmd: dict) -> str:
    path = cmd.get("path", "").rstrip("/")
    if not path:
        raise ValueError("compile_blueprint requires 'path'")
    bp = _load_bp(path)
    if not bp:
        raise RuntimeError(f"Blueprint not found: {path}")
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    unreal.EditorAssetLibrary.save_asset(path)
    return f"Compiled {path}"


def _add_variable(cmd: dict) -> str:
    bp_path     = cmd.get("blueprint_path", "").rstrip("/")
    var_name    = cmd.get("var_name", "")
    var_type    = cmd.get("var_type", "float")
    default_val = cmd.get("default_value", None)

    if not bp_path or not var_name:
        raise ValueError("add_variable requires 'blueprint_path' and 'var_name'")

    # Use full object path — bare paths cause "Failed to find object" spam
    bp = _load_bp(bp_path)
    if not bp:
        raise RuntimeError(f"Blueprint not found: {bp_path}")

    # Compile first — some UE versions silently drop variables without this
    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    except Exception:
        pass

    pin_type = _make_pin_type(var_type)
    ok = unreal.BlueprintEditorLibrary.add_member_variable(bp, var_name, pin_type)
    if not ok:
        raise RuntimeError(f"add_member_variable returned False for '{var_name}'")

    # Attempt to set default value (best-effort; may not work for all types)
    if default_val is not None:
        try:
            unreal.BlueprintEditorLibrary.set_member_variable_default_value(
                bp, var_name, str(default_val))
        except Exception:
            pass  # Default value not critical

    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    unreal.EditorAssetLibrary.save_asset(bp_path)
    return f"Added variable '{var_name}' ({var_type}) to {bp_path}"


def _add_function(cmd: dict) -> str:
    bp_path       = cmd.get("blueprint_path", "").rstrip("/")
    function_name = cmd.get("function_name", "")

    if not bp_path or not function_name:
        raise ValueError("add_function requires 'blueprint_path' and 'function_name'")

    bp = _load_bp(bp_path)
    if not bp:
        raise RuntimeError(f"Blueprint not found: {bp_path}")

    unreal.BlueprintEditorLibrary.add_function_graph(bp, function_name)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    unreal.EditorAssetLibrary.save_asset(bp_path)
    return f"Added function '{function_name}' to {bp_path}"


def _blueprint_instructions(cmd: dict) -> str:
    """Legacy action — just return the instructions text (now shown in chat)."""
    instructions = cmd.get("instructions", "")
    return f"Instructions: {instructions[:80]}..." if len(instructions) > 80 else f"Instructions: {instructions}"


# No-ops for node/pin operations (Python cannot do these in UE 5.7)
def _noop_node(cmd: dict) -> str:
    action = cmd.get("action", "")
    return f"{action} skipped (Python cannot place nodes in UE 5.7 \u2014 see wiring instructions in chat)"


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_ACTIONS = {
    "create_blueprint":      _create_blueprint,
    "compile_blueprint":     _compile_blueprint,
    "add_variable":          _add_variable,
    "add_member_variable":   _add_variable,
    "add_function":          _add_function,
    "add_function_graph":    _add_function,
    "blueprint_instructions": _blueprint_instructions,
    # No-ops
    "add_node":              _noop_node,
    "connect_nodes":         _noop_node,
    "wire_pins":             _noop_node,
    "add_component":         _noop_node,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def execute_command(cmd: dict) -> str:
    """
    Execute a single MCP Blueprint command dict.
    Returns a human-readable result string.
    Raises on error.
    """
    if not _IN_UNREAL:
        return f"[stub] Would execute: {cmd.get('action', '?')}"

    action = cmd.get("action", "").lower()
    handler = _ACTIONS.get(action)
    if handler:
        return handler(cmd)
    else:
        return f"Unknown action '{action}' \u2014 skipped"


def execute_commands(commands: list) -> list:
    """
    Execute a list of command dicts.
    Returns list of (action, result_or_error) tuples.
    """
    results = []
    for cmd in commands:
        action = cmd.get("action", "?")
        try:
            r = execute_command(cmd)
            results.append((action, r, None))
        except Exception as exc:
            results.append((action, None, traceback.format_exc()))
    return results
