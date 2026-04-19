/**
 * Unreal Engine Client
 * Sends Blueprint commands to the MCPBlueprint plugin running inside Unreal Engine.
 * 
 * The plugin must be running with its HTTP server active on UNREAL_HOST:8080
 */

import axios from "axios";

const UNREAL_HOST = process.env.UNREAL_HOST || "http://localhost:8080";
const TIMEOUT_MS = 30000; // 30 seconds

/**
 * Send an array of Blueprint commands to Unreal Engine.
 * @param {Array} commands - Array of Blueprint command objects
 * @returns {Promise<object>} - Unreal Engine response
 */
export async function sendToUnreal(commands) {
  try {
    const response = await axios.post(
      `${UNREAL_HOST}/unreal/execute`,
      { commands },
      {
        timeout: TIMEOUT_MS,
        headers: {
          "Content-Type": "application/json",
          "X-MCP-Client": "unreal-assistant/1.0",
        },
      }
    );
    return response.data;
  } catch (err) {
    if (err.code === "ECONNREFUSED") {
      throw new Error(
        `Cannot connect to Unreal Engine at ${UNREAL_HOST}. ` +
        `Make sure UE5 is running with the MCPBlueprint plugin enabled and PIE is active.`
      );
    }
    if (err.response) {
      const msg = err.response.data?.error || err.response.statusText;
      throw new Error(`Unreal Engine error (${err.response.status}): ${msg}`);
    }
    throw new Error(`Network error: ${err.message}`);
  }
}

/**
 * Check if Unreal Engine is reachable.
 * @returns {Promise<boolean>}
 */
export async function pingUnreal() {
  try {
    await axios.get(`${UNREAL_HOST}/unreal/status`, { timeout: 3000 });
    return true;
  } catch {
    return false;
  }
}
