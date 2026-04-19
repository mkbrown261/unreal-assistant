#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleInterface.h"
#include "Modules/ModuleManager.h"

class SDockTab;
class FTabManager;
class SWidget;

/**
 * FMCPBlueprintModule
 *
 * Editor-only module that:
 *  1. Starts a TCP server on port 55557 (handles AI Blueprint commands from Python)
 *  2. Registers a dockable "MCP Blueprint AI" tab whose content is an SWebBrowser
 *     pointing at http://localhost:8080/chat
 *  3. Adds a menu / toolbar entry to open the tab
 */
class FMCPBlueprintModule : public IModuleInterface
{
public:
    /** IModuleInterface */
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;

    /** Open (or focus) the docked chat tab programmatically. */
    static void OpenChatTab();

    /** The nominal tab identifier used with FGlobalTabmanager. */
    static const FName ChatTabName;

private:
    /** Tab spawner callback registered with FGlobalTabmanager. */
    static TSharedRef<SDockTab> OnSpawnChatTab(const FSpawnTabArgs& Args);

    /** Registers the tab spawner and adds a menu entry. */
    void RegisterTabSpawner();

    /** Unregisters the tab spawner. */
    void UnregisterTabSpawner();

    /** Adds "MCP AI" to the Level Editor toolbar / menu. */
    void ExtendMenus();

    /** Handle for the slate post-tick callback that defers tab opening. */
    FDelegateHandle PostTickHandle;

    /** Ensures we only try to open the tab once on startup. */
    bool bTabOpened = false;
};
