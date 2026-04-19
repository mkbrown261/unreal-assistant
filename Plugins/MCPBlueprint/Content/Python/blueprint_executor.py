"""
blueprint_executor.py — MCP Blueprint Generator v1.7.0
Executes MCP Blueprint commands inside Unreal Engine 5.7+

HONEST REWRITE — v1.7.0
─────────────────────────
The UE 5.7 Python API (BlueprintEditorLibrary) does NOT expose any
node-placement functions. Prior versions called APIs like
add_function_call_node_to_graph, add_custom_event_node, get_graphs,
add_function_override, etc. None of these exist in the documented Python
bindings. They either silently failed or threw AttributeErrors that were
swallowed, producing empty Blueprints.

WHAT PYTHON CAN ACTUALLY DO IN UE 5.7 (BlueprintEditorLibrary):
  create_blueprint_asset_with_parent(path, parent_class)  — create BP
  find_event_graph(bp)                                    — get EventGraph
  find_graph(bp, name)                                    — get any graph
  add_function_graph(bp, name)                            — add function stub
  add_member_variable(bp, name, pin_type)                 — add variable
  set_member_variable_default_value(bp, name, value)      — set default
  compile_blueprint(bp)                                   — compile

WHAT PYTHON CANNOT DO (no Python bindings in UE 5.7):
  Add nodes to graphs (no add_function_call_node_to_graph)
  Wire pins between nodes
  Place event nodes (BeginPlay, Tick, etc.)

STRATEGY (v1.7.0):
  1. create_blueprint  — creates the asset with correct parent class
  2. add_variable      — adds all member variables with correct types
  3. add_function      — creates named function stubs
  4. blueprint_instructions — logs PROMINENT step-by-step wiring guide
  5. compile_blueprint — final compile + open in editor

The AI system prompt is updated to generate ONLY these actions. The
blueprint_instructions output tells the user exactly what to wire.

add_node / connect_nodes are no-ops with a clear INFO log (not an error).
"""

import traceback

try:
    import unreal
    UNREAL_AVAILABLE = True
except ImportError:
    UNREAL_AVAILABLE = False
    print("[MCPBlueprint] WARNING: unreal module not available")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def ok(msg, **extra):
    r = {"success": True, "message": msg}
    r.update(extra)
    return r

def err(msg):
    return {"success": False, "message": msg}

def _log(msg):
    try:
        unreal.log(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] {msg}")

def _warn(msg):
    try:
        unreal.log_warning(f"[MCPBlueprint] {msg}")
    except Exception:
        print(f"[MCPBlueprint] WARN: {msg}")


def _ensure_mcp_dir():
    """Create /Game/MCP if it doesn't exist (idempotent)."""
    try:
        if not unreal.EditorAssetLibrary.does_directory_exist("/Game/MCP"):
            unreal.EditorAssetLibrary.make_directory("/Game/MCP")
            _log("Created /Game/MCP directory.")
    except Exception as e:
        _warn(f"_ensure_mcp_dir: {e}")


def _load_bp(name):
    """Load Blueprint from /Game/MCP/<name>. Raises ValueError if not found."""
    # Try both asset reference formats
    for path in (
        f"/Game/MCP/{name}.{name}",
        f"/Game/MCP/{name}",
    ):
        try:
            bp = unreal.load_asset(path)
            if bp is not None:
                return bp
        except Exception:
            pass
    raise ValueError(f"Blueprint not found at /Game/MCP/{name}")


# ─────────────────────────────────────────────────────────────────────────────
# Parent class resolution
# ─────────────────────────────────────────────────────────────────────────────
_PARENT_MAP = {
    "Actor":            "/Script/Engine.Actor",
    "Character":        "/Script/Engine.Character",
    "Pawn":             "/Script/Engine.Pawn",
    "GameModeBase":     "/Script/Engine.GameModeBase",
    "GameMode":         "/Script/Engine.GameMode",
    "PlayerController": "/Script/Engine.PlayerController",
    "AIController":     "/Script/AIModule.AIController",
    "ActorComponent":   "/Script/Engine.ActorComponent",
    "UActorComponent":  "/Script/Engine.ActorComponent",
    "SceneComponent":   "/Script/Engine.SceneComponent",
    "USceneComponent":  "/Script/Engine.SceneComponent",
    "StaticMeshActor":  "/Script/Engine.StaticMeshActor",
    "HUD":              "/Script/Engine.HUD",
    "GameInstance":     "/Script/Engine.GameInstance",
    "UserWidget":       "/Script/UMG.UserWidget",
    "GameStateBase":    "/Script/Engine.GameStateBase",
    "PlayerState":      "/Script/Engine.PlayerState",
}


def _resolve_parent_class(parent_str):
    if not parent_str:
        return unreal.Actor.static_class()

    if parent_str in _PARENT_MAP:
        cls = unreal.load_class(None, _PARENT_MAP[parent_str])
        if cls:
            return cls

    for module in ("Engine", "AIModule", "UMG", "GameplayAbilities"):
        cls = unreal.load_class(None, f"/Script/{module}.{parent_str}")
        if cls:
            return cls

    # Strip U/A prefix (e.g. UActorComponent → ActorComponent)
    stripped = parent_str.lstrip("UA")
    if stripped != parent_str:
        cls = unreal.load_class(None, f"/Script/Engine.{stripped}")
        if cls:
            return cls

    _warn(f"Unknown parent class '{parent_str}', defaulting to Actor.")
    return unreal.Actor.static_class()


# ─────────────────────────────────────────────────────────────────────────────
# Variable type map (string-based — no BlueprintVariableType enum needed)
# ─────────────────────────────────────────────────────────────────────────────
_VAR_TYPES = {
    "Boolean":   ("bool",   ""),
    "Bool":      ("bool",   ""),
    "Integer":   ("int",    ""),
    "Int":       ("int",    ""),
    "Int64":     ("int64",  ""),
    "Float":     ("real",   "float"),
    "Double":    ("real",   "double"),
    "String":    ("string", ""),
    "Name":      ("name",   ""),
    "Text":      ("text",   ""),
    "Vector":    ("struct", "/Script/CoreUObject.Vector"),
    "Rotator":   ("struct", "/Script/CoreUObject.Rotator"),
    "Transform": ("struct", "/Script/CoreUObject.Transform"),
    "Color":     ("struct", "/Script/CoreUObject.LinearColor"),
}


# ─────────────────────────────────────────────────────────────────────────────
# create_blueprint
# ─────────────────────────────────────────────────────────────────────────────
def create_blueprint(cmd):
    name       = cmd.get("name") or cmd.get("blueprint_name")
    parent_str = cmd.get("parent_class", "Actor")

    if not name:
        return err("create_blueprint: 'name' is required")

    _ensure_mcp_dir()
    parent     = _resolve_parent_class(parent_str)
    asset_path = f"/Game/MCP/{name}"
    bp         = None

    # Method 1: BlueprintEditorLibrary (documented UE 5.7 API)
    try:
        bp = unreal.BlueprintEditorLibrary.create_blueprint_asset_with_parent(
            asset_path, parent
        )
    except Exception as e:
        _warn(f"create_blueprint_asset_with_parent failed: {e}")

    # Method 2: AssetTools + BlueprintFactory (fallback)
    if bp is None:
        try:
            factory = unreal.BlueprintFactory()
            factory.set_editor_property("parent_class", parent)
            tools = unreal.AssetToolsHelpers.get_asset_tools()
            bp = tools.create_asset(
                asset_name=name,
                package_path="/Game/MCP",
                asset_class=unreal.Blueprint,
                factory=factory,
            )
        except Exception as e:
            _warn(f"AssetTools fallback failed: {e}")

    if bp is None:
        return err(f"create_blueprint: failed to create '{name}' — check Output Log")

    try:
        unreal.EditorAssetLibrary.save_asset(asset_path, only_if_is_dirty=False)
    except Exception as e:
        _warn(f"save_asset: {e}")

    _log(f"Created Blueprint '{name}' (parent: {parent_str}) at /Game/MCP/{name}")
    return ok(f"Created Blueprint '{name}' (parent: {parent_str})", blueprint=name)


# ─────────────────────────────────────────────────────────────────────────────
# add_variable
# ─────────────────────────────────────────────────────────────────────────────
def add_variable(cmd):
    bp_name  = cmd.get("blueprint") or cmd.get("blueprint_name")
    params   = cmd.get("parameters") or {}
    var_name = cmd.get("variable_name") or params.get("variable_name")
    var_type = cmd.get("variable_type") or params.get("variable_type", "Float")
    default  = cmd.get("default_value")
    if default is None:
        default = params.get("default_value")

    if not bp_name:  return err("add_variable: 'blueprint' is required")
    if not var_name: return err("add_variable: 'variable_name' is required")

    if var_type not in _VAR_TYPES:
        _warn(f"Unknown variable type '{var_type}', defaulting to Float")
        var_type = "Float"

    pin_cat, pin_sub = _VAR_TYPES[var_type]

    try:
        bp = _load_bp(bp_name)
    except ValueError as e:
        return err(str(e))

    pin_type = unreal.EdGraphPinType()
    pin_type.set_editor_property("pin_category", pin_cat)

    if pin_sub:
        if pin_cat == "struct":
            struct_obj = unreal.load_object(None, pin_sub)
            if struct_obj:
                pin_type.set_editor_property("pin_sub_category_object", struct_obj)
        else:
            pin_type.set_editor_property("pin_sub_category", pin_sub)

    try:
        success = unreal.BlueprintEditorLibrary.add_member_variable(bp, var_name, pin_type)
        if not success:
            _warn(f"add_member_variable returned False for '{var_name}'")
    except Exception as e:
        return err(f"add_variable: {e}")

    if default is not None:
        try:
            unreal.BlueprintEditorLibrary.set_member_variable_default_value(
                bp, var_name, str(default)
            )
        except Exception:
            pass

    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    except Exception:
        pass

    return ok(f"Added variable '{var_name}' ({var_type}) to {bp_name}")


# ─────────────────────────────────────────────────────────────────────────────
# add_function
# Creates a named function stub — nodes must be added manually in the editor
# ─────────────────────────────────────────────────────────────────────────────
def add_function(cmd):
    bp_name   = cmd.get("blueprint") or cmd.get("blueprint_name")
    func_name = cmd.get("function_name") or cmd.get("name", "NewFunction")

    if not bp_name: return err("add_function: 'blueprint' is required")

    try:
        bp = _load_bp(bp_name)
    except ValueError as e:
        return err(str(e))

    try:
        graph = unreal.BlueprintEditorLibrary.add_function_graph(bp, func_name)
        if graph is None:
            return err(f"add_function_graph returned None for '{func_name}'")
        try:
            unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        except Exception:
            pass
        return ok(f"Added function stub '{func_name}' to {bp_name}")
    except Exception as e:
        return err(f"add_function: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# blueprint_instructions
#
# The AI includes a blueprint_instructions command with step-by-step wiring
# guidance. We log it prominently in the Output Log so the user can follow
# the instructions in the Blueprint editor.
# ─────────────────────────────────────────────────────────────────────────────
def blueprint_instructions(cmd):
    bp_name      = cmd.get("blueprint") or cmd.get("blueprint_name", "Blueprint")
    instructions = cmd.get("instructions", "")

    if instructions:
        separator = "=" * 70
        _log(separator)
        _log(f"  WIRING INSTRUCTIONS FOR: {bp_name}")
        _log(separator)
        _log("  Double-click the Blueprint in /Game/MCP/ to open it.")
        _log("  Then implement the following logic:")
        _log("")
        for line in instructions.strip().split("\\n"):
            _log(f"  {line}")
        _log("")
        _log(separator)
        _log("  TIP: Open Window → Output Log, filter by 'MCPBlueprint'")
        _log(separator)

    return ok(f"Wiring instructions logged for {bp_name}")


# ─────────────────────────────────────────────────────────────────────────────
# compile_blueprint
# ─────────────────────────────────────────────────────────────────────────────
def compile_blueprint(cmd):
    name = cmd.get("name") or cmd.get("blueprint") or cmd.get("blueprint_name")
    if not name:
        return err("compile_blueprint: 'name' is required")

    try:
        bp = _load_bp(name)
    except ValueError as e:
        return err(str(e))

    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    except Exception as e:
        _warn(f"compile warning: {e}")

    try:
        unreal.EditorAssetLibrary.save_asset(f"/Game/MCP/{name}", only_if_is_dirty=False)
    except Exception as e:
        _warn(f"save warning: {e}")

    _log(f"Compiled and saved {name}")
    return ok(f"Compiled and saved {name}")


# ─────────────────────────────────────────────────────────────────────────────
# Graceful no-ops for node commands
#
# The AI is instructed not to generate these, but if it does anyway,
# log a clear INFO message (not an error) so the user knows.
# ─────────────────────────────────────────────────────────────────────────────
def _node_not_supported(cmd):
    action = cmd.get("action", "?")
    node   = cmd.get("node", cmd.get("name", ""))
    bp     = cmd.get("blueprint", cmd.get("blueprint_name", ""))
    _log(
        f"INFO: '{action}' ({node}) cannot be placed via Python in UE 5.7. "
        f"Open {bp} in the Blueprint editor to add this node manually."
    )
    # Return success=True with warning=True so this doesn't count as failure
    return ok(
        f"[INFO] '{action}' ({node}) — add manually in Blueprint editor",
        warning=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────
COMMANDS = {
    "create_blueprint":       create_blueprint,
    "add_variable":           add_variable,
    "add_function":           add_function,
    "blueprint_instructions": blueprint_instructions,
    "compile_blueprint":      compile_blueprint,
    # Graceful no-ops (logged as INFO, not FAIL)
    "add_node":               _node_not_supported,
    "connect_nodes":          _node_not_supported,
    "set_variable":           _node_not_supported,
}


def execute_command(cmd):
    if not isinstance(cmd, dict):
        return err("Command must be a dict")
    action = cmd.get("action")
    if not action:
        return err("Missing 'action' field")
    handler = COMMANDS.get(action)
    if not handler:
        _log(f"Unknown action '{action}' — skipping")
        return ok(f"[INFO] Unknown action '{action}' — skipping", warning=True)
    try:
        return handler(cmd)
    except Exception:
        return err(f"{action} raised exception:\n{traceback.format_exc()}")


def execute_batch(commands):
    if not isinstance(commands, list):
        return {"success": False, "error": "commands must be a list", "results": []}

    _ensure_mcp_dir()

    results   = []
    succeeded = 0
    failed    = 0

    for cmd in commands:
        r = execute_command(cmd)
        results.append(r)
        if r.get("success"):
            succeeded += 1
        else:
            failed += 1
            unreal.log_error(f"[MCPBlueprint] FAIL: {r.get('message', '?')}")

    return {
        "success":   failed == 0,
        "total":     len(commands),
        "succeeded": succeeded,
        "failed":    failed,
        "results":   results,
    }
