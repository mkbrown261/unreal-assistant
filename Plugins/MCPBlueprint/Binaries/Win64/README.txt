Pre-built binaries for Windows (Win64) go here after compiling.

To compile:
  1. Right-click your .uproject file → "Generate Visual Studio project files"
  2. Open the .sln in Visual Studio 2022
  3. Set config to "Development Editor" / Win64
  4. Build → your DLLs appear here automatically

Files that will be generated:
  UnrealEditor-MCPBlueprint.dll
  UnrealEditor-MCPBlueprint.pdb

Once compiled, zip the entire Plugins/MCPBlueprint/ folder and distribute it.
Users with matching UE version and Windows can then use it without compiling.
