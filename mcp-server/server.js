/**
 * Unreal Assistant — MCP Server
 * Bridges AI-generated Blueprint JSON commands to Unreal Engine plugin
 * 
 * Endpoints:
 *   POST /api/blueprint/execute   — Execute commands in Unreal Engine
 *   POST /api/blueprint/generate  — Generate Blueprint JSON from prompt (AI)
 *   GET  /api/health              — Health check
 */

import express from "express";
import bodyParser from "body-parser";
import cors from "cors";
import dotenv from "dotenv";
import blueprintRoutes from "./routes/blueprint.js";

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(bodyParser.json({ limit: "10mb" }));

// Routes
app.use("/api/blueprint", blueprintRoutes);

// Health check
app.get("/api/health", (req, res) => {
  res.json({
    status: "ok",
    server: "Unreal Assistant MCP Server",
    version: "1.0.0",
    unreal_host: process.env.UNREAL_HOST || "http://localhost:8080",
    ai_configured: !!process.env.OPENAI_API_KEY,
    timestamp: new Date().toISOString(),
  });
});

// 404
app.use((req, res) => {
  res.status(404).json({ error: "Route not found" });
});

// Error handler
app.use((err, req, res, next) => {
  console.error("[MCP] Error:", err.message);
  res.status(500).json({ error: err.message });
});

app.listen(PORT, () => {
  console.log(`\n⚡ Unreal Assistant MCP Server`);
  console.log(`   Running on  → http://localhost:${PORT}`);
  console.log(`   Unreal host → ${process.env.UNREAL_HOST || "http://localhost:8080"}`);
  console.log(`   AI ready    → ${process.env.OPENAI_API_KEY ? "✓ OpenAI configured" : "✗ Set OPENAI_API_KEY"}`);
  console.log(`\n   POST /api/blueprint/execute  — Execute commands in Unreal`);
  console.log(`   POST /api/blueprint/generate  — Generate Blueprint from prompt\n`);
});
