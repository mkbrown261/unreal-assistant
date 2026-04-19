// Copyright Unreal Assistant. All Rights Reserved.

using UnrealBuildTool;

public class MCPBlueprint : ModuleRules
{
    public MCPBlueprint(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "InputCore",
            "HTTP",
            "Json",
            "JsonUtilities",
            "Sockets",
            "Networking",
        });

        PrivateDependencyModuleNames.AddRange(new string[]
        {
            "Kismet",
            "KismetCompiler",
            "BlueprintGraph",
            "UnrealEd",
            "EditorStyle",
            "Slate",
            "SlateCore",
            "ToolMenus",
        });
    }
}
