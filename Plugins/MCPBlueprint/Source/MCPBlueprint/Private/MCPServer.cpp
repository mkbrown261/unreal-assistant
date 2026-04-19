// Copyright Unreal Assistant. All Rights Reserved.

#include "MCPServer.h"
#include "BlueprintExecutor.h"
#include "HttpServerModule.h"
#include "HttpServerResponse.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/DateTime.h"

FMCPServer::FMCPServer() {}

FMCPServer::~FMCPServer()
{
    Stop();
}

bool FMCPServer::Start(uint32 Port)
{
    ListenPort = Port;

    FHttpServerModule& HttpServer = FHttpServerModule::Get();
    Router = HttpServer.GetHttpRouter(Port);
    if (!Router.IsValid())
    {
        return false;
    }

    // POST /unreal/execute
    ExecuteHandle = Router->BindRoute(
        FHttpPath(TEXT("/unreal/execute")),
        EHttpServerRequestVerbs::VERB_POST,
        FHttpRequestHandler::CreateRaw(this, &FMCPServer::HandleExecute)
    );

    // GET /unreal/status
    StatusHandle = Router->BindRoute(
        FHttpPath(TEXT("/unreal/status")),
        EHttpServerRequestVerbs::VERB_GET,
        FHttpRequestHandler::CreateRaw(this, &FMCPServer::HandleStatus)
    );

    HttpServer.StartAllListeners();
    bRunning = true;
    return true;
}

void FMCPServer::Stop()
{
    if (!bRunning) return;
    if (Router.IsValid())
    {
        Router->UnbindRoute(ExecuteHandle);
        Router->UnbindRoute(StatusHandle);
    }
    FHttpServerModule::Get().StopAllListeners();
    bRunning = false;
}

bool FMCPServer::HandleExecute(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    // Parse body
    FString Body = FString(UTF8_TO_TCHAR(reinterpret_cast<const char*>(Request.Body.GetData())));

    TSharedPtr<FJsonObject> Root;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Body);
    if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
    {
        auto Resp = FHttpServerResponse::Create(
            TEXT("{\"success\":false,\"error\":\"Invalid JSON body\"}"),
            TEXT("application/json")
        );
        Resp->Code = EHttpServerResponseCodes::BadRequest;
        OnComplete(MoveTemp(Resp));
        return true;
    }

    // Expect { "commands": [...] }
    const TArray<TSharedPtr<FJsonValue>>* CommandsArray;
    if (!Root->TryGetArrayField(TEXT("commands"), CommandsArray) || !CommandsArray)
    {
        auto Resp = FHttpServerResponse::Create(
            TEXT("{\"success\":false,\"error\":\"Missing 'commands' array\"}"),
            TEXT("application/json")
        );
        Resp->Code = EHttpServerResponseCodes::BadRequest;
        OnComplete(MoveTemp(Resp));
        return true;
    }

    // Execute on the Game Thread (Blueprint APIs require GT)
    AsyncTask(ENamedThreads::GameThread, [CommandsArray = *CommandsArray, OnComplete]()
    {
        FString Result = FBlueprintExecutor::ExecuteCommandBatch(CommandsArray);
        auto Resp = FHttpServerResponse::Create(Result, TEXT("application/json"));
        Resp->Code = EHttpServerResponseCodes::Ok;
        // CORS headers so the MCP server can call from any host
        Resp->Headers.Add(TEXT("Access-Control-Allow-Origin"), { TEXT("*") });
        OnComplete(MoveTemp(Resp));
    });

    return true;
}

bool FMCPServer::HandleStatus(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
    FString Now = FDateTime::UtcNow().ToString();
    FString Json = FString::Printf(
        TEXT("{\"status\":\"ok\",\"server\":\"MCPBlueprint\",\"version\":\"1.0.0\",\"port\":%d,\"timestamp\":\"%s\"}"),
        ListenPort, *Now
    );
    auto Resp = FHttpServerResponse::Create(Json, TEXT("application/json"));
    Resp->Code = EHttpServerResponseCodes::Ok;
    Resp->Headers.Add(TEXT("Access-Control-Allow-Origin"), { TEXT("*") });
    OnComplete(MoveTemp(Resp));
    return true;
}
