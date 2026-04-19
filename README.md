# ⚡ Unreal Assistant — AI Blueprint Generator

> Describe your game logic in plain English. Get executable Unreal Engine Blueprint commands instantly.

![Unreal Assistant](https://img.shields.io/badge/Powered%20by-OpenAI%20GPT--4o-8a2be2?style=for-the-badge)
![Cloudflare Pages](https://img.shields.io/badge/Deployed%20on-Cloudflare%20Pages-f38020?style=for-the-badge)
![Hono](https://img.shields.io/badge/Backend-Hono%20%2B%20TypeScript-06b6d4?style=for-the-badge)

**Live Demo:** https://unreal-assistant.pages.dev

---

## 🎯 What It Does

Unreal Assistant converts plain English descriptions into structured JSON commands that execute directly inside Unreal Engine via the MCP (Model Control Protocol) server.

**Example prompt:**
> "Create an enemy AI that detects the player within 500 units and chases them"

**Output:**
```json
{
  "commands": [
    { "action": "create_blueprint", "name": "BP_EnemyAI", "parent_class": "Character" },
    { "action": "add_variable", "blueprint": "BP_EnemyAI", "variable_name": "DetectionRadius", "variable_type": "Float", "default_value": 500.0 },
    { "action": "add_node", "blueprint": "BP_EnemyAI", "node": "Event Tick", "id": "node_0" },
    { "action": "add_node", "blueprint": "BP_EnemyAI", "node": "Branch", "id": "node_1" },
    { "action": "connect_nodes", "blueprint": "BP_EnemyAI", "from_node": "node_0", "from_pin": "Then", "to_node": "node_1", "to_pin": "Execute" },
    { "action": "compile_blueprint", "name": "BP_EnemyAI" }
  ]
}
```

---

## 🏗️ Architecture

```
Your Prompt → OpenAI GPT-4o → MCP Server (Node.js :3001) → Unreal Plugin (C++ :8080) → Blueprint ✓
```

### Components

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Landing Page** | Hono + Cloudflare Pages | Web UI + API proxy |
| **AI Brain** | OpenAI GPT-4o | Converts English → Blueprint JSON |
| **MCP Server** | Node.js + Express | Routes commands to Unreal |
| **Unreal Plugin** | C++ | Executes commands inside UE5 |

---

## 🚀 Quick Start

### 1. Web Interface (No Setup)
Visit **https://unreal-assistant.pages.dev** — works immediately with demo responses.

For live AI generation, add your OpenAI key as a Cloudflare secret:
```bash
wrangler secret put OPENAI_API_KEY
```

### 2. Full Local Setup

```bash
# Clone
git clone https://github.com/mkbrown261/unreal-assistant
cd unreal-assistant

# Install & run MCP Server
cd mcp-server
npm install
OPENAI_API_KEY=sk-... node server.js
# Runs on :3001

# Install Unreal Plugin
cp -r MCPBlueprintPlugin/ YourUEProject/Plugins/MCPBlueprint
# Enable in UE5: Edit → Plugins → MCPBlueprint → Enable → Restart
```

---

## 🧩 Available Blueprint Commands

| Command | Description |
|---------|-------------|
| `create_blueprint` | Creates a new Blueprint class |
| `add_node` | Adds an Unreal node to the graph |
| `connect_nodes` | Connects two nodes via execution or data pins |
| `add_variable` | Declares a Blueprint variable with type + default |
| `set_variable` | Sets a variable value at runtime |
| `compile_blueprint` | Compiles the Blueprint |

---

## 🎮 Supported Node Types

- **Events:** Event BeginPlay, Event Tick, Event ActorBeginOverlap, InputAction
- **Flow Control:** Branch, Sequence, ForLoop, WhileLoop, Delay
- **Math:** Add, Subtract, Multiply, Divide, Clamp, Lerp
- **Gameplay:** AI Move To, Get Player Pawn, Cast To, Destroy Actor
- **UI:** Print String, Create Widget, Add to Viewport
- **Utility:** Timeline, Set Timer, Play Sound, Spawn Actor

---

## 📁 Project Structure

```
unreal-assistant/
├── src/
│   └── index.tsx          # Hono app — landing page + /api/generate
├── mcp-server/
│   ├── server.js          # Express MCP bridge
│   ├── routes/
│   │   └── blueprint.js   # /api/blueprint/execute route
│   └── services/
│       └── unrealClient.js # Sends commands to Unreal :8080
├── MCPBlueprintPlugin/
│   └── Source/MCPBlueprint/
│       ├── Private/
│       │   ├── MCPServer.cpp        # HTTP server inside Unreal
│       │   └── BlueprintExecutor.cpp # Executes JSON commands
│       └── Public/
│           └── BlueprintExecutor.h
├── wrangler.jsonc
├── vite.config.ts
└── package.json
```

---

## 🌐 Deployment

Deployed on **Cloudflare Pages** with edge computing.

```bash
npm run build
wrangler pages deploy dist --project-name unreal-assistant
```

---

## 📄 License

MIT — free to use and modify.
