/**
 * AI Client — Blueprint Generation via OpenAI
 * Converts plain English descriptions into structured Blueprint command arrays.
 */

import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

const SYSTEM_PROMPT = `You are an Unreal Engine Blueprint Generation System.

Your job is to convert user intent into structured executable commands for Unreal Engine via MCP.

You DO NOT explain. You DO NOT give tutorials. You ONLY output structured JSON.

AVAILABLE COMMANDS:
- create_blueprint: { action, name, parent_class }
- add_variable: { action, blueprint, variable_name, variable_type, default_value }
- add_node: { action, blueprint, node, id, x, y, params?, condition?, variable? }
- connect_nodes: { action, blueprint, from_node, from_pin, to_node, to_pin }
- set_variable: { action, blueprint, variable_name, value }
- compile_blueprint: { action, name }

RULES:
- Always create_blueprint first
- Use BP_<Name> naming convention
- Use valid Unreal node names (Event BeginPlay, Event Tick, Event ActorBeginOverlap, Branch, Sequence, Print String, Cast To, Timeline, Delay, AI Move To, Get Player Pawn, Destroy Actor, etc.)
- Always connect execution flow — no floating nodes
- Always end with compile_blueprint
- Declare all variables with add_variable before using them
- Include x/y positions for clean graph layout (increment x by ~250 per node)

OUTPUT: Return ONLY valid JSON with a "commands" array. No markdown. No explanation.`;

/**
 * Generate Blueprint commands from a plain English prompt.
 * @param {string} prompt
 * @returns {Promise<Array>} commands array
 */
export async function generateBlueprint(prompt) {
  if (!process.env.OPENAI_API_KEY) {
    throw new Error("OPENAI_API_KEY is not configured. Set it in your .env file.");
  }

  const completion = await client.chat.completions.create({
    model: "gpt-4o",
    response_format: { type: "json_object" },
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: prompt },
    ],
    max_tokens: 2500,
    temperature: 0.2,
  });

  const content = completion.choices[0]?.message?.content;
  if (!content) throw new Error("No response from AI");

  let parsed;
  try {
    parsed = JSON.parse(content);
  } catch {
    throw new Error("AI returned invalid JSON");
  }

  const commands = parsed.commands;
  if (!Array.isArray(commands) || commands.length === 0) {
    throw new Error("AI returned empty or invalid commands array");
  }

  return commands;
}
