#!/usr/bin/env python3
"""
mcp_claude_server.py — MCP Blueprint Generator for Claude Desktop / Cursor / Windsurf
Version: 3.0.0

This MCP server connects Claude Desktop (or any MCP client) to Unreal Engine 5.
When you chat with Claude, it can call these tools to build Blueprints inside UE.

SETUP:
  1. Unreal Engine must be open with the MCPBlueprint plugin enabled (port 8080 running)
  2. Add this server to Claude Desktop config (see README)
  3. Chat with Claude — ask it to build Blueprints

USAGE (Claude Desktop config):
  {
    "mcpServers": {
      "unreal-blueprint": {
        "command": "python3",
        "args": ["/path/to/mcp_claude_server.py"],
        "env": {
          "OPENROUTER_API_KEY": "sk-or-v1-...",
          "UE_HOST": "localhost",
          "UE_PORT": "8080"
        }
      }
    }
  }
"""

import json
import os
import sys
import urllib.request
import urllib.error
from typing import Any

# ── MCP protocol (stdio transport) ────────────────────────────────────────────

def _send(msg: dict):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

def _read() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    try:
        return json.loads(line.strip())
    except Exception:
        return None

# ── Config ────────────────────────────────────────────────────────────────────

UE_BASE = f"http://{os.environ.get('UE_HOST', 'localhost')}:{os.environ.get('UE_PORT', '8080')}"

MODELS = [
    {"id": "anthropic/claude-sonnet-4-5",     "name": "Claude Sonnet 4.5 (Recommended)"},
    {"id": "anthropic/claude-opus-4-5",        "name": "Claude Opus 4.5"},
    {"id": "anthropic/claude-3-7-sonnet",      "name": "Claude 3.7 Sonnet"},
    {"id": "anthropic/claude-3-5-haiku",       "name": "Claude Haiku 3.5 (Fast)"},
    {"id": "google/gemini-2.5-pro-preview",    "name": "Gemini 2.5 Pro"},
    {"id": "google/gemini-2.5-flash-preview",  "name": "Gemini 2.5 Flash"},
    {"id": "deepseek/deepseek-chat",           "name": "DeepSeek V3"},
    {"id": "deepseek/deepseek-r1",             "name": "DeepSeek R1 (Reasoning)"},
    {"id": "openai/gpt-4o",                    "name": "GPT-4o"},
    {"id": "openai/gpt-4o-mini",               "name": "GPT-4o Mini (Fast)"},
    {"id": "openai/gpt-4.1",                   "name": "GPT-4.1"},
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ue_status() -> dict:
    """Check if UE plugin is reachable."""
    try:
        req = urllib.request.Request(f"{UE_BASE}/unreal/status", method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"status": "offline", "error": str(e)}


def _ue_execute(commands: list) -> dict:
    """Send commands to the UE plugin's /unreal/execute endpoint."""
    payload = json.dumps({"commands": commands}).encode()
    req = urllib.request.Request(
        f"{UE_BASE}/unreal/execute",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _ue_chat(message: str, model: str = "") -> dict:
    """Send a message to the UE plugin's /chat endpoint (uses built-in AI)."""
    payload = json.dumps({"message": message, "model": model}).encode()
    req = urllib.request.Request(
        f"{UE_BASE}/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _ue_config(api_key: str = "", model: str = "") -> dict:
    """Update the UE plugin config (API key, model)."""
    cfg = {}
    if api_key:
        cfg["api_key"] = api_key
    if model:
        cfg["model"] = model
    if not cfg:
        # GET config
        req = urllib.request.Request(f"{UE_BASE}/config", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read())
        except Exception as e:
            return {"error": str(e)}
    payload = json.dumps(cfg).encode()
    req = urllib.request.Request(
        f"{UE_BASE}/config",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


# ── MCP Tool definitions ──────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "ue_status",
        "description": (
            "Check if Unreal Engine is running and the MCP Blueprint plugin is active. "
            "Call this first before any Blueprint operations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "ue_build_blueprint",
        "description": (
            "Build a complete Blueprint inside Unreal Engine from a natural language description. "
            "The plugin calls AI (via OpenRouter), generates Blueprint commands, creates the asset, "
            "adds variables, function stubs, and returns wiring instructions. "
            "The Blueprint appears in Content Browser under /Game/MCP/. "
            "Use this as your primary tool for Blueprint creation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Natural language description of the Blueprint to create. Be specific about parent class, variables, and behavior."
                },
                "model": {
                    "type": "string",
                    "description": "OpenRouter model ID to use. Leave empty to use the currently configured model.",
                    "enum": [m["id"] for m in MODELS]
                }
            },
            "required": ["description"]
        }
    },
    {
        "name": "ue_execute_commands",
        "description": (
            "Execute raw Blueprint commands directly in Unreal Engine. "
            "Use this when you want precise control over Blueprint creation steps. "
            "Commands: create_blueprint, compile_blueprint, add_variable, add_function."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "commands": {
                    "type": "array",
                    "description": "List of Blueprint command objects to execute in order.",
                    "items": {
                        "type": "object",
                        "description": (
                            "A single Blueprint command. Examples:\n"
                            '{"action":"create_blueprint","name":"BP_Enemy","parent_class":"Character","path":"/Game/MCP"}\n'
                            '{"action":"compile_blueprint","path":"/Game/MCP/BP_Enemy"}\n'
                            '{"action":"add_variable","blueprint_path":"/Game/MCP/BP_Enemy","var_name":"Health","var_type":"float","default_value":"100.0"}\n'
                            '{"action":"add_function","blueprint_path":"/Game/MCP/BP_Enemy","function_name":"TakeDamage_Custom"}'
                        )
                    }
                }
            },
            "required": ["commands"]
        }
    },
    {
        "name": "ue_set_config",
        "description": (
            "Set the OpenRouter API key and/or AI model for the UE plugin. "
            "Call this once to configure the plugin before building Blueprints."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "api_key": {
                    "type": "string",
                    "description": "OpenRouter API key (starts with sk-or-v1-). Get one free at openrouter.ai/keys."
                },
                "model": {
                    "type": "string",
                    "description": "OpenRouter model ID to use for Blueprint generation.",
                    "enum": [m["id"] for m in MODELS]
                }
            },
            "required": []
        }
    },
    {
        "name": "ue_get_config",
        "description": "Get the current plugin configuration: API key status and selected model.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "ue_list_models",
        "description": "List all available AI models you can use for Blueprint generation via OpenRouter.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "ue_clear_history",
        "description": "Clear the Blueprint generation conversation history in the UE plugin.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

# ── Tool handlers ─────────────────────────────────────────────────────────────

def handle_tool(name: str, args: dict) -> str:

    if name == "ue_status":
        result = _ue_status()
        if result.get("status") == "ok":
            return (
                "✅ Unreal Engine is running and the MCP Blueprint plugin is active.\n"
                f"Plugin version: {result.get('version', 'unknown')}\n"
                "You can now build Blueprints using ue_build_blueprint."
            )
        else:
            return (
                "❌ Cannot reach Unreal Engine plugin.\n"
                f"Error: {result.get('error', 'unknown')}\n\n"
                "Make sure:\n"
                "1. Unreal Engine is open\n"
                "2. The MCPBlueprint plugin is enabled (Edit → Plugins → MCP Blueprint Generator)\n"
                f"3. The plugin server is running on {UE_BASE}"
            )

    elif name == "ue_build_blueprint":
        description = args.get("description", "")
        model = args.get("model", "")
        if not description:
            return "❌ description is required."
        result = _ue_chat(description, model)
        if result.get("error"):
            return f"❌ Error: {result['error']}"
        reply = result.get("reply", "No reply from plugin.")
        exec_summary = result.get("exec_summary", "")
        out = reply
        if exec_summary:
            out += f"\n\n**Execution results:**\n{exec_summary}"
        return out

    elif name == "ue_execute_commands":
        commands = args.get("commands", [])
        if not commands:
            return "❌ commands list is required."
        result = _ue_execute(commands)
        if result.get("ok") is False:
            return f"❌ Execution failed: {result.get('error', 'unknown')}"
        inner = result.get("result", "")
        if isinstance(inner, str):
            return f"✅ Commands executed:\n{inner}"
        return f"✅ Done: {json.dumps(result, indent=2)}"

    elif name == "ue_set_config":
        api_key = args.get("api_key", "")
        model = args.get("model", "")
        result = _ue_config(api_key=api_key, model=model)
        if result.get("error"):
            return f"❌ Config error: {result['error']}"
        out = "✅ Config updated."
        if model:
            out += f"\nModel: {model}"
        if api_key:
            masked = api_key[:8] + "..." + api_key[-4:]
            out += f"\nAPI key: {masked}"
        return out

    elif name == "ue_get_config":
        result = _ue_config()
        if result.get("error"):
            return f"❌ {result['error']}"
        lines = ["**Current UE Plugin Config:**"]
        lines.append(f"API key set: {'✅ Yes' if result.get('api_key_set') else '❌ No (set with ue_set_config)'}")
        if result.get("api_key_masked"):
            lines.append(f"API key: {result['api_key_masked']}")
        lines.append(f"Model: {result.get('model', 'not set')}")
        return "\n".join(lines)

    elif name == "ue_list_models":
        lines = ["**Available models for Blueprint generation:**\n"]
        for m in MODELS:
            lines.append(f"• `{m['id']}` — {m['name']}")
        lines.append("\nUse the model ID with ue_set_config or ue_build_blueprint.")
        return "\n".join(lines)

    elif name == "ue_clear_history":
        payload = json.dumps({}).encode()
        req = urllib.request.Request(
            f"{UE_BASE}/history/clear",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                json.loads(r.read())
            return "✅ Conversation history cleared."
        except Exception as e:
            return f"❌ {e}"

    else:
        return f"❌ Unknown tool: {name}"


# ── MCP message loop ──────────────────────────────────────────────────────────

def main():
    while True:
        msg = _read()
        if msg is None:
            break

        method = msg.get("method", "")
        msg_id = msg.get("id")

        # Initialize
        if method == "initialize":
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "unreal-blueprint-mcp",
                        "version": "3.0.0"
                    }
                }
            })

        # List tools
        elif method == "tools/list":
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS}
            })

        # Call tool
        elif method == "tools/call":
            params = msg.get("params", {})
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            try:
                result_text = handle_tool(tool_name, tool_args)
            except Exception as e:
                result_text = f"❌ Tool error: {e}"
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}]
                }
            })

        # Notifications (no response needed)
        elif method.startswith("notifications/"):
            pass

        # Unknown
        elif msg_id is not None:
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            })


if __name__ == "__main__":
    main()
