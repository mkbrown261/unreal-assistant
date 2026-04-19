/**
 * Blueprint Routes
 * /api/blueprint/execute  — Send commands to Unreal Engine
 * /api/blueprint/generate — AI: text → Blueprint JSON
 */

import express from "express";
import { sendToUnreal } from "../services/unrealClient.js";
import { generateBlueprint } from "../services/aiClient.js";

const router = express.Router();

/**
 * POST /api/blueprint/execute
 * Body: { commands: [...] }
 * 
 * Sends a validated array of Blueprint commands to the Unreal Engine plugin.
 */
router.post("/execute", async (req, res) => {
  const { commands } = req.body;

  if (!commands || !Array.isArray(commands)) {
    return res.status(400).json({ error: "commands must be an array" });
  }
  if (commands.length === 0) {
    return res.status(400).json({ error: "commands array is empty" });
  }

  // Validate each command has an 'action' field
  const invalid = commands.find((c) => !c.action || typeof c.action !== "string");
  if (invalid) {
    return res.status(400).json({ error: "Each command must have an 'action' field" });
  }

  console.log(`[execute] Running ${commands.length} Blueprint commands`);

  try {
    const result = await sendToUnreal(commands);
    res.json({
      success: true,
      commands_executed: commands.length,
      result,
    });
  } catch (err) {
    console.error("[execute] Error:", err.message);
    res.status(500).json({
      success: false,
      error: err.message,
      hint: "Make sure Unreal Engine is running with the MCPBlueprint plugin enabled",
    });
  }
});

/**
 * POST /api/blueprint/generate
 * Body: { prompt: string }
 * 
 * Converts a plain English description into Blueprint commands using AI,
 * then optionally executes them in Unreal Engine.
 */
router.post("/generate", async (req, res) => {
  const { prompt, execute = false } = req.body;

  if (!prompt || typeof prompt !== "string" || !prompt.trim()) {
    return res.status(400).json({ error: "prompt is required" });
  }

  console.log(`[generate] Prompt: "${prompt.slice(0, 80)}..."`);

  try {
    // Step 1: Generate Blueprint JSON from AI
    const commands = await generateBlueprint(prompt.trim());
    console.log(`[generate] Generated ${commands.length} commands`);

    // Step 2: Optionally execute in Unreal
    let unrealResult = null;
    if (execute) {
      console.log("[generate] Executing in Unreal Engine...");
      unrealResult = await sendToUnreal(commands);
    }

    res.json({
      success: true,
      commands,
      commands_count: commands.length,
      unreal_executed: execute,
      unreal_result: unrealResult,
    });
  } catch (err) {
    console.error("[generate] Error:", err.message);
    res.status(500).json({
      success: false,
      error: err.message,
    });
  }
});

export default router;
