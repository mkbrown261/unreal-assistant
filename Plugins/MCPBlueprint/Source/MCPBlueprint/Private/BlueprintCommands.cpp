// BlueprintCommands.cpp
// Full Blueprint graph manipulation via C++ UE5 APIs.
// All handlers MUST be called on the game/editor thread.
// FBlueprintCommandDispatcher::Dispatch() enforces this via Async + blocking wait.

#include "BlueprintCommands.h"

// ── UE Core ──────────────────────────────────────────────────────────────────
#include "CoreMinimal.h"
#include "Engine/Blueprint.h"
#include "Engine/BlueprintGeneratedClass.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetToolsModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "Async/Async.h"
#include "Misc/ScopeLock.h"

// ── Blueprint factories ───────────────────────────────────────────────────────
#include "Factories/BlueprintFactory.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "KismetCompiler.h"

// ── Editor asset helpers ──────────────────────────────────────────────────────
#include "EditorAssetLibrary.h"
#include "AssetRegistry/AssetData.h"

// ── Graph / Node types ────────────────────────────────────────────────────────
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraph/EdGraphSchema.h"
#include "EdGraphSchema_K2.h"

#include "K2Node_Event.h"
#include "K2Node_CallFunction.h"
#include "K2Node_IfThenElse.h"          // Branch
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "K2Node_ExecutionSequence.h"   // Sequence
#include "K2Node_Delay.h"               // conceptually — actual delay is a function call

// ── KismetSystemLibrary (for PrintString etc.) ────────────────────────────────
#include "Kismet/KismetSystemLibrary.h"
#include "Kismet/GameplayStatics.h"

// ── JSON ──────────────────────────────────────────────────────────────────────
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"

// ── Pin type construction ─────────────────────────────────────────────────────
#include "EdGraphSchema_K2.h"   // FEdGraphPinType constants

// ── HAL ───────────────────────────────────────────────────────────────────────
#include "HAL/PlatformProcess.h"

// ---------------------------------------------------------------------------
// Static member initialisation
// ---------------------------------------------------------------------------

TMap<FString, TMap<FString, TWeakObjectPtr<UK2Node>>> FBlueprintCommandDispatcher::NodeRegistry;
FCriticalSection FBlueprintCommandDispatcher::RegistryLock;

// ---------------------------------------------------------------------------
// Helper: run a lambda on the game thread, block until done, return result.
// ---------------------------------------------------------------------------

template<typename TRet>
static TRet RunOnGameThread(TFunction<TRet()> Fn)
{
    if (IsInGameThread())
    {
        return Fn();
    }

    TPromise<TRet> Promise;
    TFuture<TRet> Future = Promise.GetFuture();

    AsyncTask(ENamedThreads::GameThread, [Fn = MoveTemp(Fn), Promise = MoveTemp(Promise)]() mutable
    {
        Promise.SetValue(Fn());
    });

    Future.Wait();
    return Future.Get();
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

TSharedPtr<FJsonObject> FBlueprintCommandDispatcher::MakeOk(const FString& Msg)
{
    TSharedPtr<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetBoolField(TEXT("success"), true);
    Obj->SetStringField(TEXT("message"), Msg);
    return Obj;
}

TSharedPtr<FJsonObject> FBlueprintCommandDispatcher::MakeErr(const FString& Msg)
{
    TSharedPtr<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetBoolField(TEXT("success"), false);
    Obj->SetStringField(TEXT("error"), Msg);
    return Obj;
}

void FBlueprintCommandDispatcher::EnsureDir(const FString& Path)
{
    if (!UEditorAssetLibrary::DoesDirectoryExist(Path))
    {
        UEditorAssetLibrary::MakeDirectory(Path);
    }
}

UBlueprint* FBlueprintCommandDispatcher::LoadBP(const FString& AssetPath)
{
    // Try /Game/MCP/BP_Foo.BP_Foo first (canonical form), then bare path
    FString Clean = AssetPath.TrimStartAndEnd().TrimEnd(TEXT("/"));
    FString AssetName = Clean;
    int32 SlashIdx = INDEX_NONE;
    if (Clean.FindLastChar(TEXT('/'), SlashIdx))
    {
        AssetName = Clean.RightChop(SlashIdx + 1);
    }
    FString Full = FString::Printf(TEXT("%s.%s"), *Clean, *AssetName);

    UBlueprint* BP = Cast<UBlueprint>(StaticLoadObject(UBlueprint::StaticClass(), nullptr, *Full));
    if (!BP)
    {
        BP = Cast<UBlueprint>(StaticLoadObject(UBlueprint::StaticClass(), nullptr, *Clean));
    }
    return BP;
}

// ---------------------------------------------------------------------------
// Node registry
// ---------------------------------------------------------------------------

FString FBlueprintCommandDispatcher::RegisterNode(const FString& BPName, UK2Node* Node)
{
    FScopeLock Lock(&RegistryLock);

    if (!NodeRegistry.Contains(BPName))
    {
        NodeRegistry.Add(BPName, TMap<FString, TWeakObjectPtr<UK2Node>>());
    }

    TMap<FString, TWeakObjectPtr<UK2Node>>& BPMap = NodeRegistry[BPName];

    // Generate a deterministic ID: ClassName_Index
    FString ClassName = Node->GetClass()->GetName();
    // Shorten "K2Node_CallFunction" → "CallFunction" for readability
    ClassName.RemoveFromStart(TEXT("K2Node_"));
    ClassName.RemoveFromStart(TEXT("K2"));

    int32 Index = 0;
    FString Id;
    do
    {
        Id = FString::Printf(TEXT("%s_%d"), *ClassName, Index++);
    } while (BPMap.Contains(Id));

    BPMap.Add(Id, TWeakObjectPtr<UK2Node>(Node));
    return Id;
}

UK2Node* FBlueprintCommandDispatcher::FindNode(const FString& BPName, const FString& NodeId)
{
    FScopeLock Lock(&RegistryLock);
    if (const TMap<FString, TWeakObjectPtr<UK2Node>>* BPMap = NodeRegistry.Find(BPName))
    {
        if (const TWeakObjectPtr<UK2Node>* WeakNode = BPMap->Find(NodeId))
        {
            return WeakNode->Get();
        }
    }
    return nullptr;
}

// ---------------------------------------------------------------------------
// Dispatch
// ---------------------------------------------------------------------------

TSharedPtr<FJsonObject> FBlueprintCommandDispatcher::Dispatch(const TSharedPtr<FJsonObject>& Cmd)
{
    if (!Cmd.IsValid())
    {
        return MakeErr(TEXT("Null command object"));
    }

    FString Action;
    if (!Cmd->TryGetStringField(TEXT("action"), Action))
    {
        return MakeErr(TEXT("Missing 'action' field"));
    }
    Action = Action.TrimStartAndEnd().ToLower();

    // All handlers must run on the game thread
    return RunOnGameThread<TSharedPtr<FJsonObject>>([&Action, &Cmd]() -> TSharedPtr<FJsonObject>
    {
        if (Action == TEXT("get_status"))          return HandleGetStatus(Cmd);
        if (Action == TEXT("create_blueprint"))    return HandleCreateBP(Cmd);
        if (Action == TEXT("add_variable"))        return HandleAddVariable(Cmd);
        if (Action == TEXT("add_member_variable")) return HandleAddVariable(Cmd);
        if (Action == TEXT("add_node"))            return HandleAddNode(Cmd);
        if (Action == TEXT("connect_nodes"))       return HandleConnectNodes(Cmd);
        if (Action == TEXT("compile_blueprint"))   return HandleCompile(Cmd);

        return MakeErr(FString::Printf(TEXT("Unknown action: %s"), *Action));
    });
}

// ---------------------------------------------------------------------------
// get_status
// ---------------------------------------------------------------------------

TSharedPtr<FJsonObject> FBlueprintCommandDispatcher::HandleGetStatus(const TSharedPtr<FJsonObject>& /*Cmd*/)
{
    TSharedPtr<FJsonObject> R = MakeShared<FJsonObject>();
    R->SetBoolField(TEXT("success"), true);
    R->SetStringField(TEXT("version"), TEXT("3.0.0"));
    R->SetStringField(TEXT("server"), TEXT("MCPBlueprint C++ TCP server"));
    R->SetStringField(TEXT("port"), TEXT("55557"));
    return R;
}

// ---------------------------------------------------------------------------
// create_blueprint
// ---------------------------------------------------------------------------

// Parent class string → UClass* lookup table
static UClass* ResolveParentClass(const FString& Name)
{
    const TMap<FString, FString> ClassPaths =
    {
        { TEXT("actor"),                    TEXT("/Script/Engine.Actor") },
        { TEXT("character"),                TEXT("/Script/Engine.Character") },
        { TEXT("pawn"),                     TEXT("/Script/Engine.Pawn") },
        { TEXT("gamemodebase"),             TEXT("/Script/Engine.GameModeBase") },
        { TEXT("gamemode"),                 TEXT("/Script/Engine.GameModeBase") },
        { TEXT("playercontroller"),         TEXT("/Script/Engine.PlayerController") },
        { TEXT("actorcomponent"),           TEXT("/Script/Engine.ActorComponent") },
        { TEXT("scenecomponent"),           TEXT("/Script/Engine.SceneComponent") },
        { TEXT("gameinstance"),             TEXT("/Script/Engine.GameInstance") },
        { TEXT("gamestate"),                TEXT("/Script/Engine.GameState") },
        { TEXT("playerstate"),              TEXT("/Script/Engine.PlayerState") },
        { TEXT("hud"),                      TEXT("/Script/Engine.HUD") },
        { TEXT("userwidget"),               TEXT("/Script/UMG.UserWidget") },
        { TEXT("animinstance"),             TEXT("/Script/Engine.AnimInstance") },
        { TEXT("blueprintfunctionlibrary"), TEXT("/Script/Engine.BlueprintFunctionLibrary") },
    };

    FString Lower = Name.ToLower();
    if (const FString* Path = ClassPaths.Find(Lower))
    {
        if (UClass* C = LoadClass<UObject>(nullptr, **Path))
        {
            return C;
        }
    }

    // Try direct load (user may have passed a full path)
    if (UClass* C = LoadClass<UObject>(nullptr, *Name))
    {
        return C;
    }

    return AActor::StaticClass();
}

TSharedPtr<FJsonObject> FBlueprintCommandDispatcher::HandleCreateBP(const TSharedPtr<FJsonObject>& Cmd)
{
    FString Name, ParentClass, Path;
    Cmd->TryGetStringField(TEXT("name"),         Name);
    Cmd->TryGetStringField(TEXT("parent_class"),  ParentClass);
    Cmd->TryGetStringField(TEXT("path"),          Path);

    if (Name.IsEmpty())  { return MakeErr(TEXT("create_blueprint: 'name' is required")); }
    if (Path.IsEmpty())  { Path = TEXT("/Game/MCP"); }

    Path.TrimEndInline(TEXT("/"));
    EnsureDir(Path);

    FString AssetPath = FString::Printf(TEXT("%s/%s"), *Path, *Name);

    // Already exists?
    if (UEditorAssetLibrary::DoesAssetExist(AssetPath))
    {
        return MakeOk(FString::Printf(TEXT("Already exists: %s"), *AssetPath));
    }

    UClass* Parent = ResolveParentClass(ParentClass.IsEmpty() ? TEXT("Actor") : ParentClass);

    UBlueprintFactory* Factory = NewObject<UBlueprintFactory>();
    Factory->ParentClass = Parent;

    IAssetTools& AssetTools = FModuleManager::LoadModuleChecked<FAssetToolsModule>(TEXT("AssetTools")).Get();
    UObject* NewAsset = AssetTools.CreateAsset(Name, Path, UBlueprint::StaticClass(), Factory);

    UBlueprint* BP = Cast<UBlueprint>(NewAsset);
    if (!BP)
    {
        return MakeErr(FString::Printf(TEXT("Failed to create Blueprint at %s"), *AssetPath));
    }

    // Initial compile + save
    FKismetEditorUtilities::CompileBlueprint(BP, EBlueprintCompileOptions::SkipGarbageCollection);
    UEditorAssetLibrary::SaveAsset(AssetPath, false);

    TSharedPtr<FJsonObject> R = MakeShared<FJsonObject>();
    R->SetBoolField(TEXT("success"), true);
    R->SetStringField(TEXT("message"), FString::Printf(TEXT("Created %s"), *AssetPath));
    R->SetStringField(TEXT("asset_path"), AssetPath);
    return R;
}

// ---------------------------------------------------------------------------
// add_variable
// ---------------------------------------------------------------------------

static FEdGraphPinType BuildPinType(const FString& VarTypeRaw)
{
    FEdGraphPinType PT;
    PT.ContainerType = EPinContainerType::None;
    PT.bIsReference  = false;
    PT.bIsConst      = false;

    FString VT = VarTypeRaw.ToLower().TrimStartAndEnd();

    if (VT == TEXT("bool") || VT == TEXT("boolean"))
    {
        PT.PinCategory = UEdGraphSchema_K2::PC_Boolean;
    }
    else if (VT == TEXT("int") || VT == TEXT("integer") || VT == TEXT("int32"))
    {
        PT.PinCategory = UEdGraphSchema_K2::PC_Int;
    }
    else if (VT == TEXT("int64"))
    {
        PT.PinCategory = UEdGraphSchema_K2::PC_Int64;
    }
    else if (VT == TEXT("float") || VT == TEXT("double"))
    {
        PT.PinCategory = UEdGraphSchema_K2::PC_Real;
        PT.PinSubCategory = UEdGraphSchema_K2::PC_Float;
    }
    else if (VT == TEXT("string") || VT == TEXT("str"))
    {
        PT.PinCategory = UEdGraphSchema_K2::PC_String;
    }
    else if (VT == TEXT("name"))
    {
        PT.PinCategory = UEdGraphSchema_K2::PC_Name;
    }
    else if (VT == TEXT("text"))
    {
        PT.PinCategory = UEdGraphSchema_K2::PC_Text;
    }
    else if (VT == TEXT("vector") || VT == TEXT("vec") || VT == TEXT("vector3"))
    {
        PT.PinCategory = UEdGraphSchema_K2::PC_Struct;
        PT.PinSubCategoryObject = TBaseStructure<FVector>::Get();
    }
    else if (VT == TEXT("rotator") || VT == TEXT("rot"))
    {
        PT.PinCategory = UEdGraphSchema_K2::PC_Struct;
        PT.PinSubCategoryObject = TBaseStructure<FRotator>::Get();
    }
    else if (VT == TEXT("transform"))
    {
        PT.PinCategory = UEdGraphSchema_K2::PC_Struct;
        PT.PinSubCategoryObject = TBaseStructure<FTransform>::Get();
    }
    else if (VT == TEXT("color") || VT == TEXT("linearcolor"))
    {
        PT.PinCategory = UEdGraphSchema_K2::PC_Struct;
        PT.PinSubCategoryObject = TBaseStructure<FLinearColor>::Get();
    }
    else if (VT == TEXT("object") || VT == TEXT("obj"))
    {
        PT.PinCategory = UEdGraphSchema_K2::PC_Object;
        PT.PinSubCategoryObject = UObject::StaticClass();
    }
    else
    {
        // Default to float
        PT.PinCategory = UEdGraphSchema_K2::PC_Real;
        PT.PinSubCategory = UEdGraphSchema_K2::PC_Float;
    }

    return PT;
}

TSharedPtr<FJsonObject> FBlueprintCommandDispatcher::HandleAddVariable(const TSharedPtr<FJsonObject>& Cmd)
{
    FString BPPath, VarName, VarType, DefaultVal;
    Cmd->TryGetStringField(TEXT("blueprint_path"), BPPath);
    Cmd->TryGetStringField(TEXT("var_name"),        VarName);
    Cmd->TryGetStringField(TEXT("var_type"),         VarType);
    Cmd->TryGetStringField(TEXT("default_value"),    DefaultVal);

    // Fallback field aliases
    if (BPPath.IsEmpty()) Cmd->TryGetStringField(TEXT("blueprint"), BPPath);
    if (BPPath.IsEmpty()) Cmd->TryGetStringField(TEXT("name"),       BPPath);
    if (VarName.IsEmpty()) Cmd->TryGetStringField(TEXT("variable_name"), VarName);
    if (VarType.IsEmpty()) Cmd->TryGetStringField(TEXT("variable_type"), VarType);

    if (BPPath.IsEmpty()) { return MakeErr(TEXT("add_variable: 'blueprint_path' is required")); }
    if (VarName.IsEmpty()){ return MakeErr(TEXT("add_variable: 'var_name' is required")); }
    if (VarType.IsEmpty()) { VarType = TEXT("float"); }

    UBlueprint* BP = LoadBP(BPPath);
    if (!BP) { return MakeErr(FString::Printf(TEXT("Blueprint not found: %s"), *BPPath)); }

    // Compile first to ensure BP is in a valid state
    FKismetEditorUtilities::CompileBlueprint(BP, EBlueprintCompileOptions::SkipGarbageCollection);

    // Check if variable already exists
    if (FBlueprintEditorUtils::FindMemberVariableGuidByName(BP, FName(*VarName)) != FGuid())
    {
        return MakeOk(FString::Printf(TEXT("Variable '%s' already exists in %s"), *VarName, *BPPath));
    }

    FEdGraphPinType PinType = BuildPinType(VarType);
    bool bAdded = FBlueprintEditorUtils::AddMemberVariable(BP, FName(*VarName), PinType);
    if (!bAdded)
    {
        return MakeErr(FString::Printf(TEXT("AddMemberVariable returned false for '%s'"), *VarName));
    }

    // Set default value (best-effort)
    if (!DefaultVal.IsEmpty())
    {
        if (FProperty* Prop = FindFProperty<FProperty>(BP->GeneratedClass, FName(*VarName)))
        {
            FBlueprintEditorUtils::PropertyValueFromString(Prop, DefaultVal,
                reinterpret_cast<uint8*>(BP->GeneratedClass->GetDefaultObject()));
        }
    }

    FKismetEditorUtilities::CompileBlueprint(BP, EBlueprintCompileOptions::SkipGarbageCollection);
    UEditorAssetLibrary::SaveAsset(BPPath.TrimEnd(TEXT("/")), false);

    return MakeOk(FString::Printf(TEXT("Added variable '%s' (%s) to %s"), *VarName, *VarType, *BPPath));
}

// ---------------------------------------------------------------------------
// add_node
// ---------------------------------------------------------------------------

// Get (or create) the EventGraph of a Blueprint
static UEdGraph* GetEventGraph(UBlueprint* BP)
{
    for (UEdGraph* Graph : BP->UbergraphPages)
    {
        if (Graph && Graph->GetFName() == TEXT("EventGraph"))
        {
            return Graph;
        }
    }
    // Create EventGraph if none exists
    UEdGraph* NewGraph = FBlueprintEditorUtils::CreateNewGraph(
        BP, FName(TEXT("EventGraph")),
        UEdGraph::StaticClass(),
        UEdGraphSchema_K2::StaticClass());
    FBlueprintEditorUtils::AddUbergraphPage(BP, NewGraph);
    return NewGraph;
}

TSharedPtr<FJsonObject> FBlueprintCommandDispatcher::HandleAddNode(const TSharedPtr<FJsonObject>& Cmd)
{
    FString BPName, NodeType, EventType, Message, VariableName, FuncName;
    int32   PosX = 0, PosY = 0;

    Cmd->TryGetStringField(TEXT("blueprint_name"), BPName);
    if (BPName.IsEmpty()) Cmd->TryGetStringField(TEXT("blueprint"), BPName);
    Cmd->TryGetStringField(TEXT("node_type"),      NodeType);
    Cmd->TryGetNumberField(TEXT("pos_x"),           PosX);
    Cmd->TryGetNumberField(TEXT("pos_y"),           PosY);
    Cmd->TryGetStringField(TEXT("event_type"),      EventType);
    Cmd->TryGetStringField(TEXT("message"),         Message);
    Cmd->TryGetStringField(TEXT("variable_name"),   VariableName);
    Cmd->TryGetStringField(TEXT("function_name"),   FuncName);

    if (BPName.IsEmpty()) { return MakeErr(TEXT("add_node: 'blueprint_name' required")); }
    if (NodeType.IsEmpty()){ return MakeErr(TEXT("add_node: 'node_type' required")); }

    // Find the blueprint asset — try common paths
    UBlueprint* BP = LoadBP(BPName);
    if (!BP)
    {
        // Try with /Game/MCP/ prefix
        FString WithPath = FString::Printf(TEXT("/Game/MCP/%s"), *BPName);
        BP = LoadBP(WithPath);
    }
    if (!BP) { return MakeErr(FString::Printf(TEXT("Blueprint not found: %s"), *BPName)); }

    UEdGraph* Graph = GetEventGraph(BP);
    if (!Graph) { return MakeErr(TEXT("Could not get EventGraph")); }

    const UEdGraphSchema_K2* Schema = Cast<UEdGraphSchema_K2>(Graph->GetSchema());
    if (!Schema) { return MakeErr(TEXT("No K2 schema on EventGraph")); }

    UK2Node* NewNode = nullptr;
    FString  NodeId;
    FString  NT = NodeType.ToLower().TrimStartAndEnd();

    // ── Event node ─────────────────────────────────────────────────────────
    if (NT == TEXT("event") || NT == TEXT("event_node"))
    {
        FString EvType = EventType.IsEmpty() ? TEXT("BeginPlay") : EventType;

        // Determine the function name for the event
        FName EventFuncName;
        if (EvType.Contains(TEXT("BeginPlay")) || EvType.Contains(TEXT("beginplay")))
            EventFuncName = TEXT("ReceiveBeginPlay");
        else if (EvType.Contains(TEXT("Tick")) || EvType.Contains(TEXT("tick")))
            EventFuncName = TEXT("ReceiveTick");
        else if (EvType.Contains(TEXT("EndPlay")) || EvType.Contains(TEXT("endplay")))
            EventFuncName = TEXT("ReceiveEndPlay");
        else
            EventFuncName = FName(*EvType);

        UK2Node_Event* EventNode = NewObject<UK2Node_Event>(Graph);
        EventNode->EventReference.SetExternalMember(EventFuncName, BP->ParentClass);
        EventNode->bOverrideFunction = true;
        Graph->AddNode(EventNode, false, false);
        EventNode->CreateNewGuid();
        EventNode->PostPlacedNewNode();
        EventNode->NodePosX = PosX;
        EventNode->NodePosY = PosY;
        EventNode->AllocateDefaultPins();
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);

        NewNode = EventNode;
    }
    // ── Print String ────────────────────────────────────────────────────────
    else if (NT == TEXT("print") || NT == TEXT("printstring") || NT == TEXT("print_string"))
    {
        UFunction* PrintFunc = UKismetSystemLibrary::StaticClass()
            ->FindFunctionByName(TEXT("PrintString"));

        UK2Node_CallFunction* PrintNode = NewObject<UK2Node_CallFunction>(Graph);
        PrintNode->FunctionReference.SetExternalMember(TEXT("PrintString"), UKismetSystemLibrary::StaticClass());
        Graph->AddNode(PrintNode, false, false);
        PrintNode->CreateNewGuid();
        PrintNode->PostPlacedNewNode();
        PrintNode->NodePosX = PosX;
        PrintNode->NodePosY = PosY;
        PrintNode->AllocateDefaultPins();

        // Set the InString default value if message provided
        if (!Message.IsEmpty())
        {
            if (UEdGraphPin* InStringPin = PrintNode->FindPin(TEXT("InString")))
            {
                InStringPin->DefaultValue = Message;
            }
        }
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
        NewNode = PrintNode;
    }
    // ── Branch (If-Then-Else) ────────────────────────────────────────────────
    else if (NT == TEXT("branch") || NT == TEXT("ifthenelse") || NT == TEXT("if"))
    {
        UK2Node_IfThenElse* BranchNode = NewObject<UK2Node_IfThenElse>(Graph);
        Graph->AddNode(BranchNode, false, false);
        BranchNode->CreateNewGuid();
        BranchNode->PostPlacedNewNode();
        BranchNode->NodePosX = PosX;
        BranchNode->NodePosY = PosY;
        BranchNode->AllocateDefaultPins();
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
        NewNode = BranchNode;
    }
    // ── Variable Get ────────────────────────────────────────────────────────
    else if (NT == TEXT("variableget") || NT == TEXT("variable_get") || NT == TEXT("get"))
    {
        if (VariableName.IsEmpty())
        {
            return MakeErr(TEXT("add_node VariableGet: 'variable_name' required"));
        }
        UK2Node_VariableGet* GetNode = NewObject<UK2Node_VariableGet>(Graph);
        GetNode->VariableReference.SetSelfMember(FName(*VariableName));
        Graph->AddNode(GetNode, false, false);
        GetNode->CreateNewGuid();
        GetNode->PostPlacedNewNode();
        GetNode->NodePosX = PosX;
        GetNode->NodePosY = PosY;
        GetNode->AllocateDefaultPins();
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
        NewNode = GetNode;
    }
    // ── Variable Set ────────────────────────────────────────────────────────
    else if (NT == TEXT("variableset") || NT == TEXT("variable_set") || NT == TEXT("set"))
    {
        if (VariableName.IsEmpty())
        {
            return MakeErr(TEXT("add_node VariableSet: 'variable_name' required"));
        }
        UK2Node_VariableSet* SetNode = NewObject<UK2Node_VariableSet>(Graph);
        SetNode->VariableReference.SetSelfMember(FName(*VariableName));
        Graph->AddNode(SetNode, false, false);
        SetNode->CreateNewGuid();
        SetNode->PostPlacedNewNode();
        SetNode->NodePosX = PosX;
        SetNode->NodePosY = PosY;
        SetNode->AllocateDefaultPins();
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
        NewNode = SetNode;
    }
    // ── Sequence ─────────────────────────────────────────────────────────────
    else if (NT == TEXT("sequence"))
    {
        UK2Node_ExecutionSequence* SeqNode = NewObject<UK2Node_ExecutionSequence>(Graph);
        Graph->AddNode(SeqNode, false, false);
        SeqNode->CreateNewGuid();
        SeqNode->PostPlacedNewNode();
        SeqNode->NodePosX = PosX;
        SeqNode->NodePosY = PosY;
        SeqNode->AllocateDefaultPins();
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
        NewNode = SeqNode;
    }
    // ── Delay ────────────────────────────────────────────────────────────────
    else if (NT == TEXT("delay"))
    {
        // Delay is UKismetSystemLibrary::Delay (a latent action)
        UK2Node_CallFunction* DelayNode = NewObject<UK2Node_CallFunction>(Graph);
        DelayNode->FunctionReference.SetExternalMember(TEXT("Delay"), UKismetSystemLibrary::StaticClass());
        Graph->AddNode(DelayNode, false, false);
        DelayNode->CreateNewGuid();
        DelayNode->PostPlacedNewNode();
        DelayNode->NodePosX = PosX;
        DelayNode->NodePosY = PosY;
        DelayNode->AllocateDefaultPins();
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
        NewNode = DelayNode;
    }
    // ── Generic CallFunction ─────────────────────────────────────────────────
    else if (NT == TEXT("callfunction") || NT == TEXT("call_function") || !FuncName.IsEmpty())
    {
        FString TargetFunc = FuncName.IsEmpty() ? FuncName : FuncName;
        if (TargetFunc.IsEmpty())
        {
            return MakeErr(TEXT("add_node CallFunction: 'function_name' required"));
        }

        // Try to find the function on known utility classes
        UClass* FuncClass = nullptr;
        UFunction* TargetFn = nullptr;
        TArray<UClass*> SearchClasses = {
            UKismetSystemLibrary::StaticClass(),
            UGameplayStatics::StaticClass(),
        };
        for (UClass* C : SearchClasses)
        {
            TargetFn = C->FindFunctionByName(*TargetFunc);
            if (TargetFn) { FuncClass = C; break; }
        }

        UK2Node_CallFunction* CFNode = NewObject<UK2Node_CallFunction>(Graph);
        if (TargetFn && FuncClass)
        {
            CFNode->FunctionReference.SetExternalMember(FName(*TargetFunc), FuncClass);
        }
        else
        {
            // Self-member fallback
            CFNode->FunctionReference.SetSelfMember(FName(*TargetFunc));
        }
        Graph->AddNode(CFNode, false, false);
        CFNode->CreateNewGuid();
        CFNode->PostPlacedNewNode();
        CFNode->NodePosX = PosX;
        CFNode->NodePosY = PosY;
        CFNode->AllocateDefaultPins();
        FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
        NewNode = CFNode;
    }
    else
    {
        return MakeErr(FString::Printf(TEXT("Unknown node_type '%s'"), *NodeType));
    }

    if (!NewNode) { return MakeErr(TEXT("Node creation failed")); }

    // Register and return the ID
    FString BPShortName = BPName;
    {
        int32 Slash = INDEX_NONE;
        if (BPShortName.FindLastChar(TEXT('/'), Slash))
            BPShortName = BPShortName.RightChop(Slash + 1);
    }
    NodeId = RegisterNode(BPShortName, NewNode);

    TSharedPtr<FJsonObject> R = MakeShared<FJsonObject>();
    R->SetBoolField(TEXT("success"), true);
    R->SetStringField(TEXT("node_id"), NodeId);
    R->SetStringField(TEXT("message"), FString::Printf(TEXT("Added node '%s' (id=%s)"), *NodeType, *NodeId));
    return R;
}

// ---------------------------------------------------------------------------
// connect_nodes
// ---------------------------------------------------------------------------

TSharedPtr<FJsonObject> FBlueprintCommandDispatcher::HandleConnectNodes(const TSharedPtr<FJsonObject>& Cmd)
{
    FString BPName, SrcId, SrcPin, DstId, DstPin;

    Cmd->TryGetStringField(TEXT("blueprint_name"),  BPName);
    if (BPName.IsEmpty()) Cmd->TryGetStringField(TEXT("blueprint"), BPName);
    Cmd->TryGetStringField(TEXT("source_node_id"),  SrcId);
    Cmd->TryGetStringField(TEXT("source_pin"),       SrcPin);
    Cmd->TryGetStringField(TEXT("target_node_id"),  DstId);
    Cmd->TryGetStringField(TEXT("target_pin"),       DstPin);

    if (BPName.IsEmpty()) { return MakeErr(TEXT("connect_nodes: 'blueprint_name' required")); }
    if (SrcId.IsEmpty())  { return MakeErr(TEXT("connect_nodes: 'source_node_id' required")); }
    if (DstId.IsEmpty())  { return MakeErr(TEXT("connect_nodes: 'target_node_id' required")); }
    if (SrcPin.IsEmpty()) { SrcPin = TEXT("then"); }
    if (DstPin.IsEmpty()) { DstPin = TEXT("execute"); }

    // Short name for registry lookup
    FString BPShortName = BPName;
    {
        int32 Slash = INDEX_NONE;
        if (BPShortName.FindLastChar(TEXT('/'), Slash))
            BPShortName = BPShortName.RightChop(Slash + 1);
    }

    UK2Node* SrcNode = FindNode(BPShortName, SrcId);
    if (!SrcNode) { return MakeErr(FString::Printf(TEXT("Source node not found: %s"), *SrcId)); }

    UK2Node* DstNode = FindNode(BPShortName, DstId);
    if (!DstNode) { return MakeErr(FString::Printf(TEXT("Target node not found: %s"), *DstId)); }

    // Find pins by name (case-insensitive search)
    auto FindPin = [](UK2Node* Node, const FString& PinName) -> UEdGraphPin*
    {
        // Exact match first
        UEdGraphPin* P = Node->FindPin(PinName);
        if (P) return P;

        // Case-insensitive
        for (UEdGraphPin* Pin : Node->Pins)
        {
            if (Pin && Pin->PinName.ToString().Equals(PinName, ESearchCase::IgnoreCase))
                return Pin;
        }
        return nullptr;
    };

    UEdGraphPin* PinA = FindPin(SrcNode, SrcPin);
    if (!PinA) { return MakeErr(FString::Printf(TEXT("Source pin '%s' not found on node %s"), *SrcPin, *SrcId)); }

    UEdGraphPin* PinB = FindPin(DstNode, DstPin);
    if (!PinB) { return MakeErr(FString::Printf(TEXT("Target pin '%s' not found on node %s"), *DstPin, *DstId)); }

    UEdGraph* Graph = SrcNode->GetGraph();
    const UEdGraphSchema* Schema = Graph->GetSchema();
    FPinConnectionResponse Resp = Schema->CanCreateConnection(PinA, PinB);

    if (Resp.Response == CONNECT_RESPONSE_DISALLOW)
    {
        return MakeErr(FString::Printf(TEXT("Cannot connect pins: %s"), *Resp.Message.ToString()));
    }

    bool bConnected = Schema->TryCreateConnection(PinA, PinB);
    if (!bConnected)
    {
        return MakeErr(FString::Printf(TEXT("TryCreateConnection failed (%s.%s → %s.%s)"),
            *SrcId, *SrcPin, *DstId, *DstPin));
    }

    UBlueprint* BP = FBlueprintEditorUtils::FindBlueprintForNode(SrcNode);
    if (BP)
    {
        FBlueprintEditorUtils::MarkBlueprintAsModified(BP);
    }

    return MakeOk(FString::Printf(TEXT("Connected %s.%s → %s.%s"), *SrcId, *SrcPin, *DstId, *DstPin));
}

// ---------------------------------------------------------------------------
// compile_blueprint
// ---------------------------------------------------------------------------

TSharedPtr<FJsonObject> FBlueprintCommandDispatcher::HandleCompile(const TSharedPtr<FJsonObject>& Cmd)
{
    FString BPPath;
    Cmd->TryGetStringField(TEXT("path"),           BPPath);
    if (BPPath.IsEmpty()) Cmd->TryGetStringField(TEXT("blueprint_path"), BPPath);
    if (BPPath.IsEmpty()) Cmd->TryGetStringField(TEXT("name"),           BPPath);

    if (BPPath.IsEmpty()) { return MakeErr(TEXT("compile_blueprint: 'path' is required")); }

    UBlueprint* BP = LoadBP(BPPath);
    if (!BP) { return MakeErr(FString::Printf(TEXT("Blueprint not found: %s"), *BPPath)); }

    FBlueprintEditorUtils::ReconstructAllNodes(BP);
    FKismetEditorUtilities::CompileBlueprint(BP, EBlueprintCompileOptions::SkipGarbageCollection);
    UEditorAssetLibrary::SaveAsset(BPPath.TrimEnd(TEXT("/")), false);

    return MakeOk(FString::Printf(TEXT("Compiled and saved %s"), *BPPath));
}
