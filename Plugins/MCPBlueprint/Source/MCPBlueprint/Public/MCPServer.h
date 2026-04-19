// Copyright Unreal Assistant. All Rights Reserved.
#pragma once

#include "CoreMinimal.h"
#include "HttpServerModule.h"
#include "IHttpRouter.h"
#include "HttpRouteHandle.h"

/**
 * FMCPServer
 *
 * Lightweight HTTP server that runs inside Unreal Engine (editor mode).
 * Listens on 0.0.0.0:8080 and exposes:
 *
 *   POST /unreal/execute   — Accepts { "commands": [...] } and forwards to FBlueprintExecutor
 *   GET  /unreal/status    — Returns { "status": "ok", "version": "1.0.0" }
 *
 * The MCP Node.js server (mcp-server/server.js) connects to this endpoint.
 */
class MCPBLUEPRINT_API FMCPServer
{
public:
    FMCPServer();
    ~FMCPServer();

    /** Start HTTP listener on the configured port (default 8080). */
    bool Start(uint32 Port = 8080);

    /** Stop the HTTP listener and release all handles. */
    void Stop();

    bool IsRunning() const { return bRunning; }

private:
    bool HandleExecute(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
    bool HandleStatus(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);

    TSharedPtr<IHttpRouter> Router;
    FHttpRouteHandle ExecuteHandle;
    FHttpRouteHandle StatusHandle;
    bool bRunning = false;
    uint32 ListenPort = 8080;
};
