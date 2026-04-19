#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

/**
 * FBlueprintCommandDispatcher
 *
 * All Blueprint graph manipulation commands executed on the game thread.
 *
 * Commands (JSON field "action"):
 *   get_status          — health check
 *   create_blueprint    — create a new UBlueprint asset
 *   add_variable        — add a member variable
 *   add_node            — add a UK2Node to the EventGraph
 *   connect_nodes       — wire two node pins together
 *   compile_blueprint   — KismetCompiler round-trip + save
 *
 * All functions must be called from the game/editor thread.
 * They return a TSharedPtr<FJsonObject> with at minimum:
 *   { "success": true/false, "message": "..." }
 */
class MCPBLUEPRINT_API FBlueprintCommandDispatcher
{
public:
    /**
     * Main entry point.
     * Parses the "action" field and routes to the appropriate handler.
     * Thread-safe: enqueues work on the game thread and blocks until done.
     */
    static TSharedPtr<FJsonObject> Dispatch(const TSharedPtr<FJsonObject>& Cmd);

private:
    // ── Individual handlers (called on game thread) ────────────────────────

    static TSharedPtr<FJsonObject> HandleGetStatus   (const TSharedPtr<FJsonObject>& Cmd);
    static TSharedPtr<FJsonObject> HandleCreateBP    (const TSharedPtr<FJsonObject>& Cmd);
    static TSharedPtr<FJsonObject> HandleAddVariable (const TSharedPtr<FJsonObject>& Cmd);
    static TSharedPtr<FJsonObject> HandleAddNode     (const TSharedPtr<FJsonObject>& Cmd);
    static TSharedPtr<FJsonObject> HandleConnectNodes(const TSharedPtr<FJsonObject>& Cmd);
    static TSharedPtr<FJsonObject> HandleCompile     (const TSharedPtr<FJsonObject>& Cmd);

    // ── Helpers ────────────────────────────────────────────────────────────

    /** Build a simple success/error response. */
    static TSharedPtr<FJsonObject> MakeOk (const FString& Msg);
    static TSharedPtr<FJsonObject> MakeErr(const FString& Msg);

    /** Load (or find loaded) Blueprint by asset path, e.g. /Game/MCP/BP_Foo */
    static class UBlueprint* LoadBP(const FString& AssetPath);

    /** Ensure the content directory exists. */
    static void EnsureDir(const FString& Path);

    /**
     * Node registry: maps (BlueprintName -> map<UserNodeId -> UK2Node*>)
     * Stored as weak pointers so GC can reclaim nodes freely.
     */
    static TMap<FString, TMap<FString, TWeakObjectPtr<class UK2Node>>> NodeRegistry;
    static FCriticalSection RegistryLock;

    /** Register a node and return the auto-generated node ID string. */
    static FString RegisterNode(const FString& BPName, class UK2Node* Node);

    /** Look up a node by blueprint name + ID string. */
    static class UK2Node* FindNode(const FString& BPName, const FString& NodeId);
};
