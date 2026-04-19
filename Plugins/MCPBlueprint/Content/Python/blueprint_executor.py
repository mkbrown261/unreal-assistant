"""
blueprint_executor.py
Executes structured MCP Blueprint commands inside Unreal Engine using the
built-in Python scripting API (unreal module).

Supported commands:
  create_blueprint   - Create a new Blueprint asset under /Game/MCP/
  add_node           - Add a node to the Blueprint's EventGraph
  connect_nodes      - Connect two nodes by pin name
  add_variable       - Add a typed member variable
  set_variable       - Set a variable's default value
  compile_blueprint  - Compile the Blueprint
"""

import json
import traceback

try:
    import unreal
    UNREAL_AVAILABLE = True
except ImportError:
    UNREAL_AVAILABLE = False
    print("[MCPBlueprint] WARNING: unreal module not found — running outside Unreal Engine")


# ── Helpers ───────────────────────────────────────────────────────────────────

def ok(msg, **extra):
    result = {"success": True, "message": msg}
    result.update(extra)
    return result

def err(msg):
    return {"success": False, "message": msg}

def load_blueprint(name):
    """Load a UBlueprint asset by name from /Game/MCP/<name>."""
    path = f"/Game/MCP/{name}.{name}"
    bp = unreal.load_asset(path)
    if bp is None:
        raise ValueError(f"Blueprint not found: {path}")
    return bp

def get_event_graph(bp):
    """Return the EventGraph UEdGraph from a blueprint."""
    graphs = unreal.BlueprintEditorLibrary.get_graphs(bp)
    for g in graphs:
        if g.get_name() == "EventGraph":
            return g
    return None


# ── Variable type map ─────────────────────────────────────────────────────────

VARIABLE_TYPES = {
    "Boolean":  (unreal.BlueprintVariableType.BOOL,      None),
    "Bool":     (unreal.BlueprintVariableType.BOOL,      None),
    "Integer":  (unreal.BlueprintVariableType.INT,       None),
    "Int":      (unreal.BlueprintVariableType.INT,       None),
    "Float":    (unreal.BlueprintVariableType.FLOAT,     None),
    "String":   (unreal.BlueprintVariableType.STRING,    None),
    "Vector":   (unreal.BlueprintVariableType.STRUCT,    "/Script/CoreUObject.Vector"),
    "Rotator":  (unreal.BlueprintVariableType.STRUCT,    "/Script/CoreUObject.Rotator"),
    "Transform":(unreal.BlueprintVariableType.STRUCT,    "/Script/CoreUObject.Transform"),
}


# ── Node name → Unreal function path map ─────────────────────────────────────

NODE_FUNCTION_MAP = {
    "Print String":              "/Script/Engine.KismetSystemLibrary:PrintString",
    "Delay":                     "/Script/Engine.KismetSystemLibrary:Delay",
    "Get Player Pawn":           "/Script/Engine.GameplayStatics:GetPlayerPawn",
    "Get Player Character":      "/Script/Engine.GameplayStatics:GetPlayerCharacter",
    "Get Distance To":           "/Script/Engine.Actor:GetDistanceTo",
    "Destroy Actor":             "/Script/Engine.Actor:K2_DestroyActor",
    "Play Sound at Location":    "/Script/Engine.GameplayStatics:PlaySoundAtLocation",
    "Spawn Emitter at Location": "/Script/Engine.GameplayStatics:SpawnEmitterAtLocation",
    "AI Move To":                "/Script/AIModule.AIBlueprintHelperLibrary:SimpleMoveToActor",
    "Simple Move To Actor":      "/Script/AIModule.AIBlueprintHelperLibrary:SimpleMoveToActor",
    "Get Actor Location":        "/Script/Engine.Actor:K2_GetActorLocation",
    "Set Actor Location":        "/Script/Engine.Actor:K2_SetActorLocation",
    "Get Actor Rotation":        "/Script/Engine.Actor:K2_GetActorRotation",
}

# Event node names → Unreal function names
EVENT_NODE_MAP = {
    "Event BeginPlay":            "ReceiveBeginPlay",
    "Event Tick":                 "ReceiveTick",
    "Event ActorBeginOverlap":    "ReceiveActorBeginOverlap",
    "Event ActorEndOverlap":      "ReceiveActorEndOverlap",
    "Event Hit":                  "ReceiveHit",
    "Event Destroyed":            "ReceiveDestroyed",
    "Event AnyDamage":            "ReceiveAnyDamage",
}


# ── Commands ──────────────────────────────────────────────────────────────────

def create_blueprint(cmd):
    """
    {"action":"create_blueprint","name":"BP_MyActor","parent_class":"Actor"}
    Creates a Blueprint asset at /Game/MCP/<name>
    """
    name = cmd.get("name") or cmd.get("blueprint_name")
    parent_class_name = cmd.get("parent_class") or (cmd.get("parameters") or {}).get("parent_class", "Actor")

    if not name:
        return err("create_blueprint: 'name' is required")

    # Resolve parent class
    parent_class = unreal.load_class(None, f"/Script/Engine.{parent_class_name}")
    if parent_class is None:
        parent_class = unreal.Actor.static_class()

    # Create asset
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    bp = asset_tools.create_asset(
        asset_name=name,
        package_path="/Game/MCP",
        asset_class=unreal.Blueprint,
        factory=unreal.BlueprintFactory()
    )

    if bp is None:
        return err(f"Failed to create Blueprint: {name}")

    # Set parent class
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", parent_class)

    unreal.EditorAssetLibrary.save_asset(f"/Game/MCP/{name}", only_if_is_dirty=False)
    return ok(f"Created Blueprint '{name}' (parent: {parent_class_name})", blueprint=name)


def add_node(cmd):
    """
    {"action":"add_node","blueprint":"BP_MyActor","node":"Event BeginPlay","id":"node_0","x":0,"y":0}
    Adds a node to the Blueprint's EventGraph.
    """
    bp_name  = cmd.get("blueprint") or cmd.get("blueprint_name")
    node_type = cmd.get("node") or cmd.get("node_type", "")
    node_id  = cmd.get("id") or cmd.get("node_id", "")
    params   = cmd.get("parameters") or cmd.get("params") or {}
    pos      = params.get("position", {}) if isinstance(params, dict) else {}
    x = cmd.get("x") or pos.get("x", 0)
    y = cmd.get("y") or pos.get("y", 0)

    if not bp_name:
        return err("add_node: 'blueprint' is required")
    if not node_type:
        return err("add_node: 'node' is required")

    bp = load_blueprint(bp_name)
    graph = get_event_graph(bp)
    if graph is None:
        return err(f"EventGraph not found in {bp_name}")

    node = None

    # ── Event nodes ───────────────────────────────────────────────────────────
    if node_type in EVENT_NODE_MAP:
        func_name = EVENT_NODE_MAP[node_type]
        node = unreal.BlueprintEditorLibrary.add_custom_event_node(
            bp, graph, func_name, x, y
        )
        # For built-in events, use override event node
        if node is None:
            node = unreal.BlueprintEditorLibrary.add_function_call_node_to_graph(
                bp, func_name, graph, x, y
            )

    # ── Branch ────────────────────────────────────────────────────────────────
    elif node_type == "Branch":
        node = unreal.BlueprintEditorLibrary.add_variable_get_node(bp, "Branch", graph, x, y)
        # Branch is a composite node; use the K2 schema directly
        node = None  # will fall through to function call below

        # Proper way: find the Branch function
        branch_func = unreal.load_object(None, "/Script/Engine.KismetSystemLibrary:Branch")
        if branch_func:
            node = unreal.BlueprintEditorLibrary.add_function_call_node_to_graph(
                bp, "/Script/Engine.KismetBoolLibrary:BoolBranch", graph, x, y
            )

    # ── Timeline ──────────────────────────────────────────────────────────────
    elif node_type == "Timeline":
        tl_name = params.get("name", "Timeline") if isinstance(params, dict) else "Timeline"
        node = unreal.BlueprintEditorLibrary.add_timeline_node(bp, tl_name, graph, x, y)

    # ── Cast To ───────────────────────────────────────────────────────────────
    elif node_type.startswith("Cast To"):
        target = node_type.replace("Cast To", "").strip()
        target_class = unreal.load_class(None, f"/Script/Engine.{target}")
        if target_class:
            node = unreal.BlueprintEditorLibrary.add_cast_node(bp, target_class, graph, x, y)

    # ── Known function nodes ───────────────────────────────────────────────────
    elif node_type in NODE_FUNCTION_MAP:
        func_path = NODE_FUNCTION_MAP[node_type]
        node = unreal.BlueprintEditorLibrary.add_function_call_node_to_graph(
            bp, func_path, graph, x, y
        )

    # ── Variable Set ──────────────────────────────────────────────────────────
    elif node_type == "Set Variable":
        var_name = params.get("variable", "") if isinstance(params, dict) else ""
        node = unreal.BlueprintEditorLibrary.add_variable_set_node(bp, var_name, graph, x, y)

    # ── Variable Get ──────────────────────────────────────────────────────────
    elif node_type == "Get Variable":
        var_name = params.get("variable", "") if isinstance(params, dict) else ""
        node = unreal.BlueprintEditorLibrary.add_variable_get_node(bp, var_name, graph, x, y)

    # ── Call Function: XYZ ────────────────────────────────────────────────────
    elif node_type.startswith("Call Function:"):
        func_name = node_type.replace("Call Function:", "").strip()
        node = unreal.BlueprintEditorLibrary.add_function_call_node_to_graph(
            bp, func_name, graph, x, y
        )

    if node is None:
        # Best-effort: log and continue — don't hard-fail the batch
        return ok(
            f"[WARN] Node '{node_type}' could not be placed automatically — add manually",
            node_id=node_id, node_type=node_type, warning=True
        )

    # Store node_id in comment for MCP tracking
    node.set_editor_property("node_comment", node_id)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)

    return ok(f"Added node '{node_type}' (id={node_id}) to {bp_name}", node_id=node_id, node_type=node_type)


def connect_nodes(cmd):
    """
    {"action":"connect_nodes","blueprint":"BP_MyActor",
     "from_node":"node_0","from_pin":"Then","to_node":"node_1","to_pin":"Execute"}
    Connects two nodes by their MCP string IDs (stored in node_comment).
    """
    bp_name  = cmd.get("blueprint") or cmd.get("blueprint_name")
    from_id  = cmd.get("from_node") or (cmd.get("connections") or {}).get("source", {}).get("node_id")
    from_pin = cmd.get("from_pin")  or (cmd.get("connections") or {}).get("source", {}).get("pin", "Then")
    to_id    = cmd.get("to_node")   or (cmd.get("connections") or {}).get("target", {}).get("node_id")
    to_pin   = cmd.get("to_pin")    or (cmd.get("connections") or {}).get("target", {}).get("pin", "Execute")

    if not bp_name:
        return err("connect_nodes: 'blueprint' is required")

    bp = load_blueprint(bp_name)
    graph = get_event_graph(bp)
    if graph is None:
        return err(f"EventGraph not found in {bp_name}")

    # Find nodes by their comment (which we set to node_id during add_node)
    nodes = graph.get_editor_property("nodes") or []
    from_node = next((n for n in nodes if n.get_editor_property("node_comment") == from_id), None)
    to_node   = next((n for n in nodes if n.get_editor_property("node_comment") == to_id),   None)

    if from_node is None:
        return err(f"connect_nodes: source node '{from_id}' not found")
    if to_node is None:
        return err(f"connect_nodes: target node '{to_id}' not found")

    # Find the pins by name
    from_pin_obj = next(
        (p for p in from_node.get_editor_property("pins") if p.get_editor_property("pin_name") == from_pin), None
    )
    to_pin_obj = next(
        (p for p in to_node.get_editor_property("pins") if p.get_editor_property("pin_name") == to_pin), None
    )

    if from_pin_obj is None:
        return err(f"connect_nodes: pin '{from_pin}' not found on node '{from_id}'")
    if to_pin_obj is None:
        return err(f"connect_nodes: pin '{to_pin}' not found on node '{to_id}'")

    success = unreal.BlueprintEditorLibrary.create_connection_between_pins(
        from_pin_obj, to_pin_obj
    )

    if not success:
        return err(f"connect_nodes: failed to connect {from_id}.{from_pin} → {to_id}.{to_pin}")

    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    return ok(f"Connected {from_id}.{from_pin} → {to_id}.{to_pin} in {bp_name}")


def add_variable(cmd):
    """
    {"action":"add_variable","blueprint":"BP_MyActor",
     "variable_name":"Health","variable_type":"Float","default_value":100.0}
    """
    bp_name  = cmd.get("blueprint") or cmd.get("blueprint_name")
    params   = cmd.get("parameters") or {}
    var_name = cmd.get("variable_name") or params.get("variable_name")
    var_type = cmd.get("variable_type") or params.get("variable_type", "Boolean")
    default  = cmd.get("default_value")
    if default is None:
        default = params.get("default_value")

    if not bp_name:  return err("add_variable: 'blueprint' is required")
    if not var_name: return err("add_variable: 'variable_name' is required")

    bp = load_blueprint(bp_name)

    if var_type not in VARIABLE_TYPES:
        return err(f"add_variable: unknown type '{var_type}'. Use Boolean, Integer, Float, String, Vector, Rotator, Transform")

    type_enum, struct_path = VARIABLE_TYPES[var_type]

    # Build pin type
    pin_type = unreal.EdGraphPinType()
    pin_type.set_editor_property("pin_category", var_type.lower() if var_type not in ("Vector","Rotator","Transform") else "struct")

    if struct_path:
        struct_obj = unreal.load_object(None, struct_path)
        pin_type.set_editor_property("pin_sub_category_object", struct_obj)

    unreal.BlueprintEditorLibrary.add_member_variable(bp, var_name, pin_type)

    # Set default value
    if default is not None:
        unreal.BlueprintEditorLibrary.set_member_variable_default_value(bp, var_name, str(default))

    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    return ok(f"Added variable '{var_name}' ({var_type}) to {bp_name}", variable=var_name, type=var_type)


def set_variable(cmd):
    """
    {"action":"set_variable","blueprint":"BP_MyActor","variable_name":"Health","value":"75"}
    Sets the default value of an existing variable.
    """
    bp_name  = cmd.get("blueprint") or cmd.get("blueprint_name")
    params   = cmd.get("parameters") or {}
    var_name = cmd.get("variable_name") or params.get("variable_name")
    value    = cmd.get("value")
    if value is None:
        value = params.get("value")

    if not bp_name:  return err("set_variable: 'blueprint' is required")
    if not var_name: return err("set_variable: 'variable_name' is required")
    if value is None: return err("set_variable: 'value' is required")

    bp = load_blueprint(bp_name)
    unreal.BlueprintEditorLibrary.set_member_variable_default_value(bp, var_name, str(value))
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    return ok(f"Set {bp_name}.{var_name} = {value}")


def compile_blueprint(cmd):
    """
    {"action":"compile_blueprint","name":"BP_MyActor"}
    Compiles the Blueprint and returns status.
    """
    name = cmd.get("name") or cmd.get("blueprint") or cmd.get("blueprint_name")
    if not name:
        return err("compile_blueprint: 'name' is required")

    bp = load_blueprint(name)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    unreal.EditorAssetLibrary.save_asset(f"/Game/MCP/{name}", only_if_is_dirty=False)
    return ok(f"Compiled and saved {name}")


# ── Dispatcher ────────────────────────────────────────────────────────────────

COMMANDS = {
    "create_blueprint":  create_blueprint,
    "add_node":          add_node,
    "connect_nodes":     connect_nodes,
    "add_variable":      add_variable,
    "set_variable":      set_variable,
    "compile_blueprint": compile_blueprint,
}

def execute_command(cmd):
    """Execute a single command dict. Returns a result dict."""
    if not isinstance(cmd, dict):
        return err("Command must be a JSON object")
    action = cmd.get("action")
    if not action:
        return err("Missing 'action' field")
    handler = COMMANDS.get(action)
    if not handler:
        return err(f"Unknown action: '{action}'")
    try:
        return handler(cmd)
    except Exception as e:
        return err(f"{action} raised an exception: {traceback.format_exc()}")

def execute_batch(commands):
    """Execute an ordered list of commands. Returns batch result dict."""
    if not isinstance(commands, list):
        return {"success": False, "error": "'commands' must be an array", "results": []}

    results = []
    succeeded = 0
    failed = 0

    for cmd in commands:
        result = execute_command(cmd)
        results.append(result)
        if result.get("success"):
            succeeded += 1
        else:
            failed += 1
            print(f"[MCPBlueprint] Command failed: {result.get('message')}")

    return {
        "success": failed == 0,
        "total": len(commands),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }
