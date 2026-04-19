// Copyright Unreal Assistant. All Rights Reserved.
#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

/**
 * FBlueprintExecutor
 * 
 * Processes structured JSON commands from the MCP server and executes them
 * directly inside Unreal Engine's Blueprint system.
 *
 * Supported commands:
 *   create_blueprint   — Create a new Blueprint asset
 *   add_node           — Add a node to an existing Blueprint graph
 *   connect_nodes      — Connect two nodes via their pins
 *   add_variable       — Add a variable to a Blueprint
 *   set_variable       — Set a variable's default value
 *   compile_blueprint  — Compile a Blueprint asset
 */
class MCPBLUEPRINT_API FBlueprintExecutor
{
public:

    /** Execute a single JSON command object. Returns result JSON string. */
    static FString ExecuteCommand(TSharedPtr<FJsonObject> Command);

    /** Execute an ordered array of commands, stopping on first hard error. */
    static FString ExecuteCommandBatch(const TArray<TSharedPtr<FJsonValue>>& Commands);

private:

    /** Create a new Blueprint asset at /Game/MCP/<Name> */
    static FString CreateBlueprint(TSharedPtr<FJsonObject> Cmd);

    /** Add a Blueprint node to the EventGraph of the target Blueprint */
    static FString AddNode(TSharedPtr<FJsonObject> Cmd);

    /** Connect two nodes by pin name */
    static FString ConnectNodes(TSharedPtr<FJsonObject> Cmd);

    /** Add a member variable to a Blueprint */
    static FString AddVariable(TSharedPtr<FJsonObject> Cmd);

    /** Set a variable's default value */
    static FString SetVariable(TSharedPtr<FJsonObject> Cmd);

    /** Compile a Blueprint and return any errors */
    static FString CompileBlueprint(TSharedPtr<FJsonObject> Cmd);

    /** Helper: load a Blueprint UBlueprint* from /Game/MCP/<Name> */
    static class UBlueprint* LoadBlueprint(const FString& Name);

    /** Helper: build a JSON result string */
    static FString MakeResult(bool bSuccess, const FString& Message, const FString& Extra = TEXT(""));
};
