// MCPBlueprintModule.cpp
// Main module lifecycle: starts TCP server, registers dockable chat tab

#include "MCPBlueprintModule.h"
#include "MCPServer.h"

#include "Framework/Docking/TabManager.h"
#include "Framework/MultiBox/MultiBoxBuilder.h"
#include "Widgets/Docking/SDockTab.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"
#include "WorkspaceMenuStructure.h"
#include "WorkspaceMenuStructureModule.h"
#include "ToolMenus.h"
#include "LevelEditor.h"
#include "Interfaces/IMainFrameModule.h"
#include "Framework/Application/SlateApplication.h"
#include "SWebBrowser.h"

#define LOCTEXT_NAMESPACE "FMCPBlueprintModule"

const FName FMCPBlueprintModule::ChatTabName(TEXT("MCPBlueprintChat"));

// ----------------------------------------------------------------------------
// Module singleton
// ----------------------------------------------------------------------------

static FMCPServer* GServer = nullptr;

// ----------------------------------------------------------------------------
// StartupModule
// ----------------------------------------------------------------------------

void FMCPBlueprintModule::StartupModule()
{
    UE_LOG(LogTemp, Log, TEXT("[MCPBlueprint] Starting C++ plugin v3.0.0"));

    // 1. Start TCP server on port 55557
    GServer = new FMCPServer();
    if (!GServer->Start(55557))
    {
        UE_LOG(LogTemp, Error, TEXT("[MCPBlueprint] Failed to start TCP server on port 55557"));
        delete GServer;
        GServer = nullptr;
    }
    else
    {
        UE_LOG(LogTemp, Log, TEXT("[MCPBlueprint] TCP server listening on port 55557"));
    }

    // 2. Register the dockable tab spawner
    RegisterTabSpawner();

    // 3. Extend menus / toolbar
    if (UToolMenus::IsToolMenuUIEnabled())
    {
        UToolMenus::RegisterStartupCallback(
            FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FMCPBlueprintModule::ExtendMenus));
    }

    // 4. Open the tab after the editor is fully loaded (defer via post-tick)
    PostTickHandle = FSlateApplication::Get().OnPreTick().AddLambda(
        [this](float /*Delta*/)
        {
            if (bTabOpened) { return; }
            bTabOpened = true;
            FSlateApplication::Get().OnPreTick().Remove(PostTickHandle);
            OpenChatTab();
        });
}

// ----------------------------------------------------------------------------
// ShutdownModule
// ----------------------------------------------------------------------------

void FMCPBlueprintModule::ShutdownModule()
{
    if (PostTickHandle.IsValid())
    {
        FSlateApplication::Get().OnPreTick().Remove(PostTickHandle);
    }

    UnregisterTabSpawner();
    UToolMenus::UnRegisterStartupCallback(this);
    UToolMenus::UnregisterOwner(this);

    if (GServer)
    {
        GServer->Stop();
        delete GServer;
        GServer = nullptr;
        UE_LOG(LogTemp, Log, TEXT("[MCPBlueprint] TCP server stopped."));
    }
}

// ----------------------------------------------------------------------------
// Tab spawner
// ----------------------------------------------------------------------------

void FMCPBlueprintModule::RegisterTabSpawner()
{
    FTabSpawnerEntry& Entry = FGlobalTabmanager::Get()->RegisterNomadTabSpawner(
        ChatTabName,
        FOnSpawnTab::CreateStatic(&FMCPBlueprintModule::OnSpawnChatTab))
        .SetDisplayName(LOCTEXT("MCPTabTitle", "MCP Blueprint AI"))
        .SetTooltipText(LOCTEXT("MCPTabTooltip", "AI-powered Blueprint generator (chat panel)"))
        .SetMenuType(ETabSpawnerMenuType::Hidden);

    // Place it in the "Developer Tools" workspace category
    const IWorkspaceMenuStructure& MenuStructure = WorkspaceMenu::GetMenuStructure();
    Entry.SetGroup(MenuStructure.GetDeveloperToolsMiscCategory());
}

void FMCPBlueprintModule::UnregisterTabSpawner()
{
    FGlobalTabmanager::Get()->UnregisterNomadTabSpawner(ChatTabName);
}

TSharedRef<SDockTab> FMCPBlueprintModule::OnSpawnChatTab(const FSpawnTabArgs& Args)
{
    // The chat panel is the Python HTTP server's web UI at localhost:8080/chat
    // We embed it using UE's SWebBrowser widget.
    const FString ChatUrl = TEXT("http://localhost:8080/chat");

    TSharedRef<SWebBrowser> WebBrowserWidget =
        SNew(SWebBrowser)
        .InitialURL(ChatUrl)
        .ShowControls(false)
        .ShowAddressBar(false)
        .ShowErrorMessage(true)
        .SupportsTransparency(false);

    return SNew(SDockTab)
        .TabRole(ETabRole::NomadTab)
        .Label(LOCTEXT("MCPTabLabel", "MCP Blueprint AI"))
        [
            WebBrowserWidget
        ];
}

// ----------------------------------------------------------------------------
// Open chat tab (public static)
// ----------------------------------------------------------------------------

void FMCPBlueprintModule::OpenChatTab()
{
    FGlobalTabmanager::Get()->TryInvokeTab(ChatTabName);
}

// ----------------------------------------------------------------------------
// Menu / toolbar extension
// ----------------------------------------------------------------------------

void FMCPBlueprintModule::ExtendMenus()
{
    UToolMenus* ToolMenus = UToolMenus::Get();
    if (!ToolMenus) { return; }

    // ── Level Editor toolbar ──────────────────────────────────────────────
    // Try the Play toolbar first (right side), fall back to main toolbar
    static const TCHAR* ToolbarNames[] = {
        TEXT("LevelEditor.LevelEditorToolBar.PlayToolBar"),
        TEXT("LevelEditor.LevelEditorToolBar"),
    };
    for (const TCHAR* ToolbarName : ToolbarNames)
    {
        if (UToolMenu* Toolbar = ToolMenus->ExtendMenu(ToolbarName))
        {
            FToolMenuSection& Section = Toolbar->FindOrAddSection(FName("MCP"));
            Section.AddMenuEntry(
                FName("MCPOpenChat"),
                LOCTEXT("MCPToolbarLabel",    "🤖 MCP AI"),
                LOCTEXT("MCPToolbarTooltip",  "Open MCP Blueprint AI chat panel (docked tab)"),
                FSlateIcon(),
                FUIAction(FExecuteAction::CreateStatic(&FMCPBlueprintModule::OpenChatTab))
            );
            break;
        }
    }

    // ── Level Editor menu bar ─────────────────────────────────────────────
    if (UToolMenu* MenuBar = ToolMenus->ExtendMenu(TEXT("LevelEditor.MainMenu")))
    {
        FToolMenuSection& Section = MenuBar->FindOrAddSection(FName("MCP"));
        Section.AddSubMenu(
            FName("MCPSubMenu"),
            LOCTEXT("MCPMenu",        "🤖 MCP AI"),
            LOCTEXT("MCPMenuTooltip", "MCP Blueprint AI tools"),
            FNewToolMenuDelegate::CreateLambda([](UToolMenu* SubMenu)
            {
                FToolMenuSection& Sub = SubMenu->AddSection(FName("MCPActions"), LOCTEXT("MCPActions","Actions"));
                Sub.AddMenuEntry(
                    FName("MCPOpenChatFromMenu"),
                    LOCTEXT("MCPMenuOpenChat",        "Open Chat Panel"),
                    LOCTEXT("MCPMenuOpenChatTooltip", "Open the docked MCP Blueprint AI chat tab"),
                    FSlateIcon(),
                    FUIAction(FExecuteAction::CreateStatic(&FMCPBlueprintModule::OpenChatTab))
                );
            })
        );
    }
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FMCPBlueprintModule, MCPBlueprint)
