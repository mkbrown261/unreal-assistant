"""
blueprint_executor.py — MCP Blueprint Generator v1.6.0
Executes MCP Blueprint commands inside Unreal Engine 5.7+

KEY CHANGES IN v1.6.0
─────────────────────
• ACTOR COMPONENT GRAPH FIX: ActorComponent/SceneComponent blueprints do
  NOT have an "EventGraph".  They have function override graphs named after
  the event functions (e.g. "ReceiveBeginPlay", "ReceiveTick").
  _get_working_graph() now detects the parent class and picks the correct
  graph:
    - Actor/Character/Pawn/GameMode variants → "EventGraph"
    - ActorComponent/SceneComponent variants → "ReceiveBeginPlay" (or
      whichever event graph is requested), created via
      BlueprintEditorLibrary.add_function_override if not already present.

• All functions run on the MAIN GAME THREAD (dispatched by mcp_ui via
  _main_queue).  Never call from a background thread.

• Config path fix (in mcp_ui.py, not here) — stable ~/.mcp_blueprint_config.json.

UNCHANGED FROM v1.5.0
─────────────────────
• _ensure_mcp_dir() creates /Game/MCP before every batch.
• _resolve_parent_class() handles ActorComponent, SceneComponent, etc.
• String-based pin categories (no BlueprintVariableType enum).
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


def _ensure_mcp_dir():
    """Create /Game/MCP if missing."""
    try:
        if not unreal.EditorAssetLibrary.does_directory_exist("/Game/MCP"):
            unreal.EditorAssetLibrary.make_directory("/Game/MCP")
            unreal.log("[MCPBlueprint] Created /Game/MCP directory.")
    except Exception as e:
        unreal.log_warning(f"[MCPBlueprint] _ensure_mcp_dir: {e}")


def _load_bp(name):
    """Load Blueprint from /Game/MCP/<name>. Raises ValueError if missing."""
    path = f"/Game/MCP/{name}.{name}"
    bp = unreal.load_asset(path)
    if bp is None:
        try:
            bp = unreal.EditorAssetLibrary.load_asset(path)
        except Exception:
            pass
    if bp is None:
        raise ValueError(f"Blueprint not found at {path}")
    return bp


# ─────────────────────────────────────────────────────────────────────────────
# Parent class resolution
# ─────────────────────────────────────────────────────────────────────────────
_PARENT_CLASS_MAP = {
    "Actor":               "/Script/Engine.Actor",
    "Character":           "/Script/Engine.Character",
    "Pawn":                "/Script/Engine.Pawn",
    "GameModeBase":        "/Script/Engine.GameModeBase",
    "GameMode":            "/Script/Engine.GameMode",
    "PlayerController":    "/Script/Engine.PlayerController",
    "AIController":        "/Script/AIModule.AIController",
    "ActorComponent":      "/Script/Engine.ActorComponent",
    "UActorComponent":     "/Script/Engine.ActorComponent",
    "SceneComponent":      "/Script/Engine.SceneComponent",
    "USceneComponent":     "/Script/Engine.SceneComponent",
    "StaticMeshActor":     "/Script/Engine.StaticMeshActor",
    "PlayerCameraManager": "/Script/Engine.PlayerCameraManager",
    "HUD":                 "/Script/Engine.HUD",
    "GameInstance":        "/Script/Engine.GameInstance",
    "UserWidget":          "/Script/UMG.UserWidget",
    "Widget":              "/Script/UMG.UserWidget",
    "GameStateBase":       "/Script/Engine.GameStateBase",
    "PlayerState":         "/Script/Engine.PlayerState",
    "SpectatorPawn":       "/Script/Engine.SpectatorPawn",
    "DefaultPawn":         "/Script/Engine.DefaultPawn",
}

# Parent classes that are component types (have no EventGraph)
_COMPONENT_PARENTS = {
    "ActorComponent", "UActorComponent",
    "SceneComponent", "USceneComponent",
}


def _resolve_parent_class(parent_str):
    if not parent_str:
        return unreal.Actor.static_class()

    if parent_str in _PARENT_CLASS_MAP:
        cls = unreal.load_class(None, _PARENT_CLASS_MAP[parent_str])
        if cls:
            return cls

    for module in ("Engine", "AIModule", "UMG"):
        cls = unreal.load_class(None, f"/Script/{module}.{parent_str}")
        if cls:
            return cls

    stripped = parent_str.lstrip("UA")
    if stripped != parent_str:
        cls = unreal.load_class(None, f"/Script/Engine.{stripped}")
        if cls:
            return cls

    unreal.log_warning(f"[MCPBlueprint] Unknown parent class '{parent_str}', falling back to Actor.")
    return unreal.Actor.static_class()


def _is_component_bp(bp):
    """Return True if this Blueprint's parent is an ActorComponent/SceneComponent."""
    try:
        parent_class = bp.get_editor_property("parent_class")
        if parent_class is None:
            return False
        name = parent_class.get_name()
        # Check against known component base names
        component_bases = {"ActorComponent", "SceneComponent"}
        # Walk up the class hierarchy
        cls = parent_class
        for _ in range(10):
            if cls is None:
                break
            n = cls.get_name()
            if n in component_bases:
                return True
            try:
                cls = cls.get_super_class()
            except Exception:
                break
    except Exception:
        pass
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Graph resolution
#
# Actor/Character/Pawn → "EventGraph"
# ActorComponent/SceneComponent → function override graphs:
#   "ReceiveBeginPlay", "ReceiveTick", "ReceiveEndPlay", etc.
#
# For components, we use BlueprintEditorLibrary.add_function_override
# to create the override graph if it doesn't exist, then return it.
# ─────────────────────────────────────────────────────────────────────────────

# Maps the user-facing event name → function name used in component override
_COMPONENT_EVENT_FUNC_MAP = {
    "Event BeginPlay":              "ReceiveBeginPlay",
    "Event Tick":                   "ReceiveTick",
    "Event EndPlay":                "ReceiveEndPlay",
    "Event ComponentBeginOverlap":  "ReceiveBeginPlay",
    "Event InitializeComponent":    "ReceiveBeginPlay",
}


def _get_graphs(bp):
    """Return all graphs in a Blueprint."""
    try:
        return unreal.BlueprintEditorLibrary.get_graphs(bp) or []
    except Exception:
        return []


def _find_graph_by_name(bp, name):
    """Find a graph by name (case-insensitive)."""
    for g in _get_graphs(bp):
        if g.get_name().lower() == name.lower():
            return g
    return None


def _get_event_graph(bp):
    """
    Return the EventGraph for Actor-based blueprints.
    Returns None if not found (e.g. it's a component BP).
    """
    return _find_graph_by_name(bp, "EventGraph")


def _get_component_override_graph(bp, event_name):
    """
    For ActorComponent/SceneComponent blueprints:
    get or create the function override graph for the given event_name.

    event_name is the user-facing name like "Event BeginPlay".
    Returns the graph, or None on failure.
    """
    func_name = _COMPONENT_EVENT_FUNC_MAP.get(event_name, "ReceiveBeginPlay")

    # Check if the override graph already exists
    existing = _find_graph_by_name(bp, func_name)
    if existing:
        return existing

    # Create it via add_function_override
    try:
        unreal.BlueprintEditorLibrary.add_function_override(bp, func_name)
        # Now find it again
        return _find_graph_by_name(bp, func_name)
    except Exception as e:
        unreal.log_warning(f"[MCPBlueprint] add_function_override({func_name}) failed: {e}")

    # Last resort: return the first available graph
    graphs = _get_graphs(bp)
    if graphs:
        unreal.log_warning(f"[MCPBlueprint] Using first available graph: {graphs[0].get_name()}")
        return graphs[0]

    return None


def _get_working_graph(bp, node_type=""):
    """
    Return the correct working graph for adding nodes to this Blueprint.

    For Actor-based BPs: EventGraph.
    For Component BPs: the appropriate function override graph.
    """
    is_comp = _is_component_bp(bp)

    if not is_comp:
        graph = _get_event_graph(bp)
        if graph:
            return graph
        # Some blueprints may not have EventGraph yet — try any graph
        graphs = _get_graphs(bp)
        for g in graphs:
            if "event" in g.get_name().lower():
                return g
        if graphs:
            return graphs[0]
        return None
    else:
        # Component blueprint
        return _get_component_override_graph(bp, node_type)


# ─────────────────────────────────────────────────────────────────────────────
# Variable types
# ─────────────────────────────────────────────────────────────────────────────
VAR_TYPES = {
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

EVENT_MAP = {
    "Event BeginPlay":              "ReceiveBeginPlay",
    "Event Tick":                   "ReceiveTick",
    "Event ActorBeginOverlap":      "ReceiveActorBeginOverlap",
    "Event ActorEndOverlap":        "ReceiveActorEndOverlap",
    "Event Hit":                    "ReceiveHit",
    "Event Destroyed":              "ReceiveDestroyed",
    "Event AnyDamage":              "ReceiveAnyDamage",
    "Event EndPlay":                "ReceiveEndPlay",
    "Event ComponentBeginOverlap":  "ReceiveBeginPlay",
}

FUNC_MAP = {
    "Print String":              "/Script/Engine.KismetSystemLibrary:PrintString",
    "Delay":                     "/Script/Engine.KismetSystemLibrary:Delay",
    "Get Player Pawn":           "/Script/Engine.GameplayStatics:GetPlayerPawn",
    "Get Player Character":      "/Script/Engine.GameplayStatics:GetPlayerCharacter",
    "Destroy Actor":             "/Script/Engine.Actor:K2_DestroyActor",
    "Get Actor Location":        "/Script/Engine.Actor:K2_GetActorLocation",
    "Set Actor Location":        "/Script/Engine.Actor:K2_SetActorLocation",
    "Get Actor Rotation":        "/Script/Engine.Actor:K2_GetActorRotation",
    "AI Move To":                "/Script/AIModule.AIBlueprintHelperLibrary:SimpleMoveToActor",
    "Simple Move To Actor":      "/Script/AIModule.AIBlueprintHelperLibrary:SimpleMoveToActor",
    "Play Sound at Location":    "/Script/Engine.GameplayStatics:PlaySoundAtLocation",
    "Get Distance To":           "/Script/Engine.Actor:GetDistanceTo",
    "Set Timer by Function Name":"/Script/Engine.KismetSystemLibrary:SetTimerDelegate",
    "Get World Delta Seconds":   "/Script/Engine.KismetSystemLibrary:GetWorldDeltaSeconds",
    "Line Trace By Channel":     "/Script/Engine.KismetSystemLibrary:LineTraceSingle",
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

    parent = _resolve_parent_class(parent_str)

    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", parent)

    tools = unreal.AssetToolsHelpers.get_asset_tools()
    bp = tools.create_asset(
        asset_name=name,
        package_path="/Game/MCP",
        asset_class=unreal.Blueprint,
        factory=factory,
    )

    if bp is None:
        _ensure_mcp_dir()
        bp = tools.create_asset(
            asset_name=name,
            package_path="/Game/MCP",
            asset_class=unreal.Blueprint,
            factory=factory,
        )

    if bp is None:
        return err(f"create_blueprint: failed to create '{name}'")

    try:
        unreal.EditorAssetLibrary.save_asset(f"/Game/MCP/{name}", only_if_is_dirty=False)
    except Exception as e:
        unreal.log_warning(f"[MCPBlueprint] save_asset warning: {e}")

    is_comp = _is_component_bp(bp)
    if is_comp:
        # Pre-create the ReceiveBeginPlay and ReceiveTick graphs for components
        # so nodes can be added immediately without needing a separate add_node call
        for func_name in ("ReceiveBeginPlay", "ReceiveTick"):
            if not _find_graph_by_name(bp, func_name):
                try:
                    unreal.BlueprintEditorLibrary.add_function_override(bp, func_name)
                    unreal.log(f"[MCPBlueprint] Created override graph: {func_name}")
                except Exception as e:
                    unreal.log_warning(f"[MCPBlueprint] Could not create {func_name}: {e}")

        try:
            unreal.BlueprintEditorLibrary.compile_blueprint(bp)
            unreal.EditorAssetLibrary.save_asset(f"/Game/MCP/{name}", only_if_is_dirty=False)
        except Exception:
            pass

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

    if var_type not in VAR_TYPES:
        var_type = "Float"

    pin_cat, pin_sub = VAR_TYPES[var_type]

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
        unreal.BlueprintEditorLibrary.add_member_variable(bp, var_name, pin_type)
    except Exception as e:
        return err(f"add_variable: add_member_variable failed: {e}")

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
# add_node
# ─────────────────────────────────────────────────────────────────────────────
def add_node(cmd):
    bp_name   = cmd.get("blueprint") or cmd.get("blueprint_name")
    node_type = cmd.get("node") or cmd.get("node_type", "")
    node_id   = cmd.get("id") or cmd.get("node_id", "node_unknown")
    params    = cmd.get("parameters") or {}
    x = float(cmd.get("x", 0))
    y = float(cmd.get("y", 0))

    if not bp_name:   return err("add_node: 'blueprint' is required")
    if not node_type: return err("add_node: 'node' is required")

    try:
        bp = _load_bp(bp_name)
    except ValueError as e:
        return err(str(e))

    # Get the correct working graph for this blueprint type + event type
    graph = _get_working_graph(bp, node_type)
    if graph is None:
        return err(f"add_node: No usable graph found in '{bp_name}'. "
                   f"Tried EventGraph and component override graphs.")

    node = None

    try:
        # ── Event nodes ──────────────────────────────────────────────────────
        if node_type in EVENT_MAP:
            func_name = EVENT_MAP[node_type]

            # For component blueprints, the "event node" IS the function entry
            # of the override graph — we don't add a node, the entry is already there.
            if _is_component_bp(bp):
                # The graph IS the event — find the function entry node
                nodes = graph.get_editor_property("nodes") or []
                for n in nodes:
                    try:
                        cls_name = n.get_class().get_name()
                        if "FunctionEntry" in cls_name or "Event" in cls_name:
                            try:
                                n.set_editor_property("node_comment", node_id)
                            except Exception:
                                pass
                            return ok(
                                f"Using component override entry for '{node_type}' (id={node_id})",
                                node_id=node_id
                            )
                    except Exception:
                        pass
                # If we get here, tag the first node as the event
                if nodes:
                    try:
                        nodes[0].set_editor_property("node_comment", node_id)
                    except Exception:
                        pass
                    return ok(
                        f"Tagged first graph node as '{node_type}' (id={node_id})",
                        node_id=node_id
                    )
                return ok(
                    f"[WARN] Component graph '{graph.get_name()}' has no nodes yet — event entry will appear after compile",
                    node_id=node_id, warning=True
                )

            # Actor-based blueprint — add event node normally
            try:
                node = unreal.BlueprintEditorLibrary.add_function_call_node_to_graph(
                    bp, f"/Script/Engine.Actor:{func_name}", graph, x, y
                )
            except Exception:
                pass
            if node is None:
                try:
                    node = unreal.BlueprintEditorLibrary.add_custom_event_node(
                        bp, graph, func_name, x, y
                    )
                except Exception:
                    pass

        # ── Timeline ─────────────────────────────────────────────────────────
        elif node_type == "Timeline":
            tl_name = params.get("name", "Timeline") if isinstance(params, dict) else "Timeline"
            try:
                node = unreal.BlueprintEditorLibrary.add_timeline_node(bp, tl_name, graph, x, y)
            except Exception:
                pass

        # ── Cast To ──────────────────────────────────────────────────────────
        elif node_type.startswith("Cast To"):
            target_name = node_type.replace("Cast To", "").strip()
            target_cls  = _resolve_parent_class(target_name)
            if target_cls:
                try:
                    node = unreal.BlueprintEditorLibrary.add_cast_node(
                        bp, target_cls, graph, x, y
                    )
                except Exception:
                    pass

        # ── Variable Get/Set ─────────────────────────────────────────────────
        elif node_type == "Get Variable":
            var = params.get("variable", "") if isinstance(params, dict) else ""
            try:
                node = unreal.BlueprintEditorLibrary.add_variable_get_node(bp, var, graph, x, y)
            except Exception:
                pass

        elif node_type == "Set Variable":
            var = params.get("variable", "") if isinstance(params, dict) else ""
            try:
                node = unreal.BlueprintEditorLibrary.add_variable_set_node(bp, var, graph, x, y)
            except Exception:
                pass

        # ── Call Function: <path> ─────────────────────────────────────────────
        elif node_type.startswith("Call Function:"):
            func_path = node_type.replace("Call Function:", "").strip()
            try:
                node = unreal.BlueprintEditorLibrary.add_function_call_node_to_graph(
                    bp, func_path, graph, x, y
                )
            except Exception:
                pass

        # ── Named function nodes ──────────────────────────────────────────────
        elif node_type in FUNC_MAP:
            try:
                node = unreal.BlueprintEditorLibrary.add_function_call_node_to_graph(
                    bp, FUNC_MAP[node_type], graph, x, y
                )
            except Exception:
                pass

    except Exception:
        pass

    if node is None:
        return ok(
            f"[WARN] Could not auto-place '{node_type}' — add it manually in the Blueprint editor",
            node_id=node_id, warning=True
        )

    try:
        node.set_editor_property("node_comment", node_id)
    except Exception:
        pass

    return ok(f"Added '{node_type}' (id={node_id}) to {bp_name}", node_id=node_id)


# ─────────────────────────────────────────────────────────────────────────────
# connect_nodes
# ─────────────────────────────────────────────────────────────────────────────
def connect_nodes(cmd):
    bp_name  = cmd.get("blueprint") or cmd.get("blueprint_name")
    from_id  = cmd.get("from_node", "")
    from_pin = cmd.get("from_pin", "Then")
    to_id    = cmd.get("to_node", "")
    to_pin   = cmd.get("to_pin", "Execute")

    if not bp_name: return err("connect_nodes: 'blueprint' is required")

    try:
        bp = _load_bp(bp_name)
    except ValueError as e:
        return err(str(e))

    # Search ALL graphs for nodes (component BPs have multiple override graphs)
    all_nodes = []
    for g in _get_graphs(bp):
        try:
            all_nodes.extend(g.get_editor_property("nodes") or [])
        except Exception:
            pass

    def _find(nid):
        for n in all_nodes:
            try:
                if n.get_editor_property("node_comment") == nid:
                    return n
            except Exception:
                pass
        return None

    from_node = _find(from_id)
    to_node   = _find(to_id)

    if from_node is None:
        return ok(f"[WARN] connect_nodes: source '{from_id}' not found — skipping", warning=True)
    if to_node is None:
        return ok(f"[WARN] connect_nodes: target '{to_id}' not found — skipping", warning=True)

    def _find_pin(node, pin_name):
        try:
            for p in node.get_editor_property("pins"):
                if str(p.get_editor_property("pin_name")) == pin_name:
                    return p
        except Exception:
            pass
        return None

    fp = _find_pin(from_node, from_pin)
    tp = _find_pin(to_node,   to_pin)

    if fp is None:
        return ok(f"[WARN] connect_nodes: pin '{from_pin}' not found on '{from_id}' — skipping", warning=True)
    if tp is None:
        return ok(f"[WARN] connect_nodes: pin '{to_pin}' not found on '{to_id}' — skipping", warning=True)

    try:
        success = unreal.BlueprintEditorLibrary.create_connection_between_pins(fp, tp)
    except Exception as e:
        return ok(f"[WARN] connect_nodes: connection failed ({e}) — skipping", warning=True)

    if not success:
        return ok(f"[WARN] connect_nodes: {from_id}.{from_pin} → {to_id}.{to_pin} failed — skipping", warning=True)

    return ok(f"Connected {from_id}.{from_pin} → {to_id}.{to_pin}")


# ─────────────────────────────────────────────────────────────────────────────
# set_variable
# ─────────────────────────────────────────────────────────────────────────────
def set_variable(cmd):
    bp_name  = cmd.get("blueprint") or cmd.get("blueprint_name")
    params   = cmd.get("parameters") or {}
    var_name = cmd.get("variable_name") or params.get("variable_name")
    value    = cmd.get("value")
    if value is None:
        value = params.get("value")

    if not bp_name:   return err("set_variable: 'blueprint' is required")
    if not var_name:  return err("set_variable: 'variable_name' is required")
    if value is None: return err("set_variable: 'value' is required")

    try:
        bp = _load_bp(bp_name)
    except ValueError as e:
        return err(str(e))

    try:
        unreal.BlueprintEditorLibrary.set_member_variable_default_value(bp, var_name, str(value))
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        return ok(f"Set {bp_name}.{var_name} = {value}")
    except Exception as e:
        return ok(f"[WARN] set_variable failed ({e}) — skipping", warning=True)


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
        unreal.log_warning(f"[MCPBlueprint] compile warning: {e}")

    try:
        unreal.EditorAssetLibrary.save_asset(f"/Game/MCP/{name}", only_if_is_dirty=False)
    except Exception as e:
        unreal.log_warning(f"[MCPBlueprint] save warning: {e}")

    return ok(f"Compiled and saved {name}")


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────
COMMANDS = {
    "create_blueprint":  create_blueprint,
    "add_node":          add_node,
    "connect_nodes":     connect_nodes,
    "add_variable":      add_variable,
    "set_variable":      set_variable,
    "compile_blueprint": compile_blueprint,
}

def execute_command(cmd):
    if not isinstance(cmd, dict):
        return err("Command must be a dict")
    action = cmd.get("action")
    if not action:
        return err("Missing 'action' field")
    handler = COMMANDS.get(action)
    if not handler:
        return ok(f"[WARN] Unknown action '{action}' — skipping", warning=True)
    try:
        return handler(cmd)
    except Exception:
        return err(f"{action} error:\n{traceback.format_exc()}")

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
            if r.get("warning"):
                unreal.log_warning(f"[MCPBlueprint] WARN: {r.get('message','?')}")
        else:
            failed += 1
            unreal.log_error(f"[MCPBlueprint] FAIL: {r.get('message','?')}")

    return {
        "success":   failed == 0,
        "total":     len(commands),
        "succeeded": succeeded,
        "failed":    failed,
        "results":   results,
    }
