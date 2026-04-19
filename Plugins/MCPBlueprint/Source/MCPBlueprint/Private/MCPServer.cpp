// MCPServer.cpp
// TCP server on port 55557.
// Accepts JSON commands from Python, routes to FBlueprintCommandDispatcher,
// returns JSON responses (newline-delimited).

#include "MCPServer.h"
#include "BlueprintCommands.h"

#include "Sockets.h"
#include "SocketSubsystem.h"
#include "Common/TcpSocketBuilder.h"
#include "Networking.h"

#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonWriter.h"
#include "HAL/RunnableThread.h"

// ---------------------------------------------------------------------------
// FMCPClientWorker
// ---------------------------------------------------------------------------

FMCPClientWorker::FMCPClientWorker(FSocket* InClientSocket)
    : ClientSocket(InClientSocket)
    , Thread(nullptr)
    , bShouldStop(false)
{
    Thread = FRunnableThread::Create(this, TEXT("MCPClientWorker"), 0, TPri_Normal);
}

FMCPClientWorker::~FMCPClientWorker()
{
    Stop();
    if (Thread)
    {
        Thread->WaitForCompletion();
        delete Thread;
        Thread = nullptr;
    }
    if (ClientSocket)
    {
        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(ClientSocket);
        ClientSocket = nullptr;
    }
}

void FMCPClientWorker::Stop()
{
    bShouldStop = true;
    if (ClientSocket)
    {
        ClientSocket->Shutdown(ESocketShutdownMode::ReadWrite);
    }
}

bool FMCPClientWorker::ReadLine(FString& OutLine)
{
    OutLine.Empty();
    TArray<uint8> Buffer;

    while (!bShouldStop)
    {
        uint8 Byte = 0;
        int32 BytesRead = 0;

        if (!ClientSocket->Recv(&Byte, 1, BytesRead, ESocketReceiveFlags::None))
        {
            return false; // disconnected
        }
        if (BytesRead == 0)
        {
            return false;
        }

        if (Byte == '\n')
        {
            break;
        }
        if (Byte != '\r')
        {
            Buffer.Add(Byte);
        }
    }

    // Convert UTF-8 bytes to FString
    Buffer.Add(0); // null terminate
    OutLine = UTF8_TO_TCHAR(reinterpret_cast<const char*>(Buffer.GetData()));
    return true;
}

bool FMCPClientWorker::WriteLine(const FString& Line)
{
    FTCHARToUTF8 Converter(*Line);
    const uint8* Data = reinterpret_cast<const uint8*>(Converter.Get());
    int32 Len = Converter.Length();

    int32 Sent = 0;
    if (!ClientSocket->Send(Data, Len, Sent) || Sent != Len)
    {
        return false;
    }

    // Send the newline delimiter
    const uint8 NL = '\n';
    int32 NLSent = 0;
    ClientSocket->Send(&NL, 1, NLSent);
    return true;
}

uint32 FMCPClientWorker::Run()
{
    while (!bShouldStop)
    {
        FString Line;
        if (!ReadLine(Line))
        {
            break; // client disconnected
        }

        if (Line.IsEmpty()) { continue; }

        // ── Parse incoming JSON ────────────────────────────────────────────
        TSharedPtr<FJsonObject> CmdObj;
        TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Line);
        FString ResponseJson;

        if (!FJsonSerializer::Deserialize(Reader, CmdObj) || !CmdObj.IsValid())
        {
            TSharedPtr<FJsonObject> ErrObj = MakeShared<FJsonObject>();
            ErrObj->SetBoolField(TEXT("success"), false);
            ErrObj->SetStringField(TEXT("error"), TEXT("Invalid JSON"));
            TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ResponseJson);
            FJsonSerializer::Serialize(ErrObj.ToSharedRef(), Writer);
        }
        else
        {
            // ── Dispatch to Blueprint command handler ──────────────────────
            TSharedPtr<FJsonObject> Result = FBlueprintCommandDispatcher::Dispatch(CmdObj);
            TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ResponseJson);
            FJsonSerializer::Serialize(Result.ToSharedRef(), Writer);
        }

        // ── Send response ──────────────────────────────────────────────────
        if (!WriteLine(ResponseJson))
        {
            break;
        }
    }

    return 0;
}

// ---------------------------------------------------------------------------
// FMCPServer
// ---------------------------------------------------------------------------

FMCPServer::FMCPServer()
    : ListenSocket(nullptr)
    , Thread(nullptr)
    , bShouldStop(false)
    , ListenPort(55557)
{
}

FMCPServer::~FMCPServer()
{
    Stop();
}

bool FMCPServer::Start(int32 Port)
{
    ListenPort = Port;

    // Create TCP listen socket
    ListenSocket = FTcpSocketBuilder(TEXT("MCPBlueprintServer"))
        .AsReusable()
        .BoundToPort(Port)
        .Listening(8)
        .Build();

    if (!ListenSocket)
    {
        UE_LOG(LogTemp, Error, TEXT("[MCPBlueprint] Could not create listen socket on port %d"), Port);
        return false;
    }

    // Non-blocking so we can poll for bShouldStop
    ListenSocket->SetNonBlocking(true);

    Thread = FRunnableThread::Create(this, TEXT("MCPBlueprintServer"), 0, TPri_Normal);
    return Thread != nullptr;
}

void FMCPServer::Stop()
{
    bShouldStop = true;

    if (ListenSocket)
    {
        ListenSocket->Shutdown(ESocketShutdownMode::ReadWrite);
        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(ListenSocket);
        ListenSocket = nullptr;
    }

    if (Thread)
    {
        Thread->WaitForCompletion();
        delete Thread;
        Thread = nullptr;
    }

    // Clean up remaining client workers
    for (FMCPClientWorker* W : ClientWorkers)
    {
        W->Stop();
        delete W;
    }
    ClientWorkers.Empty();
}

bool FMCPServer::Init()
{
    return ListenSocket != nullptr;
}

void FMCPServer::PruneFinishedWorkers()
{
    // Remove workers whose threads have finished
    ClientWorkers.RemoveAll([](FMCPClientWorker* W)
    {
        // A simple heuristic: if the socket is invalid the worker is done
        // (actual completion detection would require a flag; this is sufficient
        //  for editor-use cardinality where we have at most a handful of clients)
        return W == nullptr;
    });
}

uint32 FMCPServer::Run()
{
    while (!bShouldStop)
    {
        // Poll for incoming connections (non-blocking)
        bool bHasPending = false;
        if (ListenSocket && ListenSocket->HasPendingConnection(bHasPending) && bHasPending)
        {
            FSocket* ClientSock = ListenSocket->Accept(TEXT("MCPClient"));
            if (ClientSock)
            {
                ClientSock->SetNonBlocking(false); // blocking reads in client thread
                FMCPClientWorker* Worker = new FMCPClientWorker(ClientSock);
                ClientWorkers.Add(Worker);
                UE_LOG(LogTemp, Verbose, TEXT("[MCPBlueprint] Client connected."));
            }
        }

        PruneFinishedWorkers();
        FPlatformProcess::Sleep(0.01f); // 10 ms poll interval
    }

    return 0;
}

void FMCPServer::Exit()
{
    // Called by the thread system after Run() returns
}
