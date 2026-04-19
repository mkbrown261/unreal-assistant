// MCPBlueprint.Build.cs
// UE 5.3+ Editor plugin — C++ TCP server for AI Blueprint generation

using UnrealBuildTool;

public class MCPBlueprint : ModuleRules
{
    public MCPBlueprint(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        bEnableExceptions = false;

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "InputCore",
        });

        PrivateDependencyModuleNames.AddRange(new string[]
        {
            // Editor infrastructure
            "UnrealEd",
            "EditorSubsystem",
            "EditorFramework",
            "ToolMenus",
            "Slate",
            "SlateCore",
            "EditorStyle",
            "WorkspaceMenuStructure",

            // Blueprint graph
            "BlueprintGraph",
            "Kismet",
            "KismetCompiler",
            "KismetWidgets",
            "GraphEditor",

            // Asset pipeline
            "AssetTools",
            "AssetRegistry",
            "ContentBrowser",

            // Networking / sockets
            "Sockets",
            "Networking",

            // Serialisation
            "Json",
            "JsonUtilities",

            // Web browser widget (docked chat tab)
            "WebBrowser",

            // Level editor hook
            "LevelEditor",
        });

        // Suppress deprecation warnings from UE headers on older compilers
        bLegacyPublicIncludePaths = false;
    }
}
