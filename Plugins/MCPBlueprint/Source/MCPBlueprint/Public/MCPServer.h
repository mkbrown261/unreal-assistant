#pragma once

#include "CoreMinimal.h"
#include "HAL/Runnable.h"
#include "HAL/RunnableThread.h"
#include "Containers/Queue.h"

struct FMCPCommand;

/**
 * FMCPClientWorker
 *
 * Handles a single accepted client connection.
 * Reads newline-delimited JSON, dispatches commands, writes JSON responses.
 * Each connection runs in its own thread.
 */
class FMCPClientWorker : public FRunnable
{
public:
    explicit FMCPClientWorker(class FSocket* InClientSocket);
    virtual ~FMCPClientWorker();

    // FRunnable
    virtual bool Init() override { return true; }
    virtual uint32 Run() override;
    virtual void Stop() override;

private:
    class FSocket* ClientSocket;
    FRunnableThread* Thread;
    bool bShouldStop;

    /** Read until '\n', returns false on error/disconnect. */
    bool ReadLine(FString& OutLine);

    /** Write a JSON string followed by '\n'. */
    bool WriteLine(const FString& Line);
};

/**
 * FMCPServer
 *
 * Listens on TCP port 55557.
 * Spawns one FMCPClientWorker per accepted connection.
 * Designed to be started/stopped from the main module lifecycle.
 */
class FMCPServer : public FRunnable
{
public:
    FMCPServer();
    virtual ~FMCPServer();

    /** Start the listen thread. Returns true on success. */
    bool Start(int32 Port = 55557);

    /** Stop the listen thread and close the socket. */
    void Stop();

    // FRunnable
    virtual bool Init() override;
    virtual uint32 Run() override;
    virtual void Exit() override;

private:
    class FSocket*   ListenSocket;
    FRunnableThread* Thread;
    bool             bShouldStop;
    int32            ListenPort;

    /** Active client workers — we own them until they finish. */
    TArray<FMCPClientWorker*> ClientWorkers;

    /** Reap finished client threads. */
    void PruneFinishedWorkers();
};
