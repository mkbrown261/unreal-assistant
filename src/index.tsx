import { Hono } from 'hono'
import { cors } from 'hono/cors'

const app = new Hono<{ Bindings: { OPENAI_API_KEY?: string } }>()

app.use('/api/*', cors())

// ── Landing page ─────────────────────────────────────────────────────────────
app.get('/', (c) => {
  return c.html(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Unreal Assistant — AI Blueprint Generator</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg:        #0a0a0f;
      --bg2:       #0f0f1a;
      --bg3:       #141428;
      --panel:     #12121f;
      --border:    rgba(138,43,226,0.18);
      --border2:   rgba(138,43,226,0.35);
      --purple:    #8a2be2;
      --purple2:   #a855f7;
      --purple3:   #c084fc;
      --cyan:      #00d4ff;
      --cyan2:     #06b6d4;
      --green:     #10b981;
      --orange:    #f59e0b;
      --red:       #ef4444;
      --text:      #e2e8f0;
      --text2:     #94a3b8;
      --text3:     #64748b;
      --glow:      0 0 40px rgba(138,43,226,0.25);
      --glow2:     0 0 80px rgba(138,43,226,0.15);
    }
    * { margin:0; padding:0; box-sizing:border-box; }
    html { scroll-behavior: smooth; }
    body {
      font-family:'Inter',sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      overflow-x: hidden;
    }

    /* ── Grid bg ── */
    body::before {
      content:'';
      position:fixed; inset:0; z-index:0; pointer-events:none;
      background-image:
        linear-gradient(rgba(138,43,226,0.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(138,43,226,0.04) 1px, transparent 1px);
      background-size: 40px 40px;
    }

    /* ── Nav ── */
    nav {
      position:fixed; top:0; left:0; right:0; z-index:100;
      display:flex; align-items:center; justify-content:space-between;
      padding: 0 40px; height: 64px;
      background: rgba(10,10,15,0.85);
      backdrop-filter: blur(20px);
      border-bottom: 1px solid var(--border);
    }
    .nav-logo {
      display:flex; align-items:center; gap:10px;
      font-weight:800; font-size:17px; color:#fff; text-decoration:none;
    }
    .nav-logo-icon {
      width:34px; height:34px;
      background: linear-gradient(135deg, var(--purple), var(--purple2));
      border-radius:9px;
      display:flex; align-items:center; justify-content:center;
      font-size:17px; box-shadow: 0 0 20px rgba(138,43,226,0.5);
    }
    .nav-links { display:flex; align-items:center; gap:8px; }
    .nav-link {
      padding:7px 16px; border-radius:8px;
      font-size:13px; font-weight:500; color:var(--text2);
      text-decoration:none; transition:all .2s;
      cursor:pointer; background:none; border:none;
    }
    .nav-link:hover { color:#fff; background:rgba(255,255,255,0.06); }
    .nav-cta {
      padding:8px 20px; border-radius:9px;
      background: linear-gradient(135deg, var(--purple), var(--purple2));
      color:#fff; font-size:13px; font-weight:700;
      border:none; cursor:pointer;
      box-shadow: 0 0 20px rgba(138,43,226,0.35);
      transition:all .2s; text-decoration:none;
    }
    .nav-cta:hover { transform:translateY(-1px); box-shadow:0 0 30px rgba(168,85,247,0.5); }

    /* ── Hero ── */
    .hero {
      position:relative; z-index:1;
      min-height: 100vh;
      display:flex; flex-direction:column; align-items:center; justify-content:center;
      text-align:center; padding: 100px 24px 60px;
    }
    .hero-badge {
      display:inline-flex; align-items:center; gap:8px;
      padding:6px 16px; border-radius:99px;
      background: rgba(138,43,226,0.12);
      border: 1px solid var(--border2);
      font-size:12px; font-weight:600; color:var(--purple3);
      margin-bottom:28px; letter-spacing:.04em;
    }
    .hero-badge-dot {
      width:6px; height:6px; border-radius:50%;
      background: var(--green);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%,100%{ opacity:1; transform:scale(1); }
      50%{ opacity:.5; transform:scale(1.5); }
    }
    .hero h1 {
      font-size: clamp(42px,8vw,90px);
      font-weight:900; line-height:1.05;
      letter-spacing:-0.03em; margin-bottom:24px;
      background: linear-gradient(135deg, #fff 0%, var(--purple3) 50%, var(--cyan) 100%);
      -webkit-background-clip:text; -webkit-text-fill-color:transparent;
      background-clip:text;
    }
    .hero-sub {
      font-size: clamp(16px,2.5vw,22px);
      color:var(--text2); max-width:640px;
      line-height:1.65; margin-bottom:44px;
    }
    .hero-actions { display:flex; gap:14px; flex-wrap:wrap; justify-content:center; }
    .btn-primary {
      padding:14px 32px; border-radius:12px;
      background: linear-gradient(135deg, var(--purple), var(--purple2));
      color:#fff; font-size:15px; font-weight:700;
      border:none; cursor:pointer;
      box-shadow: 0 0 30px rgba(138,43,226,0.4);
      transition:all .25s;
    }
    .btn-primary:hover { transform:translateY(-2px); box-shadow:0 0 50px rgba(168,85,247,0.55); }
    .btn-secondary {
      padding:14px 32px; border-radius:12px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.12);
      color:var(--text); font-size:15px; font-weight:600;
      cursor:pointer; transition:all .25s;
    }
    .btn-secondary:hover { background:rgba(255,255,255,0.09); transform:translateY(-2px); }

    /* ── Demo terminal ── */
    .hero-terminal {
      margin-top:64px; width:100%; max-width:820px;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius:16px;
      overflow:hidden;
      box-shadow: var(--glow), 0 40px 80px rgba(0,0,0,0.6);
    }
    .terminal-header {
      display:flex; align-items:center; gap:8px;
      padding:12px 18px;
      background: rgba(255,255,255,0.03);
      border-bottom:1px solid var(--border);
    }
    .terminal-dot { width:12px; height:12px; border-radius:50%; }
    .terminal-title {
      margin-left:8px; font-size:12px; font-weight:600;
      color:var(--text3); font-family:'JetBrains Mono',monospace;
    }
    .terminal-body { padding:24px; font-family:'JetBrains Mono',monospace; font-size:13px; text-align:left; }
    .t-comment { color:var(--text3); }
    .t-key { color:var(--purple3); }
    .t-str { color:var(--cyan); }
    .t-num { color:var(--orange); }
    .t-bool { color:var(--green); }
    .t-bracket { color:var(--text2); }
    .t-line { line-height:1.8; }

    /* ── Section shared ── */
    section { position:relative; z-index:1; padding:100px 24px; }
    .section-label {
      font-size:11px; font-weight:700; letter-spacing:.12em;
      color:var(--purple2); text-transform:uppercase; margin-bottom:12px;
    }
    .section-title {
      font-size: clamp(28px,5vw,48px);
      font-weight:900; line-height:1.1; letter-spacing:-.02em;
      margin-bottom:16px;
    }
    .section-sub { font-size:17px; color:var(--text2); line-height:1.65; max-width:560px; }
    .container { max-width:1200px; margin:0 auto; }

    /* ── How it works ── */
    .how-grid {
      display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
      gap:24px; margin-top:60px;
    }
    .how-card {
      background:var(--panel);
      border:1px solid var(--border);
      border-radius:16px; padding:32px;
      transition:all .3s; position:relative; overflow:hidden;
    }
    .how-card::before {
      content:''; position:absolute; inset:0;
      background:linear-gradient(135deg, rgba(138,43,226,0.06) 0%, transparent 60%);
      opacity:0; transition:.3s;
    }
    .how-card:hover { border-color:var(--border2); transform:translateY(-4px); box-shadow:var(--glow); }
    .how-card:hover::before { opacity:1; }
    .how-num {
      font-size:11px; font-weight:700; letter-spacing:.1em;
      color:var(--purple3); margin-bottom:16px;
    }
    .how-icon {
      width:48px; height:48px; border-radius:12px;
      display:flex; align-items:center; justify-content:center;
      font-size:22px; margin-bottom:20px;
    }
    .how-card h3 { font-size:18px; font-weight:700; margin-bottom:10px; }
    .how-card p { font-size:14px; color:var(--text2); line-height:1.65; }

    /* ── Interactive demo ── */
    .demo-section { background: var(--bg2); }
    .demo-container {
      display:grid; grid-template-columns:1fr 1fr; gap:24px;
      margin-top:56px;
    }
    @media(max-width:768px){ .demo-container { grid-template-columns:1fr; } }
    .demo-input-panel, .demo-output-panel {
      background:var(--panel); border:1px solid var(--border);
      border-radius:16px; overflow:hidden;
    }
    .panel-header {
      display:flex; align-items:center; justify-content:space-between;
      padding:14px 20px;
      background:rgba(255,255,255,0.025);
      border-bottom:1px solid var(--border);
    }
    .panel-label {
      font-size:11px; font-weight:700; letter-spacing:.1em;
      color:var(--text3); text-transform:uppercase;
    }
    .panel-badge {
      font-size:10px; font-weight:700; padding:3px 10px;
      border-radius:99px; letter-spacing:.05em;
    }
    .badge-ai { background:rgba(168,85,247,0.15); color:var(--purple3); }
    .badge-json { background:rgba(0,212,255,0.1); color:var(--cyan); }
    .demo-textarea {
      width:100%; min-height:180px; padding:20px;
      background:transparent; border:none; outline:none; resize:vertical;
      font-family:'Inter',sans-serif; font-size:14px; color:var(--text);
      line-height:1.7;
    }
    .demo-textarea::placeholder { color:var(--text3); }
    .demo-actions {
      padding:14px 20px;
      border-top:1px solid var(--border);
      display:flex; align-items:center; justify-content:space-between; gap:12px;
    }
    .generate-btn {
      flex:1; padding:11px 24px; border-radius:10px;
      background:linear-gradient(135deg, var(--purple), var(--purple2));
      color:#fff; font-size:14px; font-weight:700;
      border:none; cursor:pointer;
      box-shadow:0 0 20px rgba(138,43,226,0.35);
      transition:all .2s;
      display:flex; align-items:center; justify-content:center; gap:8px;
    }
    .generate-btn:hover { transform:translateY(-1px); box-shadow:0 0 30px rgba(168,85,247,0.5); }
    .generate-btn:disabled { opacity:.5; cursor:not-allowed; transform:none; }
    .demo-output {
      padding:20px; font-family:'JetBrains Mono',monospace; font-size:12px;
      line-height:1.8; min-height:280px; overflow-y:auto; max-height:420px;
      white-space:pre-wrap; color:var(--text2);
    }
    .demo-output.empty { color:var(--text3); font-style:italic; font-family:'Inter',sans-serif; font-size:14px; }
    .token-action { color:var(--purple3); }
    .token-key { color:var(--cyan2); }
    .token-string { color:var(--cyan); }
    .token-number { color:var(--orange); }
    .token-bracket { color:var(--text2); }

    /* ── Features ── */
    .features-grid {
      display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr));
      gap:20px; margin-top:60px;
    }
    .feature-card {
      background:var(--panel); border:1px solid var(--border);
      border-radius:14px; padding:28px;
      transition:.3s;
    }
    .feature-card:hover { border-color:var(--border2); box-shadow:var(--glow); }
    .feature-icon { font-size:28px; margin-bottom:16px; }
    .feature-card h3 { font-size:16px; font-weight:700; margin-bottom:8px; }
    .feature-card p { font-size:13px; color:var(--text2); line-height:1.65; }
    .feature-tags { display:flex; flex-wrap:wrap; gap:6px; margin-top:14px; }
    .feature-tag {
      font-size:10px; font-weight:700; padding:3px 10px;
      border-radius:99px; letter-spacing:.05em;
      background:rgba(138,43,226,0.12); color:var(--purple3);
      border:1px solid rgba(138,43,226,0.2);
    }

    /* ── Architecture ── */
    .arch-section { background:var(--bg2); }
    .arch-flow {
      display:flex; align-items:center; justify-content:center;
      flex-wrap:wrap; gap:0; margin-top:60px;
    }
    .arch-node {
      background:var(--panel); border:1px solid var(--border);
      border-radius:14px; padding:24px 28px; text-align:center;
      min-width:160px; transition:.3s;
    }
    .arch-node:hover { border-color:var(--border2); box-shadow:var(--glow); }
    .arch-node-icon { font-size:28px; margin-bottom:10px; }
    .arch-node-label { font-size:13px; font-weight:700; color:var(--text); margin-bottom:4px; }
    .arch-node-sub { font-size:11px; color:var(--text3); }
    .arch-arrow {
      display:flex; align-items:center; padding:0 8px; color:var(--purple3); font-size:20px;
    }

    /* ── Setup ── */
    .setup-steps { margin-top:56px; display:flex; flex-direction:column; gap:20px; }
    .setup-step {
      display:flex; gap:20px; align-items:flex-start;
      background:var(--panel); border:1px solid var(--border);
      border-radius:14px; padding:24px;
    }
    .step-num {
      width:36px; height:36px; border-radius:10px; flex-shrink:0;
      background:linear-gradient(135deg,var(--purple),var(--purple2));
      display:flex; align-items:center; justify-content:center;
      font-size:14px; font-weight:800; color:#fff;
      box-shadow:0 0 16px rgba(138,43,226,0.4);
    }
    .step-content h3 { font-size:15px; font-weight:700; margin-bottom:6px; }
    .step-content p { font-size:13px; color:var(--text2); line-height:1.6; margin-bottom:10px; }
    .code-block {
      background:rgba(0,0,0,0.4); border:1px solid rgba(255,255,255,0.07);
      border-radius:8px; padding:12px 16px;
      font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--cyan);
      overflow-x:auto; white-space:pre;
    }

    /* ── CTA ── */
    .cta-section {
      text-align:center; padding:120px 24px;
      background:linear-gradient(180deg,var(--bg) 0%,rgba(138,43,226,0.06) 50%,var(--bg) 100%);
    }
    .cta-glow {
      position:absolute; left:50%; top:50%; transform:translate(-50%,-50%);
      width:600px; height:400px; border-radius:50%;
      background:radial-gradient(ellipse, rgba(138,43,226,0.15) 0%, transparent 70%);
      pointer-events:none;
    }
    .cta-section h2 { font-size:clamp(32px,5vw,56px); font-weight:900; margin-bottom:20px; }
    .cta-section p { font-size:18px; color:var(--text2); margin-bottom:40px; max-width:520px; margin-left:auto; margin-right:auto; }

    /* ── Footer ── */
    footer {
      border-top:1px solid var(--border);
      padding:40px 40px;
      display:flex; align-items:center; justify-content:space-between;
      flex-wrap:wrap; gap:16px;
      position:relative; z-index:1;
    }
    .footer-logo { font-weight:800; font-size:15px; color:var(--text2); }
    .footer-links { display:flex; gap:24px; }
    .footer-link { font-size:13px; color:var(--text3); text-decoration:none; transition:.2s; }
    .footer-link:hover { color:var(--text2); }
    .footer-copy { font-size:12px; color:var(--text3); }

    /* ── Spinner ── */
    @keyframes spin { to { transform:rotate(360deg); } }
    .spinner {
      width:16px; height:16px; border-radius:50%;
      border:2px solid rgba(255,255,255,0.2);
      border-top-color:#fff;
      animation:spin .7s linear infinite;
    }

    /* ── Notifications ── */
    .toast {
      position:fixed; bottom:24px; right:24px; z-index:999;
      padding:12px 20px; border-radius:10px;
      font-size:13px; font-weight:600;
      backdrop-filter:blur(12px);
      border:1px solid; animation:slideIn .3s ease;
      pointer-events:none;
    }
    @keyframes slideIn { from{opacity:0;transform:translateY(12px)} to{opacity:1;transform:translateY(0)} }
    .toast-success { background:rgba(16,185,129,0.15); border-color:rgba(16,185,129,0.3); color:#6ee7b7; }
    .toast-error   { background:rgba(239,68,68,0.12);  border-color:rgba(239,68,68,0.25);  color:#fca5a5; }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar { width:6px; height:6px; }
    ::-webkit-scrollbar-track { background:transparent; }
    ::-webkit-scrollbar-thumb { background:rgba(138,43,226,0.3); border-radius:99px; }
  </style>
</head>
<body>

<!-- NAV -->
<nav>
  <a href="#" class="nav-logo">
    <div class="nav-logo-icon">⚡</div>
    Unreal Assistant
  </a>
  <div class="nav-links">
    <button class="nav-link" onclick="scrollTo('how')">How It Works</button>
    <button class="nav-link" onclick="scrollTo('demo')">Live Demo</button>
    <button class="nav-link" onclick="scrollTo('features')">Features</button>
    <button class="nav-link" onclick="scrollTo('setup')">Setup</button>
    <a href="#demo" class="nav-cta">Try It Free ↗</a>
  </div>
</nav>

<!-- HERO -->
<section class="hero">
  <div class="hero-badge">
    <span class="hero-badge-dot"></span>
    AI-Powered Blueprint Generator · Powered by OpenAI
  </div>
  <h1>Build Unreal Blueprints<br/>with Plain English</h1>
  <p class="hero-sub">
    Describe your game logic in plain English. Unreal Assistant converts it to structured Blueprint JSON commands — ready to execute inside Unreal Engine via MCP.
  </p>
  <div class="hero-actions">
    <button class="btn-primary" onclick="document.getElementById('demo-section').scrollIntoView({behavior:'smooth'})">
      ⚡ Generate a Blueprint
    </button>
    <a href="https://github.com/mkbrown261/unreal-assistant" target="_blank" class="btn-secondary">
      ⭐ View on GitHub
    </a>
  </div>

  <!-- Animated terminal preview -->
  <div class="hero-terminal">
    <div class="terminal-header">
      <div class="terminal-dot" style="background:#ef4444"></div>
      <div class="terminal-dot" style="background:#f59e0b"></div>
      <div class="terminal-dot" style="background:#10b981"></div>
      <span class="terminal-title">blueprint_output.json</span>
    </div>
    <div class="terminal-body" id="hero-terminal-body">
      <div class="t-line"><span class="t-bracket">{</span></div>
      <div class="t-line">  <span class="t-key">"commands"</span><span class="t-bracket">: [</span></div>
      <div class="t-line">    <span class="t-bracket">{</span></div>
      <div class="t-line">      <span class="t-key">"action"</span>: <span class="t-str">"create_blueprint"</span>,</div>
      <div class="t-line">      <span class="t-key">"name"</span>: <span class="t-str">"BP_EnemyAI"</span></div>
      <div class="t-line">    <span class="t-bracket">},</span></div>
      <div class="t-line">    <span class="t-bracket">{</span></div>
      <div class="t-line">      <span class="t-key">"action"</span>: <span class="t-str">"add_node"</span>,</div>
      <div class="t-line">      <span class="t-key">"node"</span>: <span class="t-str">"Event BeginPlay"</span>,</div>
      <div class="t-line">      <span class="t-key">"blueprint"</span>: <span class="t-str">"BP_EnemyAI"</span></div>
      <div class="t-line">    <span class="t-bracket">},</span></div>
      <div class="t-line">    <span class="t-bracket">{</span></div>
      <div class="t-line">      <span class="t-key">"action"</span>: <span class="t-str">"add_node"</span>,</div>
      <div class="t-line">      <span class="t-key">"node"</span>: <span class="t-str">"Branch"</span>,</div>
      <div class="t-line">      <span class="t-key">"condition"</span>: <span class="t-str">"bIsPlayerInRange"</span></div>
      <div class="t-line">    <span class="t-bracket">},</span></div>
      <div class="t-line">    <span class="t-bracket">{</span></div>
      <div class="t-line">      <span class="t-key">"action"</span>: <span class="t-str">"connect_nodes"</span>,</div>
      <div class="t-line">      <span class="t-key">"from"</span>: <span class="t-str">"Event BeginPlay"</span>, <span class="t-key">"to"</span>: <span class="t-str">"Branch"</span></div>
      <div class="t-line">    <span class="t-bracket">},</span></div>
      <div class="t-line">    <span class="t-bracket">{</span></div>
      <div class="t-line">      <span class="t-key">"action"</span>: <span class="t-str">"compile_blueprint"</span>,</div>
      <div class="t-line">      <span class="t-key">"name"</span>: <span class="t-str">"BP_EnemyAI"</span></div>
      <div class="t-line">    <span class="t-bracket">}</span></div>
      <div class="t-line">  <span class="t-bracket">]</span></div>
      <div class="t-line"><span class="t-bracket">}</span></div>
    </div>
  </div>
</section>

<!-- HOW IT WORKS -->
<section id="how">
  <div class="container">
    <div class="section-label">How It Works</div>
    <h2 class="section-title">From English to Blueprint<br/>in Seconds</h2>
    <p class="section-sub">Three simple steps. No Blueprint knowledge required.</p>
    <div class="how-grid">
      <div class="how-card">
        <div class="how-num">STEP 01</div>
        <div class="how-icon" style="background:rgba(168,85,247,0.12)">💬</div>
        <h3>Describe Your Logic</h3>
        <p>Type what you want in plain English. "When the player enters the trigger box, play a sound and open the door" — that's all it takes.</p>
      </div>
      <div class="how-card">
        <div class="how-num">STEP 02</div>
        <div class="how-icon" style="background:rgba(0,212,255,0.1)">🧠</div>
        <h3>AI Generates Commands</h3>
        <p>Our AI system converts your description into a structured JSON array of Blueprint commands — nodes, connections, variables, and compilation steps.</p>
      </div>
      <div class="how-card">
        <div class="how-num">STEP 03</div>
        <div class="how-icon" style="background:rgba(16,185,129,0.12)">⚡</div>
        <h3>Execute in Unreal</h3>
        <p>Feed the JSON to the MCP Server. It routes commands to the Unreal Engine plugin, which creates the Blueprint directly inside your project.</p>
      </div>
    </div>
  </div>
</section>

<!-- LIVE DEMO -->
<section class="demo-section" id="demo-section">
  <div class="container">
    <div class="section-label">Live Demo</div>
    <h2 class="section-title">Generate Your Blueprint</h2>
    <p class="section-sub">Describe any game mechanic and watch the AI produce executable Blueprint commands.</p>
    <div class="demo-container">
      <!-- Input -->
      <div class="demo-input-panel">
        <div class="panel-header">
          <span class="panel-label">Your Prompt</span>
          <span class="panel-badge badge-ai">AI Input</span>
        </div>
        <textarea
          class="demo-textarea"
          id="demo-prompt"
          placeholder="Describe your Blueprint logic...

Examples:
• Create an enemy AI that chases the player when they get close
• Make a door that opens when the player presses E near it
• Build a health pickup that heals 25 HP on overlap
• Create a jumping mechanic with double jump support"
        ></textarea>
        <div class="demo-actions">
          <button class="generate-btn" id="generate-btn" onclick="generateBlueprint()">
            <span id="btn-content">⚡ Generate Blueprint</span>
          </button>
        </div>
        <!-- Quick prompts -->
        <div style="padding:0 20px 16px; display:flex; flex-wrap:wrap; gap:8px;">
          <button class="quick-prompt" onclick="setPrompt('Create an enemy AI that detects the player within 500 units, chases them, and plays an alert sound when detected')">Enemy AI</button>
          <button class="quick-prompt" onclick="setPrompt('Make a door that opens smoothly when the player presses E near it, with an interaction prompt UI')">Door System</button>
          <button class="quick-prompt" onclick="setPrompt('Build a health pickup actor that heals the player by 25 HP on overlap, then destroys itself')">Health Pickup</button>
          <button class="quick-prompt" onclick="setPrompt('Create a checkpoint system that saves the player position and respawns them there on death')">Checkpoint</button>
        </div>
      </div>
      <!-- Output -->
      <div class="demo-output-panel">
        <div class="panel-header">
          <span class="panel-label">Blueprint Commands</span>
          <div style="display:flex;align-items:center;gap:8px;">
            <button id="copy-btn" onclick="copyOutput()" style="display:none;padding:4px 12px;border-radius:6px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);color:var(--text2);font-size:11px;cursor:pointer;font-weight:600;">Copy</button>
            <span class="panel-badge badge-json">JSON Output</span>
          </div>
        </div>
        <div class="demo-output empty" id="demo-output">
          ← Enter a prompt and click Generate Blueprint to see the output here.
        </div>
        <div id="cmd-count" style="padding:10px 20px;border-top:1px solid var(--border);font-size:11px;color:var(--text3);display:none;"></div>
      </div>
    </div>
  </div>
</section>

<!-- FEATURES -->
<section id="features">
  <div class="container">
    <div class="section-label">Features</div>
    <h2 class="section-title">Everything You Need</h2>
    <p class="section-sub">A complete system from AI prompt to compiled Blueprint.</p>
    <div class="features-grid">
      <div class="feature-card">
        <div class="feature-icon">🎯</div>
        <h3>Smart Node Mapping</h3>
        <p>AI automatically selects the correct Unreal node types — Event BeginPlay, Branch, Cast To, Print String, Timeline, and hundreds more.</p>
        <div class="feature-tags"><span class="feature-tag">Event Nodes</span><span class="feature-tag">Flow Control</span><span class="feature-tag">Math Nodes</span></div>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🔗</div>
        <h3>Automatic Pin Connection</h3>
        <p>Every node is connected with correct execution flow. No floating nodes, no broken graphs — everything compiles on the first try.</p>
        <div class="feature-tags"><span class="feature-tag">Exec Pins</span><span class="feature-tag">Data Pins</span><span class="feature-tag">Auto-wire</span></div>
      </div>
      <div class="feature-card">
        <div class="feature-icon">📦</div>
        <h3>Variable Management</h3>
        <p>Automatically declares and initializes Blueprint variables with correct types — Bool, Float, Int, Vector, Object Reference, and more.</p>
        <div class="feature-tags"><span class="feature-tag">Bool</span><span class="feature-tag">Float</span><span class="feature-tag">Struct</span><span class="feature-tag">Reference</span></div>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🖥️</div>
        <h3>MCP Server Bridge</h3>
        <p>Node.js MCP server routes JSON commands to Unreal Engine's HTTP endpoint. Supports batch execution and real-time feedback.</p>
        <div class="feature-tags"><span class="feature-tag">Node.js</span><span class="feature-tag">REST API</span><span class="feature-tag">WebSocket</span></div>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🔌</div>
        <h3>Unreal Plugin Included</h3>
        <p>Complete C++ Unreal plugin with HTTP server, JSON parser, Blueprint executor, and FKismetEditorUtilities integration.</p>
        <div class="feature-tags"><span class="feature-tag">C++ Plugin</span><span class="feature-tag">HTTP Module</span><span class="feature-tag">Kismet</span></div>
      </div>
      <div class="feature-card">
        <div class="feature-icon">⚡</div>
        <h3>Instant Compilation</h3>
        <p>Every generated Blueprint is automatically compiled. Errors are reported back to the MCP server for AI-assisted debugging.</p>
        <div class="feature-tags"><span class="feature-tag">Auto-compile</span><span class="feature-tag">Error Feedback</span><span class="feature-tag">Hot Reload</span></div>
      </div>
    </div>
  </div>
</section>

<!-- ARCHITECTURE -->
<section class="arch-section" id="architecture">
  <div class="container" style="text-align:center;">
    <div class="section-label">Architecture</div>
    <h2 class="section-title">How The System Connects</h2>
    <p class="section-sub" style="margin:0 auto 24px;">A clean three-layer architecture — AI brain, MCP bridge, Unreal engine.</p>
    <div class="arch-flow">
      <div class="arch-node">
        <div class="arch-node-icon">💬</div>
        <div class="arch-node-label">Your Prompt</div>
        <div class="arch-node-sub">Plain English</div>
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-node" style="border-color:rgba(168,85,247,0.4);">
        <div class="arch-node-icon">🧠</div>
        <div class="arch-node-label">AI (OpenAI)</div>
        <div class="arch-node-sub">GPT-4o · JSON output</div>
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-node">
        <div class="arch-node-icon">⚙️</div>
        <div class="arch-node-label">MCP Server</div>
        <div class="arch-node-sub">Node.js · Port 3001</div>
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-node" style="border-color:rgba(0,212,255,0.3);">
        <div class="arch-node-icon">🎮</div>
        <div class="arch-node-label">Unreal Plugin</div>
        <div class="arch-node-sub">C++ · Port 8080</div>
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-node" style="border-color:rgba(16,185,129,0.4);">
        <div class="arch-node-icon">📋</div>
        <div class="arch-node-label">Blueprint</div>
        <div class="arch-node-sub">Compiled & Ready</div>
      </div>
    </div>
  </div>
</section>

<!-- SETUP -->
<section id="setup">
  <div class="container">
    <div class="section-label">Setup Guide</div>
    <h2 class="section-title">Get Running in Minutes</h2>
    <p class="section-sub">Three components to install and you're ready to generate Blueprints from AI.</p>
    <div class="setup-steps">
      <div class="setup-step">
        <div class="step-num">1</div>
        <div class="step-content">
          <h3>Clone & Install MCP Server</h3>
          <p>Clone the repository and install the Node.js MCP server that bridges AI output to Unreal Engine.</p>
          <div class="code-block">git clone https://github.com/mkbrown261/unreal-assistant
cd unreal-assistant/mcp-server
npm install
OPENAI_API_KEY=sk-... node server.js</div>
        </div>
      </div>
      <div class="setup-step">
        <div class="step-num">2</div>
        <div class="step-content">
          <h3>Install Unreal Engine Plugin</h3>
          <p>Copy the MCPBlueprint plugin into your Unreal project's Plugins folder and enable it in the Plugin Manager.</p>
          <div class="code-block">cp -r MCPBlueprintPlugin/ YourProject/Plugins/MCPBlueprint
# Open Unreal Engine
# Edit → Plugins → Search "MCPBlueprint" → Enable → Restart</div>
        </div>
      </div>
      <div class="setup-step">
        <div class="step-num">3</div>
        <div class="step-content">
          <h3>Configure & Generate</h3>
          <p>Add your OpenAI API key, start both servers, then describe your Blueprint logic in the web interface above.</p>
          <div class="code-block"># .env
OPENAI_API_KEY=sk-your-key-here
UNREAL_HOST=http://localhost:8080

# MCP Server starts on :3001
# Unreal plugin listens on :8080
# Web interface at https://unreal-assistant.pages.dev</div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- CTA -->
<section class="cta-section" style="position:relative;">
  <div class="cta-glow"></div>
  <div style="position:relative;z-index:1;">
    <div class="section-label" style="margin-bottom:16px;">Get Started Today</div>
    <h2>Start Building Smarter<br/>Blueprints Now</h2>
    <p>No Blueprint expertise required. Just describe what you want and let AI do the rest.</p>
    <div style="display:flex;gap:14px;justify-content:center;flex-wrap:wrap;">
      <button class="btn-primary" onclick="document.getElementById('demo-section').scrollIntoView({behavior:'smooth'})">
        ⚡ Try the Demo
      </button>
      <a href="https://github.com/mkbrown261/unreal-assistant" target="_blank" class="btn-secondary">
        View Source on GitHub
      </a>
    </div>
  </div>
</section>

<!-- FOOTER -->
<footer>
  <div class="footer-logo">⚡ Unreal Assistant</div>
  <div class="footer-links">
    <a class="footer-link" href="https://github.com/mkbrown261/unreal-assistant" target="_blank">GitHub</a>
    <a class="footer-link" href="#how">Docs</a>
    <a class="footer-link" href="#demo-section">Demo</a>
  </div>
  <div class="footer-copy">© 2025 Unreal Assistant · Built with Hono + Cloudflare Pages</div>
</footer>

<style>
.quick-prompt {
  font-size:11px; font-weight:600; padding:5px 12px; border-radius:99px;
  background:rgba(138,43,226,0.1); border:1px solid rgba(138,43,226,0.2);
  color:var(--purple3); cursor:pointer; transition:.2s;
}
.quick-prompt:hover { background:rgba(138,43,226,0.2); }
</style>

<script>
function scrollTo(id) {
  document.getElementById(id)?.scrollIntoView({behavior:'smooth'});
}

function setPrompt(text) {
  document.getElementById('demo-prompt').value = text;
  document.getElementById('demo-prompt').focus();
}

let lastOutput = '';

async function generateBlueprint() {
  const prompt = document.getElementById('demo-prompt').value.trim();
  if (!prompt) { showToast('Please enter a prompt first', 'error'); return; }

  const btn = document.getElementById('generate-btn');
  const btnContent = document.getElementById('btn-content');
  const output = document.getElementById('demo-output');
  const copyBtn = document.getElementById('copy-btn');
  const cmdCount = document.getElementById('cmd-count');

  btn.disabled = true;
  btnContent.innerHTML = '<div class="spinner"></div> Generating…';
  output.className = 'demo-output';
  output.innerHTML = '<span style="color:var(--text3);font-family:Inter,sans-serif;font-style:italic">Thinking…</span>';
  copyBtn.style.display = 'none';
  cmdCount.style.display = 'none';

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt })
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      throw new Error(data.error || 'Generation failed');
    }

    lastOutput = JSON.stringify(data.commands || data, null, 2);
    output.className = 'demo-output';
    output.innerHTML = syntaxHighlight(lastOutput);
    copyBtn.style.display = 'block';

    const count = (data.commands || []).length;
    if (count > 0) {
      cmdCount.style.display = 'block';
      cmdCount.innerHTML = '✓ ' + count + ' command' + (count!==1?'s':'') + ' generated · Ready to execute in Unreal Engine';
    }

    showToast('Blueprint generated! ' + count + ' commands ready.', 'success');
  } catch(e) {
    output.className = 'demo-output empty';
    output.textContent = '✕ Error: ' + e.message;
    showToast(e.message, 'error');
  } finally {
    btn.disabled = false;
    btnContent.innerHTML = '⚡ Generate Blueprint';
  }
}

function syntaxHighlight(json) {
  return json
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function(match) {
      let cls = 'token-number';
      if (/^"/.test(match)) {
        if (/:$/.test(match)) {
          const key = match.replace(/"/g,'').replace(':','');
          cls = key === 'action' ? 'token-action' : 'token-key';
        } else {
          cls = 'token-string';
        }
      } else if (/true|false/.test(match)) {
        cls = 'token-bracket';
      }
      return '<span class="' + cls + '">' + match + '</span>';
    })
    .replace(/([{}\[\]])/g, '<span class="token-bracket">$1</span>');
}

function copyOutput() {
  if (!lastOutput) return;
  navigator.clipboard.writeText(lastOutput).then(() => {
    showToast('Copied to clipboard!', 'success');
    document.getElementById('copy-btn').textContent = 'Copied!';
    setTimeout(() => document.getElementById('copy-btn').textContent = 'Copy', 1800);
  });
}

function showToast(msg, type) {
  const t = document.createElement('div');
  t.className = 'toast toast-' + type;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

// Enter key to generate
document.getElementById('demo-prompt').addEventListener('keydown', function(e) {
  if (e.ctrlKey && e.key === 'Enter') generateBlueprint();
});
</script>

</body>
</html>`)
})

// ── Blueprint generation API ──────────────────────────────────────────────────
const SYSTEM_PROMPT = `You are an Unreal Engine Blueprint Generation System.

Your job is to convert user intent into structured executable commands for Unreal Engine via MCP.

You DO NOT explain.
You DO NOT give tutorials.
You ONLY output structured JSON.

You must think like a Blueprint system:
- Everything is nodes
- Everything is execution flow
- All logic must be connected

AVAILABLE COMMANDS:
1. create_blueprint
2. add_node
3. connect_nodes
4. set_variable
5. add_variable
6. compile_blueprint

RULES:
- Always create blueprint first
- Always use valid Unreal node names (Event BeginPlay, Event Tick, Event ActorBeginOverlap, Print String, Branch, Cast To, Set, Get, Sequence, Timeline, Delay, etc.)
- Always connect execution flow (no floating nodes)
- Break logic into clear sequential steps
- Always end with compile_blueprint
- Use consistent blueprint naming (BP_<Name>)
- Avoid ambiguity
- Add variables with add_variable before using them with set_variable
- Include position hints (x, y) on nodes for clean graph layout

OUTPUT FORMAT - return ONLY valid JSON, no markdown, no explanation:
{
  "commands": [
    {
      "action": "create_blueprint",
      "name": "BP_ExampleName",
      "parent_class": "Actor"
    },
    {
      "action": "add_variable",
      "blueprint": "BP_ExampleName",
      "variable_name": "bIsActive",
      "variable_type": "Boolean",
      "default_value": false
    },
    {
      "action": "add_node",
      "blueprint": "BP_ExampleName",
      "node": "Event BeginPlay",
      "id": "node_0",
      "x": 0,
      "y": 0
    },
    {
      "action": "connect_nodes",
      "blueprint": "BP_ExampleName",
      "from_node": "node_0",
      "from_pin": "Then",
      "to_node": "node_1",
      "to_pin": "Execute"
    },
    {
      "action": "compile_blueprint",
      "name": "BP_ExampleName"
    }
  ]
}`;

app.post('/api/generate', async (c) => {
  const apiKey = c.env.OPENAI_API_KEY
  if (!apiKey) {
    // Return a demo response when no API key is configured
    return c.json(getDemoResponse(await c.req.json().then(b => b.prompt || '').catch(() => '')))
  }

  let body: { prompt?: string }
  try { body = await c.req.json() } catch { return c.json({ error: 'Invalid JSON body' }, 400) }
  if (!body.prompt?.trim()) return c.json({ error: 'prompt is required' }, 400)

  try {
    const res = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: 'gpt-4o',
        response_format: { type: 'json_object' },
        messages: [
          { role: 'system', content: SYSTEM_PROMPT },
          { role: 'user', content: body.prompt.trim() }
        ],
        max_tokens: 2000,
        temperature: 0.3,
      })
    })

    if (!res.ok) {
      const err = await res.text()
      return c.json({ error: `OpenAI error: ${res.status}` }, 502)
    }

    const data = await res.json() as any
    const content = data.choices?.[0]?.message?.content
    if (!content) return c.json({ error: 'No content from AI' }, 502)

    const parsed = JSON.parse(content)
    return c.json(parsed)
  } catch (e: any) {
    return c.json({ error: e.message || 'Generation failed' }, 500)
  }
})

// ── Demo response (no API key) ───────────────────────────────────────────────
function getDemoResponse(prompt: string) {
  const lower = prompt.toLowerCase()
  const isEnemy = lower.includes('enemy') || lower.includes('ai') || lower.includes('chase')
  const isDoor  = lower.includes('door')  || lower.includes('open')
  const isHealth = lower.includes('health') || lower.includes('heal') || lower.includes('pickup')

  if (isEnemy) return {
    commands: [
      { action: 'create_blueprint', name: 'BP_EnemyAI', parent_class: 'Character' },
      { action: 'add_variable', blueprint: 'BP_EnemyAI', variable_name: 'bIsPlayerInRange', variable_type: 'Boolean', default_value: false },
      { action: 'add_variable', blueprint: 'BP_EnemyAI', variable_name: 'DetectionRadius', variable_type: 'Float', default_value: 500.0 },
      { action: 'add_variable', blueprint: 'BP_EnemyAI', variable_name: 'ChaseSpeed', variable_type: 'Float', default_value: 300.0 },
      { action: 'add_node', blueprint: 'BP_EnemyAI', node: 'Event BeginPlay', id: 'node_0', x: 0, y: 0 },
      { action: 'add_node', blueprint: 'BP_EnemyAI', node: 'Print String', id: 'node_1', x: 300, y: 0, params: { InString: 'Enemy AI Initialized' } },
      { action: 'add_node', blueprint: 'BP_EnemyAI', node: 'Event Tick', id: 'node_2', x: 0, y: 300 },
      { action: 'add_node', blueprint: 'BP_EnemyAI', node: 'Get Player Pawn', id: 'node_3', x: 200, y: 400 },
      { action: 'add_node', blueprint: 'BP_EnemyAI', node: 'Get Distance To', id: 'node_4', x: 450, y: 350 },
      { action: 'add_node', blueprint: 'BP_EnemyAI', node: 'Branch', id: 'node_5', x: 700, y: 300, condition: 'Distance <= DetectionRadius' },
      { action: 'add_node', blueprint: 'BP_EnemyAI', node: 'AI Move To', id: 'node_6', x: 950, y: 200, params: { GoalActor: 'PlayerPawn' } },
      { action: 'add_node', blueprint: 'BP_EnemyAI', node: 'Set', id: 'node_7', x: 950, y: 380, variable: 'bIsPlayerInRange', value: false },
      { action: 'connect_nodes', blueprint: 'BP_EnemyAI', from_node: 'node_0', from_pin: 'Then', to_node: 'node_1', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_EnemyAI', from_node: 'node_2', from_pin: 'Then', to_node: 'node_5', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_EnemyAI', from_node: 'node_5', from_pin: 'True', to_node: 'node_6', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_EnemyAI', from_node: 'node_5', from_pin: 'False', to_node: 'node_7', to_pin: 'Execute' },
      { action: 'compile_blueprint', name: 'BP_EnemyAI' }
    ]
  }

  if (isDoor) return {
    commands: [
      { action: 'create_blueprint', name: 'BP_InteractiveDoor', parent_class: 'Actor' },
      { action: 'add_variable', blueprint: 'BP_InteractiveDoor', variable_name: 'bIsOpen', variable_type: 'Boolean', default_value: false },
      { action: 'add_variable', blueprint: 'BP_InteractiveDoor', variable_name: 'bPlayerNearby', variable_type: 'Boolean', default_value: false },
      { action: 'add_variable', blueprint: 'BP_InteractiveDoor', variable_name: 'OpenAngle', variable_type: 'Float', default_value: 90.0 },
      { action: 'add_node', blueprint: 'BP_InteractiveDoor', node: 'Event ActorBeginOverlap', id: 'node_0', x: 0, y: 0 },
      { action: 'add_node', blueprint: 'BP_InteractiveDoor', node: 'Set', id: 'node_1', x: 280, y: 0, variable: 'bPlayerNearby', value: true },
      { action: 'add_node', blueprint: 'BP_InteractiveDoor', node: 'Print String', id: 'node_2', x: 480, y: 0, params: { InString: 'Press E to Open' } },
      { action: 'add_node', blueprint: 'BP_InteractiveDoor', node: 'Event ActorEndOverlap', id: 'node_3', x: 0, y: 220 },
      { action: 'add_node', blueprint: 'BP_InteractiveDoor', node: 'Set', id: 'node_4', x: 280, y: 220, variable: 'bPlayerNearby', value: false },
      { action: 'add_node', blueprint: 'BP_InteractiveDoor', node: 'InputAction IE_Interact', id: 'node_5', x: 0, y: 440 },
      { action: 'add_node', blueprint: 'BP_InteractiveDoor', node: 'Branch', id: 'node_6', x: 280, y: 440, condition: 'bPlayerNearby' },
      { action: 'add_node', blueprint: 'BP_InteractiveDoor', node: 'Branch', id: 'node_7', x: 520, y: 440, condition: 'bIsOpen' },
      { action: 'add_node', blueprint: 'BP_InteractiveDoor', node: 'Timeline', id: 'node_8', x: 760, y: 360, params: { name: 'DoorTimeline', length: 1.0 } },
      { action: 'connect_nodes', blueprint: 'BP_InteractiveDoor', from_node: 'node_0', from_pin: 'Then', to_node: 'node_1', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_InteractiveDoor', from_node: 'node_1', from_pin: 'Then', to_node: 'node_2', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_InteractiveDoor', from_node: 'node_3', from_pin: 'Then', to_node: 'node_4', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_InteractiveDoor', from_node: 'node_5', from_pin: 'Pressed', to_node: 'node_6', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_InteractiveDoor', from_node: 'node_6', from_pin: 'True', to_node: 'node_7', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_InteractiveDoor', from_node: 'node_7', from_pin: 'False', to_node: 'node_8', to_pin: 'Play' },
      { action: 'compile_blueprint', name: 'BP_InteractiveDoor' }
    ]
  }

  if (isHealth) return {
    commands: [
      { action: 'create_blueprint', name: 'BP_HealthPickup', parent_class: 'Actor' },
      { action: 'add_variable', blueprint: 'BP_HealthPickup', variable_name: 'HealAmount', variable_type: 'Float', default_value: 25.0 },
      { action: 'add_variable', blueprint: 'BP_HealthPickup', variable_name: 'bPickedUp', variable_type: 'Boolean', default_value: false },
      { action: 'add_node', blueprint: 'BP_HealthPickup', node: 'Event ActorBeginOverlap', id: 'node_0', x: 0, y: 0 },
      { action: 'add_node', blueprint: 'BP_HealthPickup', node: 'Branch', id: 'node_1', x: 280, y: 0, condition: 'NOT bPickedUp' },
      { action: 'add_node', blueprint: 'BP_HealthPickup', node: 'Cast To Character', id: 'node_2', x: 520, y: 0 },
      { action: 'add_node', blueprint: 'BP_HealthPickup', node: 'Call Function: ApplyHeal', id: 'node_3', x: 760, y: 0, params: { Amount: 'HealAmount' } },
      { action: 'add_node', blueprint: 'BP_HealthPickup', node: 'Set', id: 'node_4', x: 1000, y: 0, variable: 'bPickedUp', value: true },
      { action: 'add_node', blueprint: 'BP_HealthPickup', node: 'Play Sound at Location', id: 'node_5', x: 1000, y: 150, params: { Sound: 'S_PickupSound' } },
      { action: 'add_node', blueprint: 'BP_HealthPickup', node: 'Spawn Emitter at Location', id: 'node_6', x: 1000, y: 280, params: { Template: 'PS_PickupEffect' } },
      { action: 'add_node', blueprint: 'BP_HealthPickup', node: 'Destroy Actor', id: 'node_7', x: 1200, y: 0 },
      { action: 'connect_nodes', blueprint: 'BP_HealthPickup', from_node: 'node_0', from_pin: 'Then', to_node: 'node_1', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_HealthPickup', from_node: 'node_1', from_pin: 'True', to_node: 'node_2', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_HealthPickup', from_node: 'node_2', from_pin: 'Then', to_node: 'node_3', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_HealthPickup', from_node: 'node_3', from_pin: 'Then', to_node: 'node_4', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_HealthPickup', from_node: 'node_4', from_pin: 'Then', to_node: 'node_5', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_HealthPickup', from_node: 'node_5', from_pin: 'Then', to_node: 'node_7', to_pin: 'Execute' },
      { action: 'compile_blueprint', name: 'BP_HealthPickup' }
    ]
  }

  // Generic default response
  return {
    commands: [
      { action: 'create_blueprint', name: 'BP_CustomActor', parent_class: 'Actor' },
      { action: 'add_variable', blueprint: 'BP_CustomActor', variable_name: 'bIsActive', variable_type: 'Boolean', default_value: true },
      { action: 'add_variable', blueprint: 'BP_CustomActor', variable_name: 'DebugMessage', variable_type: 'String', default_value: 'Actor Started' },
      { action: 'add_node', blueprint: 'BP_CustomActor', node: 'Event BeginPlay', id: 'node_0', x: 0, y: 0 },
      { action: 'add_node', blueprint: 'BP_CustomActor', node: 'Branch', id: 'node_1', x: 280, y: 0, condition: 'bIsActive' },
      { action: 'add_node', blueprint: 'BP_CustomActor', node: 'Print String', id: 'node_2', x: 520, y: -80, params: { InString: 'DebugMessage', Duration: 5.0, TextColor: 'Green' } },
      { action: 'add_node', blueprint: 'BP_CustomActor', node: 'Print String', id: 'node_3', x: 520, y: 80, params: { InString: 'Actor is Inactive', Duration: 5.0, TextColor: 'Red' } },
      { action: 'connect_nodes', blueprint: 'BP_CustomActor', from_node: 'node_0', from_pin: 'Then', to_node: 'node_1', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_CustomActor', from_node: 'node_1', from_pin: 'True', to_node: 'node_2', to_pin: 'Execute' },
      { action: 'connect_nodes', blueprint: 'BP_CustomActor', from_node: 'node_1', from_pin: 'False', to_node: 'node_3', to_pin: 'Execute' },
      { action: 'compile_blueprint', name: 'BP_CustomActor' }
    ]
  }
}

export default app
