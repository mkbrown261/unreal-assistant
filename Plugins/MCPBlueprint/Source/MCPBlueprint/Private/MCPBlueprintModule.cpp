// Copyright Unreal Assistant. All Rights Reserved.

#include "MCPBlueprintModule.h"
#include "MCPServer.h"
#include "Modules/ModuleManager.h"

static TUniquePtr<FMCPServer> GMCPServer;

void FMCPBlueprintModule::StartupModule()
{
    UE_LOG(LogTemp, Log, TEXT("[MCPBlueprint] StartupModule — starting HTTP server on :8080"));

    GMCPServer = MakeUnique<FMCPServer>();
    if (!GMCPServer->Start(8080))
    {
        UE_LOG(LogTemp, Error, TEXT("[MCPBlueprint] Failed to start MCP HTTP server on port 8080"));
    }
    else
    {
        UE_LOG(LogTemp, Log, TEXT("[MCPBlueprint] MCP HTTP server ready → POST http://localhost:8080/unreal/execute"));
    }
}

void FMCPBlueprintModule::ShutdownModule()
{
    UE_LOG(LogTemp, Log, TEXT("[MCPBlueprint] ShutdownModule — stopping HTTP server"));
    if (GMCPServer)
    {
        GMCPServer->Stop();
        GMCPServer.Reset();
    }
}

IMPLEMENT_MODULE(FMCPBlueprintModule, MCPBlueprint)
