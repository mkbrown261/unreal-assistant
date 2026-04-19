"""
test_server.py
Run this OUTSIDE Unreal to verify the HTTP server starts correctly.
It uses a mock 'unreal' module so you don't need Unreal installed to test.

Usage:
  python test_server.py

Then in another terminal:
  curl http://localhost:8080/unreal/status
  curl -X POST http://localhost:8080/unreal/execute \
    -H "Content-Type: application/json" \
    -d '{"commands":[{"action":"create_blueprint","name":"BP_Test","parent_class":"Actor"}]}'
"""

import sys
import types
import json
import time

# ── Mock the unreal module so tests work without UE installed ─────────────────

mock_unreal = types.ModuleType("unreal")

class MockBP:
    def get_name(self): return "MockBlueprint"

class MockGraph:
    def __init__(self):
        self._nodes = []
    def get_editor_property(self, k):
        return self._nodes if k == "nodes" else None

class MockBlueprintEditorLibrary:
    @staticmethod
    def compile_blueprint(bp): pass
    @staticmethod
    def add_member_variable(bp, name, pin_type): pass
    @staticmethod
    def set_member_variable_default_value(bp, name, val): pass
    @staticmethod
    def get_graphs(bp): return [MockGraph()]
    @staticmethod
    def add_function_call_node_to_graph(bp, path, graph, x, y): return None
    @staticmethod
    def add_variable_get_node(bp, name, graph, x, y): return None
    @staticmethod
    def add_variable_set_node(bp, name, graph, x, y): return None
    @staticmethod
    def add_timeline_node(bp, name, graph, x, y): return None
    @staticmethod
    def add_cast_node(bp, cls, graph, x, y): return None
    @staticmethod
    def add_custom_event_node(bp, graph, name, x, y): return None
    @staticmethod
    def create_connection_between_pins(a, b): return True

class MockAssetTools:
    def create_asset(self, asset_name, package_path, asset_class, factory):
        return MockBP()

class MockAssetToolsHelpers:
    @staticmethod
    def get_asset_tools(): return MockAssetTools()

class MockEditorAssetLibrary:
    @staticmethod
    def save_asset(path, only_if_is_dirty=True): pass

class MockBlueprintFactory:
    def set_editor_property(self, k, v): pass

class MockBlueprint: pass
class MockActor:
    @staticmethod
    def static_class(): return None

class MockEdGraphPinType:
    def set_editor_property(self, k, v): pass

mock_unreal.BlueprintEditorLibrary = MockBlueprintEditorLibrary
mock_unreal.AssetToolsHelpers = MockAssetToolsHelpers
mock_unreal.EditorAssetLibrary = MockEditorAssetLibrary
mock_unreal.BlueprintFactory = MockBlueprintFactory
mock_unreal.Blueprint = MockBlueprint
mock_unreal.Actor = MockActor
mock_unreal.EdGraphPinType = MockEdGraphPinType
mock_unreal.BlueprintVariableType = types.SimpleNamespace(
    BOOL="bool", INT="int", FLOAT="float", STRING="string", STRUCT="struct"
)
mock_unreal.log = lambda msg: print(f"[UE] {msg}")
mock_unreal.load_asset = lambda path: MockBP()
mock_unreal.load_class = lambda a, b: None
mock_unreal.load_object = lambda a, b: None
mock_unreal.call_on_game_thread = lambda fn: fn()

sys.modules["unreal"] = mock_unreal

# ── Now import and start the server ───────────────────────────────────────────

import mcp_server

print("Starting MCP test server on http://localhost:8080 ...")
mcp_server.start(8080)

print("Server running. Try:")
print("  curl http://localhost:8080/unreal/status")
print('  curl -X POST http://localhost:8080/unreal/execute \\')
print('    -H "Content-Type: application/json" \\')
print('    -d \'{"commands":[{"action":"create_blueprint","name":"BP_Test","parent_class":"Actor"}]}\'')
print("\nPress Ctrl+C to stop.\n")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping...")
    mcp_server.stop()
