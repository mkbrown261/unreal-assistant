import { Hono } from 'hono'
import { cors } from 'hono/cors'

const app = new Hono<{ Bindings: { OPENAI_API_KEY?: string } }>()

app.use('/api/*', cors())

// ── Blueprint Execution Translator ────────────────────────────────────────────
// POST /api/translate
// Input:  { commands: [...] }  — raw MCP Blueprint command array
// Output: { translated: [...] } — clean, fully explicit Blueprint Manager JSON
//         ready to POST directly to POST /unreal/execute inside Unreal Engine
//
// Rules:
//   - Normalize node names to canonical Unreal names
//   - Ensure every node has a unique numeric id
//   - Explicit action / blueprint_name / node_type / parameters / connections fields
//   - Preserve execution order
//   - compile_blueprint always last

app.post('/api/translate', async (c) => {
  let body: { commands?: any[] }
  try { body = await c.req.json() } catch { return c.json({ error: 'Invalid JSON body' }, 400) }

  const raw = body.commands
  if (!Array.isArray(raw) || raw.length === 0)
    return c.json({ error: "'commands' must be a non-empty array" }, 400)

  // ── Node name normalisation map ─────────────────────────────────────────────
  const NODE_NAMES: Record<string, string> = {
    'beginplay':               'Event BeginPlay',
    'event beginplay':         'Event BeginPlay',
    'receivebeginplay':        'Event BeginPlay',
    'tick':                    'Event Tick',
    'event tick':              'Event Tick',
    'receivetick':             'Event Tick',
    'actorendoverlap':         'Event ActorEndOverlap',
    'event actorendoverlap':   'Event ActorEndOverlap',
    'actorbeginoverlap':       'Event ActorBeginOverlap',
    'event actorbeginoverlap': 'Event ActorBeginOverlap',
    'branch':                  'Branch',
    'ifthenelse':              'Branch',
    'sequence':                'Sequence',
    'delay':                   'Delay',
    'timeline':                'Timeline',
    'print string':            'Print String',
    'printstring':             'Print String',
    'cast to character':       'Cast To Character',
    'casttocharacter':         'Cast To Character',
    'get player pawn':         'Get Player Pawn',
    'getplayerpawn':           'Get Player Pawn',
    'get distance to':         'Get Distance To',
    'getdistanceto':           'Get Distance To',
    'ai move to':              'AI Move To',
    'aimoveto':                'AI Move To',
    'simple move to actor':    'Simple Move To Actor',
    'destroy actor':           'Destroy Actor',
    'destroyactor':            'Destroy Actor',
    'play sound at location':  'Play Sound at Location',
    'spawn emitter at location':'Spawn Emitter at Location',
    'set':                     'Set Variable',
    'get':                     'Get Variable',
    'set variable':            'Set Variable',
    'get variable':            'Get Variable',
    'call function':           'Call Function',
  }

  function normalizeNodeName(raw: string): string {
    const key = raw.toLowerCase().trim()
    // handle "Call Function: XYZ" prefix
    if (key.startsWith('call function:')) return raw // keep original with function name
    return NODE_NAMES[key] || raw
  }

  // ── Pin name normalisation ──────────────────────────────────────────────────
  const PIN_NAMES: Record<string, string> = {
    'then': 'Then', 'exec': 'Execute', 'execute': 'Execute',
    'true': 'True', 'false': 'False',
    'pressed': 'Pressed', 'released': 'Released',
    'play': 'Play', 'stop': 'Stop', 'reverse': 'Reverse',
    'completed': 'Completed', 'update': 'Update',
  }
  function normalizePin(p: string): string {
    return PIN_NAMES[p?.toLowerCase()] || p || 'Execute'
  }

  // ── ID tracker ─────────────────────────────────────────────────────────────
  //  MCP commands use string ids like "node_0". We keep them as-is but guarantee
  //  every add_node gets one; generate one if missing.
  let autoId = 0
  const usedIds = new Set<string>()

  function ensureId(cmd: any): string {
    if (cmd.id && !usedIds.has(cmd.id)) { usedIds.add(cmd.id); return cmd.id }
    let id: string
    do { id = `node_${autoId++}` } while (usedIds.has(id))
    usedIds.add(id)
    return id
  }

  // ── Translate each command ─────────────────────────────────────────────────
  const translated: any[] = []
  const compileCommands: any[] = []  // collect compiles, always push to end

  for (const cmd of raw) {
    if (!cmd.action) continue
    const action: string = cmd.action

    switch (action) {

      case 'create_blueprint': {
        translated.push({
          action: 'create_blueprint',
          blueprint_name: cmd.name || cmd.blueprint || 'BP_Unnamed',
          parameters: {
            parent_class: cmd.parent_class || 'Actor',
          },
        })
        break
      }

      case 'add_variable': {
        translated.push({
          action: 'add_variable',
          blueprint_name: cmd.blueprint || cmd.name,
          parameters: {
            variable_name: cmd.variable_name,
            variable_type: cmd.variable_type || 'Boolean',
            default_value: cmd.default_value ?? null,
          },
        })
        break
      }

      case 'add_node': {
        const nodeId = ensureId(cmd)
        const nodeType = normalizeNodeName(cmd.node || '')

        // Build explicit parameters object
        const params: Record<string, any> = { ...(cmd.params || {}) }
        if (cmd.condition !== undefined) params.condition = cmd.condition
        if (cmd.variable !== undefined) params.variable = cmd.variable
        if (cmd.value !== undefined) params.value = cmd.value

        translated.push({
          action: 'add_node',
          blueprint_name: cmd.blueprint,
          node_type: nodeType,
          node_id: nodeId,
          parameters: {
            position: { x: cmd.x ?? 0, y: cmd.y ?? 0 },
            ...params,
          },
        })
        break
      }

      case 'connect_nodes': {
        translated.push({
          action: 'connect_nodes',
          blueprint_name: cmd.blueprint,
          connections: {
            source: {
              node_id: cmd.from_node,
              pin: normalizePin(cmd.from_pin),
            },
            target: {
              node_id: cmd.to_node,
              pin: normalizePin(cmd.to_pin),
            },
          },
        })
        break
      }

      case 'set_variable': {
        translated.push({
          action: 'set_variable',
          blueprint_name: cmd.blueprint || cmd.name,
          parameters: {
            variable_name: cmd.variable_name,
            value: cmd.value ?? cmd.default_value ?? null,
          },
        })
        break
      }

      case 'compile_blueprint': {
        // Deferred — always goes last
        compileCommands.push({
          action: 'compile_blueprint',
          blueprint_name: cmd.name || cmd.blueprint,
          parameters: {},
        })
        break
      }

      default: {
        // Pass unknown commands through unchanged with action field
        translated.push({ action, blueprint_name: cmd.blueprint || cmd.name, parameters: cmd })
      }
    }
  }

  // Compile always last
  translated.push(...compileCommands)

  return c.json({
    translated,
    meta: {
      input_count: raw.length,
      output_count: translated.length,
      timestamp: new Date().toISOString(),
    },
  })
})

// ── Blueprint generation API (AI → MCP JSON) ──────────────────────────────────
const SYSTEM_PROMPT = `You are an Unreal Engine Blueprint Generation System.
Convert user intent into structured JSON commands for the MCP Blueprint server.
DO NOT explain. DO NOT give tutorials. Output ONLY valid JSON.

COMMANDS: create_blueprint | add_node | connect_nodes | set_variable | add_variable | compile_blueprint

RULES:
- create_blueprint first, compile_blueprint last
- Node names: Event BeginPlay, Event Tick, Event ActorBeginOverlap, Event ActorEndOverlap, Branch, Sequence, Delay, Timeline, Print String, Cast To Character, Get Player Pawn, Get Distance To, AI Move To, Destroy Actor, Play Sound at Location, Spawn Emitter at Location, Set, Get
- Connect all execution flow — no floating nodes
- Declare variables with add_variable before using them
- Use BP_<Name> naming. Include x/y positions (+250x per step).

OUTPUT FORMAT (JSON only, no markdown):
{"commands":[{"action":"create_blueprint","name":"BP_X","parent_class":"Actor"},{"action":"add_node","blueprint":"BP_X","node":"Event BeginPlay","id":"node_0","x":0,"y":0},{"action":"compile_blueprint","name":"BP_X"}]}`

app.post('/api/generate', async (c) => {
  let body: { prompt?: string }
  try { body = await c.req.json() } catch { return c.json({ error: 'Invalid JSON body' }, 400) }
  if (!body.prompt?.trim()) return c.json({ error: 'prompt is required' }, 400)

  const apiKey = c.env.OPENAI_API_KEY
  if (!apiKey) return c.json(getDemoResponse(body.prompt))

  try {
    const res = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${apiKey}` },
      body: JSON.stringify({
        model: 'gpt-4o',
        response_format: { type: 'json_object' },
        messages: [
          { role: 'system', content: SYSTEM_PROMPT },
          { role: 'user', content: body.prompt.trim() },
        ],
        max_tokens: 2500,
        temperature: 0.2,
      }),
    })
    if (!res.ok) return c.json({ error: `OpenAI error: ${res.status}` }, 502)
    const data = await res.json() as any
    const content = data.choices?.[0]?.message?.content
    if (!content) return c.json({ error: 'No content from AI' }, 502)
    return c.json(JSON.parse(content))
  } catch (e: any) {
    return c.json({ error: e.message || 'Generation failed' }, 500)
  }
})

// ── Demo response ─────────────────────────────────────────────────────────────
function getDemoResponse(prompt: string) {
  const l = prompt.toLowerCase()
  if (l.includes('enemy') || l.includes('chase') || l.includes('ai')) return { commands: [
    { action:'create_blueprint', name:'BP_EnemyAI', parent_class:'Character' },
    { action:'add_variable', blueprint:'BP_EnemyAI', variable_name:'DetectionRadius', variable_type:'Float', default_value:500.0 },
    { action:'add_variable', blueprint:'BP_EnemyAI', variable_name:'bIsChasing', variable_type:'Boolean', default_value:false },
    { action:'add_node', blueprint:'BP_EnemyAI', node:'Event BeginPlay', id:'node_0', x:0, y:0 },
    { action:'add_node', blueprint:'BP_EnemyAI', node:'Print String', id:'node_1', x:250, y:0, params:{ InString:'Enemy AI Ready' } },
    { action:'add_node', blueprint:'BP_EnemyAI', node:'Event Tick', id:'node_2', x:0, y:300 },
    { action:'add_node', blueprint:'BP_EnemyAI', node:'Get Player Pawn', id:'node_3', x:200, y:400 },
    { action:'add_node', blueprint:'BP_EnemyAI', node:'Get Distance To', id:'node_4', x:450, y:350 },
    { action:'add_node', blueprint:'BP_EnemyAI', node:'Branch', id:'node_5', x:700, y:300, condition:'Distance <= DetectionRadius' },
    { action:'add_node', blueprint:'BP_EnemyAI', node:'AI Move To', id:'node_6', x:950, y:200, params:{ GoalActor:'PlayerPawn' } },
    { action:'connect_nodes', blueprint:'BP_EnemyAI', from_node:'node_0', from_pin:'Then', to_node:'node_1', to_pin:'Execute' },
    { action:'connect_nodes', blueprint:'BP_EnemyAI', from_node:'node_2', from_pin:'Then', to_node:'node_5', to_pin:'Execute' },
    { action:'connect_nodes', blueprint:'BP_EnemyAI', from_node:'node_5', from_pin:'True', to_node:'node_6', to_pin:'Execute' },
    { action:'compile_blueprint', name:'BP_EnemyAI' },
  ]}
  if (l.includes('door')) return { commands: [
    { action:'create_blueprint', name:'BP_InteractiveDoor', parent_class:'Actor' },
    { action:'add_variable', blueprint:'BP_InteractiveDoor', variable_name:'bIsOpen', variable_type:'Boolean', default_value:false },
    { action:'add_variable', blueprint:'BP_InteractiveDoor', variable_name:'OpenAngle', variable_type:'Float', default_value:90.0 },
    { action:'add_node', blueprint:'BP_InteractiveDoor', node:'Event ActorBeginOverlap', id:'node_0', x:0, y:0 },
    { action:'add_node', blueprint:'BP_InteractiveDoor', node:'Branch', id:'node_1', x:280, y:0, condition:'NOT bIsOpen' },
    { action:'add_node', blueprint:'BP_InteractiveDoor', node:'Timeline', id:'node_2', x:520, y:0, params:{ name:'DoorOpen', length:1.0 } },
    { action:'connect_nodes', blueprint:'BP_InteractiveDoor', from_node:'node_0', from_pin:'Then', to_node:'node_1', to_pin:'Execute' },
    { action:'connect_nodes', blueprint:'BP_InteractiveDoor', from_node:'node_1', from_pin:'True', to_node:'node_2', to_pin:'Play' },
    { action:'compile_blueprint', name:'BP_InteractiveDoor' },
  ]}
  if (l.includes('health') || l.includes('pickup')) return { commands: [
    { action:'create_blueprint', name:'BP_HealthPickup', parent_class:'Actor' },
    { action:'add_variable', blueprint:'BP_HealthPickup', variable_name:'HealAmount', variable_type:'Float', default_value:25.0 },
    { action:'add_variable', blueprint:'BP_HealthPickup', variable_name:'bPickedUp', variable_type:'Boolean', default_value:false },
    { action:'add_node', blueprint:'BP_HealthPickup', node:'Event ActorBeginOverlap', id:'node_0', x:0, y:0 },
    { action:'add_node', blueprint:'BP_HealthPickup', node:'Branch', id:'node_1', x:280, y:0, condition:'NOT bPickedUp' },
    { action:'add_node', blueprint:'BP_HealthPickup', node:'Cast To Character', id:'node_2', x:520, y:0 },
    { action:'add_node', blueprint:'BP_HealthPickup', node:'Destroy Actor', id:'node_3', x:780, y:0 },
    { action:'connect_nodes', blueprint:'BP_HealthPickup', from_node:'node_0', from_pin:'Then', to_node:'node_1', to_pin:'Execute' },
    { action:'connect_nodes', blueprint:'BP_HealthPickup', from_node:'node_1', from_pin:'True', to_node:'node_2', to_pin:'Execute' },
    { action:'connect_nodes', blueprint:'BP_HealthPickup', from_node:'node_2', from_pin:'Then', to_node:'node_3', to_pin:'Execute' },
    { action:'compile_blueprint', name:'BP_HealthPickup' },
  ]}
  return { commands: [
    { action:'create_blueprint', name:'BP_CustomActor', parent_class:'Actor' },
    { action:'add_variable', blueprint:'BP_CustomActor', variable_name:'bIsActive', variable_type:'Boolean', default_value:true },
    { action:'add_node', blueprint:'BP_CustomActor', node:'Event BeginPlay', id:'node_0', x:0, y:0 },
    { action:'add_node', blueprint:'BP_CustomActor', node:'Branch', id:'node_1', x:280, y:0, condition:'bIsActive' },
    { action:'add_node', blueprint:'BP_CustomActor', node:'Print String', id:'node_2', x:520, y:0, params:{ InString:'Actor is Active' } },
    { action:'connect_nodes', blueprint:'BP_CustomActor', from_node:'node_0', from_pin:'Then', to_node:'node_1', to_pin:'Execute' },
    { action:'connect_nodes', blueprint:'BP_CustomActor', from_node:'node_1', from_pin:'True', to_node:'node_2', to_pin:'Execute' },
    { action:'compile_blueprint', name:'BP_CustomActor' },
  ]}
}

// ── Landing page ──────────────────────────────────────────────────────────────
app.get('/', (c) => c.html(`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Unreal Assistant — AI Blueprint MCP Plugin</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet"/>
<style>
:root{
  --bg:#0a0a0f;--bg2:#0f0f1a;--panel:#12121f;
  --border:rgba(138,43,226,.18);--border2:rgba(138,43,226,.4);
  --purple:#8a2be2;--purple2:#a855f7;--purple3:#c084fc;
  --cyan:#00d4ff;--green:#10b981;--orange:#f59e0b;--red:#ef4444;
  --text:#e2e8f0;--text2:#94a3b8;--text3:#64748b;
  --glow:0 0 40px rgba(138,43,226,.25);
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;z-index:0;pointer-events:none;
  background-image:linear-gradient(rgba(138,43,226,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(138,43,226,.04) 1px,transparent 1px);
  background-size:40px 40px}

/* NAV */
nav{position:fixed;top:0;left:0;right:0;z-index:100;display:flex;align-items:center;justify-content:space-between;
  padding:0 40px;height:64px;background:rgba(10,10,15,.9);backdrop-filter:blur(20px);border-bottom:1px solid var(--border)}
.logo{display:flex;align-items:center;gap:10px;font-weight:800;font-size:17px;color:#fff;text-decoration:none}
.logo-icon{width:34px;height:34px;background:linear-gradient(135deg,var(--purple),var(--purple2));
  border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:17px;box-shadow:0 0 20px rgba(138,43,226,.5)}
.nav-links{display:flex;align-items:center;gap:6px}
.nav-link{padding:7px 14px;border-radius:8px;font-size:13px;font-weight:500;color:var(--text2);
  text-decoration:none;transition:.2s;cursor:pointer;background:none;border:none}
.nav-link:hover{color:#fff;background:rgba(255,255,255,.06)}
.dl-btn{padding:8px 20px;border-radius:9px;background:linear-gradient(135deg,var(--purple),var(--purple2));
  color:#fff;font-size:13px;font-weight:700;border:none;cursor:pointer;
  box-shadow:0 0 20px rgba(138,43,226,.35);transition:.2s;text-decoration:none;display:flex;align-items:center;gap:6px}
.dl-btn:hover{transform:translateY(-1px);box-shadow:0 0 30px rgba(168,85,247,.5)}

/* HERO */
.hero{position:relative;z-index:1;min-height:100vh;display:flex;flex-direction:column;
  align-items:center;justify-content:center;text-align:center;padding:100px 24px 60px}
.badge{display:inline-flex;align-items:center;gap:8px;padding:6px 16px;border-radius:99px;
  background:rgba(138,43,226,.12);border:1px solid var(--border2);font-size:12px;font-weight:600;
  color:var(--purple3);margin-bottom:28px;letter-spacing:.04em}
.badge-dot{width:6px;height:6px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.5)}}
h1.hero-title{font-size:clamp(40px,7vw,84px);font-weight:900;line-height:1.05;
  letter-spacing:-.03em;margin-bottom:24px;
  background:linear-gradient(135deg,#fff 0%,var(--purple3) 50%,var(--cyan) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.hero-sub{font-size:clamp(15px,2.2vw,20px);color:var(--text2);max-width:620px;line-height:1.7;margin-bottom:44px}
.hero-actions{display:flex;gap:14px;flex-wrap:wrap;justify-content:center;margin-bottom:48px}
.btn-primary{padding:14px 36px;border-radius:12px;background:linear-gradient(135deg,var(--purple),var(--purple2));
  color:#fff;font-size:15px;font-weight:700;border:none;cursor:pointer;
  box-shadow:0 0 30px rgba(138,43,226,.4);transition:.25s;text-decoration:none;display:inline-flex;align-items:center;gap:8px}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 0 50px rgba(168,85,247,.55)}
.btn-ghost{padding:14px 32px;border-radius:12px;background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.12);color:var(--text);font-size:15px;font-weight:600;
  cursor:pointer;transition:.25s;text-decoration:none;display:inline-flex;align-items:center;gap:8px}
.btn-ghost:hover{background:rgba(255,255,255,.09);transform:translateY(-2px)}

/* STATS BAR */
.stats{display:flex;gap:48px;justify-content:center;flex-wrap:wrap;margin-bottom:60px;position:relative;z-index:1}
.stat{text-align:center}
.stat-num{font-size:28px;font-weight:900;background:linear-gradient(135deg,var(--purple2),var(--cyan));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.stat-label{font-size:12px;color:var(--text3);font-weight:500;margin-top:2px}

/* SECTIONS */
section{position:relative;z-index:1;padding:90px 24px}
.container{max-width:1100px;margin:0 auto}
.section-label{font-size:11px;font-weight:700;letter-spacing:.12em;color:var(--purple2);text-transform:uppercase;margin-bottom:12px}
.section-title{font-size:clamp(26px,4.5vw,44px);font-weight:900;line-height:1.1;letter-spacing:-.02em;margin-bottom:16px}
.section-sub{font-size:16px;color:var(--text2);line-height:1.7;max-width:540px}
.alt-bg{background:var(--bg2)}

/* ARCHITECTURE FLOW */
.arch-flow{display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:0;margin-top:56px}
.arch-node{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:22px 26px;
  text-align:center;min-width:145px;transition:.3s}
.arch-node:hover{border-color:var(--border2);box-shadow:var(--glow);transform:translateY(-3px)}
.arch-icon{font-size:26px;margin-bottom:8px}
.arch-label{font-size:13px;font-weight:700;color:var(--text);margin-bottom:3px}
.arch-sub{font-size:11px;color:var(--text3)}
.arch-arrow{padding:0 6px;color:var(--purple3);font-size:20px}

/* FEATURE GRID */
.feat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;margin-top:56px}
.feat{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:28px;transition:.3s}
.feat:hover{border-color:var(--border2);box-shadow:var(--glow);transform:translateY(-3px)}
.feat-icon{font-size:26px;margin-bottom:14px}
.feat h3{font-size:16px;font-weight:700;margin-bottom:8px}
.feat p{font-size:13px;color:var(--text2);line-height:1.65}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.tag{font-size:10px;font-weight:700;padding:3px 10px;border-radius:99px;letter-spacing:.05em;
  background:rgba(138,43,226,.1);color:var(--purple3);border:1px solid rgba(138,43,226,.2)}

/* INSTALL STEPS */
.steps{display:flex;flex-direction:column;gap:16px;margin-top:52px}
.step{display:flex;gap:20px;align-items:flex-start;background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:22px}
.step-num{width:36px;height:36px;border-radius:10px;flex-shrink:0;
  background:linear-gradient(135deg,var(--purple),var(--purple2));
  display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:800;color:#fff;
  box-shadow:0 0 16px rgba(138,43,226,.4)}
.step h3{font-size:15px;font-weight:700;margin-bottom:6px}
.step p{font-size:13px;color:var(--text2);line-height:1.6;margin-bottom:10px}
.code{background:rgba(0,0,0,.5);border:1px solid rgba(255,255,255,.07);border-radius:8px;
  padding:12px 16px;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--cyan);
  overflow-x:auto;white-space:pre;line-height:1.7}

/* TRANSLATOR DEMO */
.translator-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:52px}
@media(max-width:860px){.translator-grid{grid-template-columns:1fr}}
.t-panel{background:var(--panel);border:1px solid var(--border);border-radius:14px;overflow:hidden;display:flex;flex-direction:column}
.t-header{display:flex;align-items:center;justify-content:space-between;padding:12px 18px;
  background:rgba(255,255,255,.025);border-bottom:1px solid var(--border)}
.t-label{font-size:11px;font-weight:700;letter-spacing:.1em;color:var(--text3);text-transform:uppercase}
.t-badge{font-size:10px;font-weight:700;padding:3px 10px;border-radius:99px;letter-spacing:.05em}
.badge-mcp{background:rgba(138,43,226,.15);color:var(--purple3)}
.badge-exec{background:rgba(0,212,255,.1);color:var(--cyan)}
.t-body{padding:16px;font-family:'JetBrains Mono',monospace;font-size:12px;line-height:1.8;
  min-height:280px;max-height:420px;overflow-y:auto;white-space:pre-wrap;color:var(--text2);flex:1}
.t-body.placeholder{color:var(--text3);font-style:italic;font-family:'Inter',sans-serif;font-size:13px}
.t-footer{padding:12px 18px;border-top:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;gap:10px}
.trans-btn{flex:1;padding:10px;border-radius:9px;
  background:linear-gradient(135deg,var(--cyan2,#06b6d4),var(--cyan));
  color:#000;font-size:13px;font-weight:700;border:none;cursor:pointer;
  box-shadow:0 0 20px rgba(0,212,255,.25);transition:.2s;display:flex;align-items:center;justify-content:center;gap:6px}
.trans-btn:hover{transform:translateY(-1px);box-shadow:0 0 30px rgba(0,212,255,.45)}
.trans-btn:disabled{opacity:.5;cursor:not-allowed;transform:none}
.copy-btn{padding:7px 14px;border-radius:7px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);
  color:var(--text2);font-size:11px;cursor:pointer;font-weight:600;transition:.2s;display:none}
.copy-btn:hover{background:rgba(255,255,255,.1)}

/* DOWNLOAD CARD */
.dl-card{background:var(--panel);border:1px solid var(--border2);border-radius:18px;padding:40px;
  text-align:center;position:relative;overflow:hidden;margin-top:52px}
.dl-card::before{content:'';position:absolute;inset:0;
  background:radial-gradient(ellipse at 50% 0%, rgba(138,43,226,.12) 0%, transparent 65%);pointer-events:none}
.dl-card h3{font-size:26px;font-weight:900;margin-bottom:10px}
.dl-card p{font-size:15px;color:var(--text2);margin-bottom:28px;max-width:500px;margin-left:auto;margin-right:auto}
.dl-links{display:flex;gap:14px;justify-content:center;flex-wrap:wrap}

/* FOOTER */
footer{border-top:1px solid var(--border);padding:32px 40px;
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:14px;position:relative;z-index:1}
.footer-logo{font-weight:800;font-size:14px;color:var(--text2)}
.footer-links{display:flex;gap:20px}
.footer-link{font-size:13px;color:var(--text3);text-decoration:none;transition:.2s}
.footer-link:hover{color:var(--text2)}
.footer-copy{font-size:11px;color:var(--text3)}

/* JSON syntax */
.jk{color:#c084fc}.js{color:#00d4ff}.jn{color:#f59e0b}.jb{color:#94a3b8}.ja{color:#10b981}

/* Spinner */
@keyframes spin{to{transform:rotate(360deg)}}
.spin{width:14px;height:14px;border-radius:50%;border:2px solid rgba(0,0,0,.2);border-top-color:#000;animation:spin .7s linear infinite}

/* Toast */
.toast{position:fixed;bottom:24px;right:24px;z-index:999;padding:11px 18px;border-radius:9px;
  font-size:13px;font-weight:600;backdrop-filter:blur(12px);border:1px solid;pointer-events:none;
  animation:slideIn .3s ease}
@keyframes slideIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.toast-ok{background:rgba(16,185,129,.15);border-color:rgba(16,185,129,.3);color:#6ee7b7}
.toast-err{background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.25);color:#fca5a5}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(138,43,226,.3);border-radius:99px}
</style>
</head>
<body>

<!-- NAV -->
<nav>
  <a href="#" class="logo"><div class="logo-icon">⚡</div>Unreal Assistant</a>
  <div class="nav-links">
    <button class="nav-link" onclick="go('how')">How It Works</button>
    <button class="nav-link" onclick="go('install')">Install</button>
    <button class="nav-link" onclick="go('translator')">Translator</button>
    <button class="nav-link" onclick="go('plugin')">Plugin Docs</button>
    <a href="https://github.com/mkbrown261/unreal-assistant/releases" target="_blank" class="dl-btn">⬇ Download Plugin</a>
  </div>
</nav>

<!-- HERO -->
<section class="hero">
  <div class="badge"><span class="badge-dot"></span>Unreal Engine 5 · AI Blueprint MCP Plugin</div>
  <h1 class="hero-title">AI Blueprints,<br/>Inside Unreal Engine</h1>
  <p class="hero-sub">
    Describe game logic in plain English. The MCP plugin runs <strong>inside your Unreal project</strong>,
    receives AI-generated Blueprint commands, and creates fully wired, compiled Blueprints — automatically.
  </p>
  <div class="hero-actions">
    <a href="https://github.com/mkbrown261/unreal-assistant/releases" target="_blank" class="btn-primary">⬇ Download Plugin (.uplugin)</a>
    <a href="https://github.com/mkbrown261/unreal-assistant" target="_blank" class="btn-ghost">⭐ GitHub Source</a>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-num">6</div><div class="stat-label">Blueprint Commands</div></div>
    <div class="stat"><div class="stat-num">:8080</div><div class="stat-label">Unreal HTTP Server</div></div>
    <div class="stat"><div class="stat-num">UE5</div><div class="stat-label">Compatible</div></div>
    <div class="stat"><div class="stat-num">C++</div><div class="stat-label">Native Plugin</div></div>
  </div>
</section>

<!-- HOW IT WORKS -->
<section id="how" class="alt-bg">
  <div class="container">
    <div class="section-label">Architecture</div>
    <h2 class="section-title">How It All Connects</h2>
    <p class="section-sub">The plugin runs an HTTP server <em>inside</em> Unreal. The MCP Node.js server is your bridge from AI to engine.</p>
    <div class="arch-flow">
      <div class="arch-node">
        <div class="arch-icon">💬</div>
        <div class="arch-label">Your Prompt</div>
        <div class="arch-sub">Plain English</div>
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-node" style="border-color:rgba(168,85,247,.4)">
        <div class="arch-icon">🧠</div>
        <div class="arch-label">AI (OpenAI)</div>
        <div class="arch-sub">MCP JSON commands</div>
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-node">
        <div class="arch-icon">⚙️</div>
        <div class="arch-label">MCP Server</div>
        <div class="arch-sub">Node.js · :3001</div>
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-node" style="border-color:rgba(0,212,255,.35)">
        <div class="arch-icon">🎮</div>
        <div class="arch-label">UE5 Plugin</div>
        <div class="arch-sub">C++ · :8080</div>
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-node" style="border-color:rgba(16,185,129,.4)">
        <div class="arch-icon">📋</div>
        <div class="arch-label">Blueprint</div>
        <div class="arch-sub">Compiled in-engine</div>
      </div>
    </div>
  </div>
</section>

<!-- FEATURES -->
<section id="features">
  <div class="container">
    <div class="section-label">Plugin Capabilities</div>
    <h2 class="section-title">What the Plugin Does</h2>
    <p class="section-sub">A Python-based Unreal Editor plugin — no compilation needed. Handles every step of Blueprint creation via JSON commands from the MCP server.</p>
    <div class="feat-grid">
      <div class="feat">
        <div class="feat-icon">🌐</div>
        <h3>HTTP Server Inside Unreal</h3>
        <p>Plugin starts a Python <code>http.server</code> on port 8080 in a background thread at editor startup. No compilation, no DLLs — pure Python using Unreal's built-in interpreter.</p>
        <div class="tags"><span class="tag">Python http.server</span><span class="tag">:8080</span><span class="tag">No compilation</span></div>
      </div>
      <div class="feat">
        <div class="feat-icon">📋</div>
        <h3>Blueprint Creation</h3>
        <p>Creates UBlueprint assets under <code>/Game/MCP/</code>, sets parent class (Actor, Character, Pawn, etc.), and registers them in the Asset Registry instantly.</p>
        <div class="tags"><span class="tag">asset_tools.create_asset</span><span class="tag">BlueprintEditorLibrary</span><span class="tag">/Game/MCP/</span></div>
      </div>
      <div class="feat">
        <div class="feat-icon">🔗</div>
        <h3>Node Graph Editing</h3>
        <p>Adds nodes to EventGraph by Unreal name (Event BeginPlay, Branch, Print String, AI Move To, Timeline…), positions them on the graph, and allocates default pins.</p>
        <div class="tags"><span class="tag">add_function_call_node</span><span class="tag">add_timeline_node</span><span class="tag">add_cast_node</span></div>
      </div>
      <div class="feat">
        <div class="feat-icon">📦</div>
        <h3>Variable Management</h3>
        <p>Adds typed member variables (Boolean, Float, Int, String, Vector, Rotator) and sets default values on the CDO via FBlueprintEditorUtils.</p>
        <div class="tags"><span class="tag">add_member_variable</span><span class="tag">Boolean·Float·Vector</span><span class="tag">set_default_value</span></div>
      </div>
      <div class="feat">
        <div class="feat-icon">⚡</div>
        <h3>Auto Compile</h3>
        <p>Calls <code>unreal.BlueprintEditorLibrary.compile_blueprint()</code> after every command. Saves the asset automatically. Errors returned in the JSON response.</p>
        <div class="tags"><span class="tag">compile_blueprint()</span><span class="tag">save_asset()</span><span class="tag">Error feedback</span></div>
      </div>
      <div class="feat">
        <div class="feat-icon">🔄</div>
        <h3>Execution Translator</h3>
        <p>API endpoint (<code>/api/translate</code>) normalises raw MCP JSON into clean Blueprint Manager format — explicit fields, canonical node names, guaranteed unique IDs, compile step last.</p>
        <div class="tags"><span class="tag">POST /api/translate</span><span class="tag">Node normalisation</span><span class="tag">Pin mapping</span></div>
      </div>
    </div>
  </div>
</section>

<!-- INSTALL -->
<section id="install" class="alt-bg">
  <div class="container">
    <div class="section-label">Installation</div>
    <h2 class="section-title">No Compilation Required</h2>
    <p class="section-sub">Pure Python plugin. Drop the folder in, enable it in the Plugin Browser, done. No Visual Studio. No build tools. Works on Windows, Mac, and Linux.</p>

    <!-- Zero compile badge -->
    <div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:32px;margin-bottom:36px;">
      <div style="display:inline-flex;align-items:center;gap:8px;padding:10px 18px;border-radius:99px;background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.3);font-size:13px;font-weight:700;color:var(--green);">✓ No Visual Studio required</div>
      <div style="display:inline-flex;align-items:center;gap:8px;padding:10px 18px;border-radius:99px;background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.3);font-size:13px;font-weight:700;color:var(--green);">✓ No compilation step</div>
      <div style="display:inline-flex;align-items:center;gap:8px;padding:10px 18px;border-radius:99px;background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.3);font-size:13px;font-weight:700;color:var(--green);">✓ Works on Windows · Mac · Linux</div>
      <div style="display:inline-flex;align-items:center;gap:8px;padding:10px 18px;border-radius:99px;background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.3);font-size:13px;font-weight:700;color:var(--green);">✓ Unreal Engine 5.0+</div>
    </div>

    <div class="steps">
      <div class="step">
        <div class="step-num">1</div>
        <div>
          <h3>Drop the Folder into Your Project's Plugins Directory</h3>
          <p>Download the zip from GitHub, extract it, and copy the <code>MCPBlueprint</code> folder into your project. Create a <code>Plugins/</code> folder if one doesn't exist yet.</p>
          <div class="code">YourProject/
└── Plugins/
    └── MCPBlueprint/              ← drop here
        ├── MCPBlueprint.uplugin   ← Unreal reads this to show it in Plugin Browser
        └── Content/
            └── Python/
                ├── init_unreal.py      ← auto-runs on plugin enable
                ├── mcp_server.py       ← HTTP server on :8080
                └── blueprint_executor.py  ← creates/connects/compiles Blueprints</div>
        </div>
      </div>

      <div class="step">
        <div class="step-num">2</div>
        <div>
          <h3>Enable in Plugin Browser → Restart Editor</h3>
          <p>Open Unreal Editor → <strong>Edit → Plugins</strong> → search <strong>"MCP Blueprint"</strong> → it appears under <strong>Developer Tools</strong> → click <strong>Enable</strong> → restart. The HTTP server starts automatically on port 8080.</p>
          <div class="code"># After restarting, check the Output Log for:
[MCPBlueprint] MCP HTTP server ready → POST http://localhost:8080/unreal/execute
[MCPBlueprint] Health check         → GET  http://localhost:8080/unreal/status

# Verify it's running:
curl http://localhost:8080/unreal/status
# → {"status":"ok","server":"MCPBlueprint","version":"1.0.0","mode":"Python Plugin"}</div>
        </div>
      </div>

      <div class="step">
        <div class="step-num">3</div>
        <div>
          <h3>Run the MCP Server and Generate Blueprints</h3>
          <p>Start the Node.js MCP server with your OpenAI key. Send a plain English prompt — it calls the AI, translates the result to Blueprint commands, and POSTs them directly to Unreal.</p>
          <div class="code">cd unreal-assistant/mcp-server
npm install
echo "OPENAI_API_KEY=sk-your-key" > .env
node server.js
# → MCP Server running on http://localhost:3001

# Generate + execute a Blueprint in Unreal in one call:
curl -X POST http://localhost:3001/api/blueprint/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Create an enemy AI that chases the player","execute":true}'
# → Blueprint appears in /Game/MCP/BP_EnemyAI — compiled and ready</div>
        </div>
      </div>
    </div>

    <!-- How it works under the hood -->
    <div style="margin-top:28px;background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:28px;">
      <div style="font-size:13px;font-weight:700;color:var(--purple3);letter-spacing:.06em;text-transform:uppercase;margin-bottom:16px;">How the Python plugin works</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;">
        <div style="background:rgba(138,43,226,.06);border:1px solid rgba(138,43,226,.15);border-radius:10px;padding:16px;">
          <div style="font-size:18px;margin-bottom:8px;">📄</div>
          <div style="font-size:12px;font-weight:700;margin-bottom:4px;">init_unreal.py</div>
          <div style="font-size:11px;color:var(--text3);line-height:1.6;">Unreal auto-executes this file on plugin enable. It calls <code>mcp_server.start()</code>.</div>
        </div>
        <div style="background:rgba(138,43,226,.06);border:1px solid rgba(138,43,226,.15);border-radius:10px;padding:16px;">
          <div style="font-size:18px;margin-bottom:8px;">🌐</div>
          <div style="font-size:12px;font-weight:700;margin-bottom:4px;">mcp_server.py</div>
          <div style="font-size:11px;color:var(--text3);line-height:1.6;">Runs <code>http.server</code> in a background thread on port 8080. Editor stays fully responsive.</div>
        </div>
        <div style="background:rgba(138,43,226,.06);border:1px solid rgba(138,43,226,.15);border-radius:10px;padding:16px;">
          <div style="font-size:18px;margin-bottom:8px;">⚡</div>
          <div style="font-size:12px;font-weight:700;margin-bottom:4px;">blueprint_executor.py</div>
          <div style="font-size:11px;color:var(--text3);line-height:1.6;">Calls <code>unreal.BlueprintEditorLibrary</code> to create assets, add nodes, connect pins, and compile.</div>
        </div>
        <div style="background:rgba(138,43,226,.06);border:1px solid rgba(138,43,226,.15);border-radius:10px;padding:16px;">
          <div style="font-size:18px;margin-bottom:8px;">🔒</div>
          <div style="font-size:12px;font-weight:700;margin-bottom:4px;">Game thread safety</div>
          <div style="font-size:11px;color:var(--text3);line-height:1.6;">Blueprint API calls are dispatched to the game thread via <code>unreal.call_on_game_thread()</code>.</div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- TRANSLATOR DEMO -->
<section id="translator">
  <div class="container">
    <div class="section-label">Blueprint Execution Translator</div>
    <h2 class="section-title">MCP JSON → Executable Format</h2>
    <p class="section-sub">
      Paste raw MCP Blueprint commands on the left. The translator normalises node names, assigns unique IDs,
      makes all fields explicit, and ensures <code>compile_blueprint</code> always runs last — ready for <code>POST /unreal/execute</code>.
    </p>
    <div class="translator-grid">
      <div class="t-panel">
        <div class="t-header">
          <span class="t-label">Raw MCP Input</span>
          <span class="t-badge badge-mcp">MCP JSON</span>
        </div>
        <textarea id="t-input" class="t-body" style="resize:none;outline:none;border:none;font-family:'JetBrains Mono',monospace;font-size:12px;line-height:1.8;background:transparent;color:var(--text2)" placeholder='Paste raw MCP commands here, e.g.:
{
  "commands": [
    {
      "action": "create_blueprint",
      "name": "BP_Enemy",
      "parent_class": "Character"
    },
    {
      "action": "add_node",
      "blueprint": "BP_Enemy",
      "node": "event beginplay",
      "id": "node_0",
      "x": 0,
      "y": 0
    },
    {
      "action": "connect_nodes",
      "blueprint": "BP_Enemy",
      "from_node": "node_0",
      "from_pin": "then",
      "to_node": "node_1",
      "to_pin": "exec"
    },
    {
      "action": "compile_blueprint",
      "name": "BP_Enemy"
    }
  ]
}'></textarea>
        <div class="t-footer">
          <button class="trans-btn" id="trans-btn" onclick="runTranslate()">
            <span id="trans-content">🔄 Translate</span>
          </button>
          <button class="copy-btn" id="copy-input-btn" onclick="copyInput()">Copy Input</button>
        </div>
      </div>
      <div class="t-panel">
        <div class="t-header">
          <span class="t-label">Executable Output</span>
          <div style="display:flex;align-items:center;gap:8px">
            <button class="copy-btn" id="copy-out-btn" onclick="copyOutput()">Copy</button>
            <span class="t-badge badge-exec">Blueprint Manager JSON</span>
          </div>
        </div>
        <div class="t-body placeholder" id="t-output">← Paste MCP JSON and click Translate to see the normalised executable format.</div>
        <div id="t-meta" style="padding:10px 18px;border-top:1px solid var(--border);font-size:11px;color:var(--text3);display:none"></div>
      </div>
    </div>
  </div>
</section>

<!-- PLUGIN DOCS -->
<section id="plugin" class="alt-bg">
  <div class="container">
    <div class="section-label">Plugin Reference</div>
    <h2 class="section-title">Command Schema</h2>
    <p class="section-sub">All six commands the Unreal plugin understands. POST to <code>http://localhost:8080/unreal/execute</code> with a <code>commands</code> array.</p>
    <div class="feat-grid" style="margin-top:40px">
      <div class="feat">
        <div class="feat-icon">📦</div>
        <h3>create_blueprint</h3>
        <div class="code" style="margin-top:10px;font-size:11px">{
  "action": "create_blueprint",
  "name": "BP_MyActor",
  "parent_class": "Actor"
}</div>
      </div>
      <div class="feat">
        <div class="feat-icon">➕</div>
        <h3>add_node</h3>
        <div class="code" style="margin-top:10px;font-size:11px">{
  "action": "add_node",
  "blueprint": "BP_MyActor",
  "node": "Event BeginPlay",
  "id": "node_0",
  "x": 0, "y": 0
}</div>
      </div>
      <div class="feat">
        <div class="feat-icon">🔗</div>
        <h3>connect_nodes</h3>
        <div class="code" style="margin-top:10px;font-size:11px">{
  "action": "connect_nodes",
  "blueprint": "BP_MyActor",
  "from_node": "node_0",
  "from_pin": "Then",
  "to_node": "node_1",
  "to_pin": "Execute"
}</div>
      </div>
      <div class="feat">
        <div class="feat-icon">📋</div>
        <h3>add_variable</h3>
        <div class="code" style="margin-top:10px;font-size:11px">{
  "action": "add_variable",
  "blueprint": "BP_MyActor",
  "variable_name": "Health",
  "variable_type": "Float",
  "default_value": 100.0
}</div>
      </div>
      <div class="feat">
        <div class="feat-icon">✏️</div>
        <h3>set_variable</h3>
        <div class="code" style="margin-top:10px;font-size:11px">{
  "action": "set_variable",
  "blueprint": "BP_MyActor",
  "variable_name": "Health",
  "value": "75"
}</div>
      </div>
      <div class="feat">
        <div class="feat-icon">⚡</div>
        <h3>compile_blueprint</h3>
        <div class="code" style="margin-top:10px;font-size:11px">{
  "action": "compile_blueprint",
  "name": "BP_MyActor"
}</div>
      </div>
    </div>
  </div>
</section>

<!-- DOWNLOAD -->
<section>
  <div class="container">
    <div class="dl-card">
      <div style="font-size:48px;margin-bottom:16px">⬇</div>
      <h3>Download the Plugin</h3>
      <p>Get the complete MCPBlueprint Unreal Engine 5 plugin — C++ source, .uplugin, Build.cs, and all headers included. MIT licensed and open source.</p>
      <div class="dl-links">
        <a href="https://github.com/mkbrown261/unreal-assistant/releases" target="_blank" class="btn-primary">⬇ Download Latest Release</a>
        <a href="https://github.com/mkbrown261/unreal-assistant" target="_blank" class="btn-ghost">⭐ View Source on GitHub</a>
      </div>
      <p style="margin-top:20px;font-size:12px;color:var(--text3)">Unreal Engine 5.1+ · C++17 · MIT License · No marketplace account required</p>
    </div>
  </div>
</section>

<!-- FOOTER -->
<footer>
  <div class="footer-logo">⚡ Unreal Assistant</div>
  <div class="footer-links">
    <a class="footer-link" href="https://github.com/mkbrown261/unreal-assistant" target="_blank">GitHub</a>
    <a class="footer-link" href="https://github.com/mkbrown261/unreal-assistant/releases" target="_blank">Releases</a>
    <a class="footer-link" href="#plugin">Docs</a>
    <a class="footer-link" href="#translator">Translator</a>
  </div>
  <div class="footer-copy">© 2025 Unreal Assistant · Hono + Cloudflare Pages</div>
</footer>

<script>
function go(id){ document.getElementById(id)?.scrollIntoView({behavior:'smooth'}) }

// ── Translator ──────────────────────────────────────────────────────────────
let lastTranslated = ''

async function runTranslate() {
  const raw = document.getElementById('t-input').value.trim()
  if (!raw) { toast('Paste MCP JSON first', 'err'); return }

  let parsed
  try { parsed = JSON.parse(raw) } catch { toast('Invalid JSON — check your input', 'err'); return }

  const commands = parsed.commands || (Array.isArray(parsed) ? parsed : null)
  if (!commands) { toast("Input must have a \\"commands\\" array", 'err'); return }

  const btn = document.getElementById('trans-btn')
  const content = document.getElementById('trans-content')
  const out = document.getElementById('t-output')
  const meta = document.getElementById('t-meta')
  const copyOut = document.getElementById('copy-out-btn')

  btn.disabled = true
  content.innerHTML = '<div class="spin"></div> Translating…'
  out.className = 't-body'
  out.textContent = 'Translating…'
  copyOut.style.display = 'none'
  meta.style.display = 'none'

  try {
    const res = await fetch('/api/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ commands })
    })
    const data = await res.json()
    if (!res.ok || data.error) throw new Error(data.error || 'Translate failed')

    lastTranslated = JSON.stringify({ translated: data.translated }, null, 2)
    out.className = 't-body'
    out.innerHTML = syntaxHL(lastTranslated)
    copyOut.style.display = 'block'

    meta.style.display = 'block'
    meta.textContent = '✓ ' + data.meta.input_count + ' commands in → ' + data.meta.output_count + ' translated · ready for POST /unreal/execute'
    toast('Translated ' + data.meta.output_count + ' commands', 'ok')
  } catch(e) {
    out.className = 't-body placeholder'
    out.textContent = '✕ ' + e.message
    toast(e.message, 'err')
  } finally {
    btn.disabled = false
    content.textContent = '🔄 Translate'
  }
}

function copyInput() {
  const v = document.getElementById('t-input').value
  if (!v) return
  navigator.clipboard.writeText(v).then(() => toast('Input copied!', 'ok'))
}

function copyOutput() {
  if (!lastTranslated) return
  navigator.clipboard.writeText(lastTranslated).then(() => {
    toast('Copied!', 'ok')
    const btn = document.getElementById('copy-out-btn')
    btn.textContent = 'Copied!'
    setTimeout(() => btn.textContent = 'Copy', 1800)
  })
}

// ── JSON syntax highlight ───────────────────────────────────────────────────
function syntaxHL(json) {
  return json
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/("(\\\\u[a-zA-Z0-9]{4}|\\\\[^u]|[^\\\\"])*"(\\s*:)?|\\b(true|false|null)\\b|-?\\d+(?:\\.\\d*)?(?:[eE][+\\-]?\\d+)?)/g, m => {
      let cls = 'jn'
      if (/^"/.test(m)) {
        if (/:$/.test(m)) {
          const k = m.replace(/"/g,'').replace(':','').trim()
          cls = k === 'action' ? 'ja' : 'jk'
        } else cls = 'js'
      } else if (/true|false/.test(m)) cls = 'jb'
      return '<span class="'+cls+'">'+m+'</span>'
    })
    .replace(/([{}\\[\\]])/g,'<span class="jb">$1</span>')
}

// ── Toast ───────────────────────────────────────────────────────────────────
function toast(msg, type) {
  const t = document.createElement('div')
  t.className = 'toast toast-' + (type === 'ok' ? 'ok' : 'err')
  t.textContent = msg
  document.body.appendChild(t)
  setTimeout(() => t.remove(), 3000)
}
</script>

</body>
</html>`))

export default app
