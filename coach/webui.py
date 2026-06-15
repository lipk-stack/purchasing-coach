"""Minimal local web UI on the stdlib http.server — no extra packages.

Serves a single-page chat interface for the same Coach used by the CLI:
free-form questions about the guideline plus the tender-checklist wizard.
The server binds to 127.0.0.1 only; generated workbooks are written to the
out dir and offered as downloads.

The page is one self-contained HTML document (inline CSS + JS, system fonts,
no CDN or build step) so it works on locked-down, offline corporate machines.
"""

import json
import threading
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .excel import write_checklist
from .llm import Coach
from .models import TenderChecklist
from .tender import output_name


class WebUI:
    def __init__(self, coach: Coach, backend, guideline_path: str,
                 template_path: str | Path | None, out_dir: str | Path = "."):
        self.coach = coach
        self.backend = backend
        self.guideline_path = str(guideline_path)
        self.template_path = template_path
        self.out_dir = Path(out_dir)
        self.generated: set[str] = set()  # downloadable file names

    # -- API operations ------------------------------------------------------
    def meta(self) -> dict:
        return {"backend": self.backend.name, "model": self.backend.model,
                "guideline": Path(self.guideline_path).name}

    def tender_start(self, item: str) -> dict:
        plan = self.coach.plan_interview(item)
        return {"questions": [{"key": q.key, "question": q.question}
                              for q in plan.questions]}

    def tender_finish(self, item: str, answers: list) -> dict:
        checklist: TenderChecklist = self.coach.build_checklist(
            item, [(str(q), str(a)) for q, a in answers])
        name = output_name(checklist.tender_info.purchase_item)
        write_checklist(checklist.tender_info, checklist.requirements,
                        self.out_dir / name, self.template_path)
        self.generated.add(name)
        return {"file": name, "download": f"/api/download/{name}",
                "count": len(checklist.requirements),
                "unverified": checklist.unverified_refs,
                "added_core": checklist.added_core_sections,
                "tender_info": checklist.tender_info.__dict__}

    def serve(self, port: int = 8765, open_browser: bool = True) -> None:
        server = self.make_server(port)
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        print(f"Purchasing Coach web UI: {url}  (Ctrl+C to stop)")
        if open_browser:
            threading.Timer(0.3, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")

    def make_server(self, port: int = 0) -> ThreadingHTTPServer:
        ui = self

        class Handler(_Handler):
            webui = ui

        return ThreadingHTTPServer(("127.0.0.1", port), Handler)


class _Handler(BaseHTTPRequestHandler):
    webui: WebUI  # set by WebUI.make_server
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    # -- routing -------------------------------------------------------------
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            self._respond(200, "text/html; charset=utf-8", body)
        elif self.path == "/api/meta":
            self._json(200, self.webui.meta())
        elif self.path.startswith("/api/download/"):
            self._download(self.path[len("/api/download/"):])
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "invalid JSON body"})
            return
        try:
            if self.path == "/api/chat":
                self._chat(payload)
            elif self.path == "/api/tender/start":
                item = str(payload.get("item") or "").strip()
                if not item:
                    self._json(400, {"error": "item description is required"})
                else:
                    self._json(200, self.webui.tender_start(item))
            elif self.path == "/api/tender/finish":
                item = str(payload.get("item") or "").strip()
                answers = payload.get("answers") or []
                if not item or not isinstance(answers, list):
                    self._json(400, {"error": "item and answers are required"})
                else:
                    self._json(200, self.webui.tender_finish(item, answers))
            else:
                self._json(404, {"error": "not found"})
        except Exception as exc:  # surface LLM/backend errors to the page
            self._json(500, {"error": str(exc)})

    # -- handlers ------------------------------------------------------------
    def _chat(self, payload: dict):
        messages = payload.get("messages") or []
        if not messages:
            self._json(400, {"error": "messages are required"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            for text in self.webui.coach.answer(messages):
                self._chunk(text.encode("utf-8"))
        except BrokenPipeError:  # client hit Stop / closed the tab
            return
        except Exception as exc:
            try:
                self._chunk(f"\n[error: {exc}]".encode("utf-8"))
            except BrokenPipeError:
                return
        try:
            self._chunk(b"")  # terminating chunk
        except BrokenPipeError:
            pass

    def _chunk(self, data: bytes):
        if data:
            self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
        else:
            self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _download(self, name: str):
        if name not in self.webui.generated:
            self._json(404, {"error": "unknown file"})
            return
        path = self.webui.out_dir / name
        if not path.is_file():
            self._json(404, {"error": "file no longer exists"})
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-"
                                         "officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- plumbing ------------------------------------------------------------
    def _respond(self, status: int, ctype: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: dict):
        self._respond(status, "application/json; charset=utf-8",
                      json.dumps(data).encode("utf-8"))


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Purchasing Coach</title>
<script>
  // Set the theme before first paint to avoid a flash.
  (function () {
    try {
      var t = localStorage.getItem('pc-theme');
      if (!t) t = matchMedia('(prefers-color-scheme: dark)').matches
                   ? 'dark' : 'light';
      document.documentElement.dataset.theme = t;
    } catch (e) { document.documentElement.dataset.theme = 'light'; }
  })();
</script>
<style>
  :root {
    --bg:#eef1f5; --panel:#ffffff; --panel-2:#f6f8fb; --ink:#15202b;
    --muted:#566676; --border:#d8e0e9; --accent:#1f4e78; --accent-2:#2e75b6;
    --accent-ink:#ffffff; --me:#e6f0fb; --me-border:#cfe0f3; --sys:#fff6e3;
    --sys-border:#efdfb6; --err:#b42318; --code:#eef1f5; --ring:#2e75b6;
    --shadow:0 1px 2px rgba(16,24,40,.06), 0 2px 6px rgba(16,24,40,.05);
    --radius:14px;
  }
  :root[data-theme="dark"] {
    --bg:#0e1319; --panel:#161d26; --panel-2:#1b2530; --ink:#e8eef4;
    --muted:#a3b3c2; --border:#27333f; --accent:#3f84c6; --accent-2:#5aa0e0;
    --accent-ink:#08101a; --me:#16263a; --me-border:#264056; --sys:#2c2611;
    --sys-border:#4a3f18; --err:#ff8a7a; --code:#0c1219; --ring:#5aa0e0;
    --shadow:0 1px 2px rgba(0,0,0,.5), 0 3px 10px rgba(0,0,0,.35);
  }
  * { box-sizing:border-box; }
  html, body { height:100%; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
         display:flex; flex-direction:column;
         -webkit-font-smoothing:antialiased; }
  .sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px;
             overflow:hidden; clip:rect(0,0,0,0); border:0; }

  header { background:var(--panel); border-bottom:1px solid var(--border);
           padding:10px 16px; display:flex; align-items:center; gap:12px;
           position:sticky; top:0; z-index:5; }
  .brand { display:flex; align-items:center; gap:11px; min-width:0; }
  .logo { width:34px; height:34px; flex:none; border-radius:9px;
          background:linear-gradient(135deg,var(--accent),var(--accent-2));
          color:#fff; display:grid; place-items:center; font-size:18px;
          box-shadow:var(--shadow); }
  .brand h1 { font-size:16px; margin:0; line-height:1.1; }
  .brand .meta { font-size:12px; color:var(--muted); display:block;
                 white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
                 max-width:62vw; }
  header .spacer { flex:1; }
  .icon { width:40px; height:40px; flex:none; border-radius:10px;
          border:1px solid var(--border); background:var(--panel-2);
          color:var(--ink); font-size:17px; cursor:pointer; line-height:1; }
  .icon:hover { border-color:var(--accent-2); }

  #log { flex:1; overflow-y:auto; padding:20px 16px 8px; scroll-behavior:smooth; }
  .thread { max-width:820px; margin:0 auto; display:flex; flex-direction:column;
            gap:14px; }
  .msg { padding:11px 14px 12px; border-radius:var(--radius);
         background:var(--panel); border:1px solid var(--border);
         box-shadow:var(--shadow); overflow-wrap:anywhere; }
  .msg.me { background:var(--me); border-color:var(--me-border);
            align-self:flex-end; max-width:88%; }
  .msg.sys { background:var(--sys); border-color:var(--sys-border); }
  .msg .who { display:flex; align-items:center; gap:8px; margin-bottom:5px; }
  .msg .av { width:22px; height:22px; flex:none; border-radius:6px;
             display:grid; place-items:center; font-size:11px; font-weight:700;
             color:#fff; background:var(--accent); }
  .msg.me .av { background:var(--accent-2); }
  .msg.sys .av { background:var(--sys-border); color:var(--ink); }
  .msg .name { font-size:11.5px; font-weight:700; color:var(--muted);
               text-transform:uppercase; letter-spacing:.04em; }
  .msg .copy { margin-left:auto; border:0; background:transparent;
               color:var(--muted); cursor:pointer; font-size:12px;
               padding:3px 7px; border-radius:7px; }
  .msg .copy:hover { background:var(--panel-2); color:var(--ink); }
  .msg .body { white-space:pre-wrap; }
  .msg .body.md { white-space:normal; }
  .msg .body.streaming::after { content:"▍"; margin-left:1px;
       animation:blink 1s steps(2) infinite; color:var(--accent-2); }
  @keyframes blink { 50% { opacity:0; } }

  .md p { margin:0 0 9px; } .md p:last-child { margin-bottom:0; }
  .md ul, .md ol { margin:0 0 9px; padding-left:22px; }
  .md li { margin:3px 0; }
  .md .h { font-weight:700; color:var(--accent); margin:11px 0 5px;
           font-size:15px; }
  .md code { background:var(--code); border-radius:5px; padding:1px 5px;
             font:13px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace; }
  .md pre { background:var(--code); border:1px solid var(--border);
            border-radius:9px; padding:11px 13px; overflow-x:auto; margin:0 0 9px;
            font:13px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace; }
  .md table { border-collapse:collapse; margin:5px 0 9px; font-size:14px;
              display:block; overflow-x:auto; }
  .md th, .md td { border:1px solid var(--border); padding:6px 11px;
                   text-align:left; vertical-align:top; }
  .md th { background:var(--accent); color:#fff; font-weight:600; }
  .md tr:nth-child(even) td { background:var(--panel-2); }

  a.dl { display:inline-flex; align-items:center; gap:7px; margin-top:9px;
         padding:9px 15px; min-height:40px; background:var(--accent);
         color:#fff; border-radius:10px; text-decoration:none; font-weight:600;
         box-shadow:var(--shadow); }
  a.dl:hover { background:var(--accent-2); }
  .warn { color:var(--err); font-weight:600; }
  .stopnote { color:var(--muted); font-size:12px; margin-top:6px;
              font-style:italic; }

  footer { padding:10px 16px calc(12px + env(safe-area-inset-bottom));
           background:var(--panel); border-top:1px solid var(--border); }
  .bar { max-width:820px; margin:0 auto; display:flex; gap:9px;
         align-items:flex-end; }
  textarea { flex:1; resize:none; padding:11px 13px; border-radius:12px;
             border:1px solid var(--border); background:var(--panel-2);
             color:var(--ink); font:inherit; min-height:48px; max-height:170px;
             overflow-y:auto; }
  textarea:focus-visible { outline:2px solid var(--ring); outline-offset:1px;
             border-color:transparent; }
  .btns { display:flex; gap:8px; }
  button { font:inherit; font-weight:600; cursor:pointer; border-radius:12px;
           min-height:48px; padding:0 18px; border:1px solid transparent; }
  button:focus-visible { outline:2px solid var(--ring); outline-offset:1px; }
  #send { background:var(--accent); color:#fff; }
  #send:hover { background:var(--accent-2); }
  #send.stop { background:var(--err); }
  #tender.ghost { background:var(--panel); color:var(--accent);
                  border-color:var(--border); }
  #tender.ghost:hover { border-color:var(--accent-2); }
  button:disabled { opacity:.45; cursor:default; }
  .hint { max-width:820px; margin:7px auto 0; font-size:12px;
          color:var(--muted); text-align:center; }

  @media (max-width:560px) {
    .brand h1 { font-size:15px; }
    .btns { flex-direction:column; }
    .hint { text-align:left; }
  }
  @media (prefers-reduced-motion:reduce) {
    * { scroll-behavior:auto !important; animation:none !important; }
  }
</style>
</head>
<body>
<header>
  <div class="brand">
    <span class="logo" aria-hidden="true">▦</span>
    <div>
      <h1>Purchasing Coach</h1>
      <span class="meta" id="meta">connecting…</span>
    </div>
  </div>
  <span class="spacer"></span>
  <button id="theme" class="icon" type="button"
          aria-label="Toggle dark mode" title="Toggle light / dark">🌙</button>
</header>

<main id="log" role="log" aria-live="polite" aria-label="Conversation"
      aria-relevant="additions text">
  <div class="thread" id="thread"></div>
</main>

<footer>
  <div class="bar">
    <textarea id="box" rows="1" autofocus aria-label="Message"
              placeholder="Ask about the guideline…"></textarea>
    <div class="btns">
      <button id="send" type="button" aria-label="Send message">Send</button>
      <button id="tender" class="ghost" type="button">Tender checklist</button>
    </div>
  </div>
  <div class="hint">Enter to send · Shift+Enter for a new line · Esc stops a
    reply. “Tender checklist” (or typing /tender) starts a short interview and
    produces an Excel checklist from your template; “cancel” aborts,
    “restart” starts over.</div>
</footer>
<div id="sr" class="sr-only" role="status" aria-live="assertive"></div>

<script>
const log = document.getElementById('log');
const thread = document.getElementById('thread');
const box = document.getElementById('box');
const sendBtn = document.getElementById('send');
const tenderBtn = document.getElementById('tender');
const themeBtn = document.getElementById('theme');
const sr = document.getElementById('sr');
let history = [];           // chat turns sent to the model
let tender = null;          // active interview state, or null
let busy = false;
let aborter = null;         // AbortController for the in-flight request

// ---- theme ---------------------------------------------------------------
function paintTheme() {
  themeBtn.textContent =
    document.documentElement.dataset.theme === 'dark' ? '☀️' : '🌙';
}
function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'dark'
             ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('pc-theme', next); } catch (e) {}
  paintTheme();
}
paintTheme();
themeBtn.addEventListener('click', toggleTheme);

// ---- meta ----------------------------------------------------------------
fetch('/api/meta').then(r => r.json()).then(m => {
  document.getElementById('meta').textContent =
    `${m.guideline} · ${m.backend} (${m.model})`;
}).catch(() => { document.getElementById('meta').textContent = 'offline'; });

// ---- markdown ------------------------------------------------------------
// Renders model replies: paragraphs, bullet/numbered lists, ### headings,
// **bold**, `code`, ``` fences and | tables |. Everything is HTML-escaped
// first; only our own tags are emitted. Code fences are buffered and only
// rendered once the closing fence arrives, so streaming never shows raw ```.
function md(src) {
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;');
  const inline = s => esc(s)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
  let html = '', list = null, table = false, fence = false, fenceBuf = [];
  const closeList = () => { if (list) { html += `</${list}>`; list = null; } };
  const closeTable = () => { if (table) { html += '</table>'; table = false; } };
  for (const line of src.split('\n')) {
    if (fence) {
      if (/^\s*```/.test(line)) {
        html += '<pre>' + esc(fenceBuf.join('\n')) + '</pre>';
        fence = false; fenceBuf = [];
      } else fenceBuf.push(line);
      continue;
    }
    if (/^\s*```/.test(line)) { closeList(); closeTable(); fence = true; continue; }
    if (/^\s*\|.*\|\s*$/.test(line)) {
      closeList();
      if (/^\s*\|[\s:|-]+\|\s*$/.test(line)) continue;  // |---|---| separator
      const cells = line.trim().replace(/^\|/, '').replace(/\|$/, '')
                        .split('|').map(c => inline(c.trim()));
      const tag = table ? 'td' : 'th';
      if (!table) { html += '<table>'; table = true; }
      html += '<tr>' + cells.map(c => `<${tag}>${c}</${tag}>`).join('') + '</tr>';
      continue;
    }
    closeTable();
    const h = line.match(/^#{1,6}\s+(.*)/);
    const li = line.match(/^\s*[-*+]\s+(.*)/);
    const num = line.match(/^\s*\d+[.)]\s+(.*)/);
    if (h) { closeList(); html += '<div class="h">' + inline(h[1]) + '</div>'; }
    else if (li) {
      if (list !== 'ul') { closeList(); html += '<ul>'; list = 'ul'; }
      html += '<li>' + inline(li[1]) + '</li>';
    } else if (num) {
      if (list !== 'ol') { closeList(); html += '<ol>'; list = 'ol'; }
      html += '<li>' + inline(num[1]) + '</li>';
    } else if (!line.trim()) { closeList(); }
    else { closeList(); html += '<p>' + inline(line) + '</p>'; }
  }
  if (fence) html += '<pre>' + esc(fenceBuf.join('\n')) + '</pre>';
  closeList(); closeTable();
  return html;
}

// ---- messages ------------------------------------------------------------
function nearBottom() {
  return log.scrollHeight - log.scrollTop - log.clientHeight < 90;
}
function keepDown(stick) { if (stick) log.scrollTop = log.scrollHeight; }

function add(who, cls, text) {
  const stick = nearBottom();
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  const head = document.createElement('div');
  head.className = 'who';
  const av = document.createElement('span');
  av.className = 'av'; av.setAttribute('aria-hidden', 'true');
  av.textContent = who === 'you' ? 'U' : (who === 'coach' ? 'PC' : 'i');
  const name = document.createElement('span');
  name.className = 'name'; name.textContent = who;
  head.append(av, name);
  if (who === 'coach') {
    const copy = document.createElement('button');
    copy.className = 'copy'; copy.type = 'button';
    copy.textContent = 'Copy'; copy.setAttribute('aria-label', 'Copy reply');
    head.appendChild(copy);
  }
  const body = document.createElement('div');
  body.className = 'body';
  body.textContent = text;
  div.append(head, body);
  thread.appendChild(div);
  keepDown(stick);
  return body;
}

function attachCopy(body) {
  const btn = body.parentElement.querySelector('.copy');
  if (btn) btn.addEventListener('click', () => {
    const t = body.innerText;
    (navigator.clipboard
        ? navigator.clipboard.writeText(t)
        : Promise.reject()).then(
      () => { btn.textContent = 'Copied'; setTimeout(() => btn.textContent = 'Copy', 1200); },
      () => { btn.textContent = 'Copy failed'; setTimeout(() => btn.textContent = 'Copy', 1200); });
  });
}

function announce(msg) { sr.textContent = msg; }

function setBusy(b) {
  busy = b;
  tenderBtn.disabled = b;
  if (b) {
    sendBtn.textContent = 'Stop';
    sendBtn.classList.add('stop');
    sendBtn.setAttribute('aria-label', 'Stop the current request');
  } else {
    sendBtn.textContent = 'Send';
    sendBtn.classList.remove('stop');
    sendBtn.setAttribute('aria-label', 'Send message');
    aborter = null;
  }
}

function stopRequest() {
  if (aborter) { announce('Stopping…'); aborter.abort(); }
}

add('coach', 'sys',
    'Hello! Ask me anything about the purchasing guideline, or click ' +
    '“Tender checklist” to prepare a tender for something you want to buy.');

// ---- chat ----------------------------------------------------------------
async function chat(text) {
  add('you', 'me', text);
  history.push({role: 'user', content: text});
  const body = add('coach', '', '');
  body.classList.add('streaming');
  setBusy(true);
  const ac = aborter = new AbortController();
  let full = '';
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({messages: history}), signal: ac.signal,
    });
    if (!resp.ok) throw new Error((await resp.json()).error || resp.status);
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    body.className = 'body md streaming';
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      const stick = nearBottom();
      full += dec.decode(value, {stream: true});
      body.innerHTML = md(full);
      keepDown(stick);
    }
    if (ac.signal.aborted) throw new DOMException('stopped', 'AbortError');
    history.push({role: 'assistant', content: full});
    announce('Reply complete.');
  } catch (err) {
    if (err.name === 'AbortError' || ac.signal.aborted) {
      // Keep whatever streamed so far so the conversation stays coherent.
      if (full) {
        body.innerHTML = md(full) + '<div class="stopnote">stopped</div>';
        history.push({role: 'assistant', content: full});
      } else {
        body.innerHTML = '<div class="stopnote">stopped</div>';
      }
    } else {
      body.className = 'body';
      body.innerHTML = '<span class="warn">Request failed: ' +
        err.message.replace(/</g, '&lt;') + '</span>';
      history.pop();
    }
  } finally {
    body.classList.remove('streaming');
    attachCopy(body);
    setBusy(false);
    box.focus();
  }
}

// ---- tender interview ----------------------------------------------------
function startTender() {
  if (busy) return;
  const restarting = tender !== null;
  tender = {stage: 'item', item: '', questions: [], answers: []};
  tenderBtn.textContent = 'Restart interview';
  add('coach', 'sys',
      (restarting ? 'Interview restarted — what' : 'Tender checklist — what') +
      ' do you want to buy? ' +
      'Describe the item or solution in one or two sentences. ' +
      '(Type “cancel” to abort or “restart” to start over.)');
  box.placeholder = 'e.g. 200 laptops for the sales team';
  box.focus();
}

function endTender() {
  tender = null;
  tenderBtn.textContent = 'Tender checklist';
  box.placeholder = 'Ask about the guideline…';
}

function askNext() {
  const i = tender.answers.length;
  add('coach', 'sys',
      `[${i + 1}/${tender.questions.length}] ${tender.questions[i].question}`);
}

async function tenderInput(text) {
  const word = text.toLowerCase();
  if (word === 'cancel') {
    endTender();
    add('coach', 'sys', 'Tender flow cancelled.');
    return;
  }
  if (word === 'restart' || word === '/tender') {
    startTender();
    return;
  }
  add('you', 'me', text);
  if (tender.stage === 'item') {
    tender.item = text;
    tender.stage = 'questions';
    const note = add('coach', 'sys',
                     'Thinking about the right questions for this purchase…');
    setBusy(true);
    const ac = aborter = new AbortController();
    try {
      const resp = await fetch('/api/tender/start', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({item: tender.item}), signal: ac.signal,
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || resp.status);
      tender.questions = data.questions;
      note.textContent = `I have ${data.questions.length} questions. ` +
                         'Answer briefly; reply “TBC” if you don’t know yet.';
      askNext();
    } catch (err) {
      note.innerHTML = (err.name === 'AbortError' || ac.signal.aborted)
        ? 'Interview stopped.'
        : '<span class="warn">Could not plan the interview: ' +
          err.message.replace(/</g, '&lt;') + '</span>';
      endTender();
    } finally {
      setBusy(false);
      box.focus();
    }
    return;
  }
  // answering questions
  tender.answers.push([tender.questions[tender.answers.length].question,
                       text || 'TBC']);
  if (tender.answers.length < tender.questions.length) {
    askNext();
    return;
  }
  const note = add('coach', 'sys',
                   'Building the compliance checklist from the guideline… ' +
                   'this can take a minute on a local model.');
  setBusy(true);
  const ac = aborter = new AbortController();
  try {
    const resp = await fetch('/api/tender/finish', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({item: tender.item, answers: tender.answers}),
      signal: ac.signal,
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.status);
    const unverified = (data.unverified || []).length
        ? ` <span class="warn">${data.unverified.length} clause ` +
          `reference(s) could not be matched to the guideline ` +
          `(${data.unverified.join(', ')}) — please verify those rows.</span>`
        : '';
    const addedCore = (data.added_core || []).length
        ? ` Guideline section(s) ${data.added_core.join(', ')} were ` +
          `added automatically to ensure full coverage (cross-cutting ` +
          `compliance plus sections your answers flagged as relevant).`
        : '';
    note.innerHTML = `Done — ${data.count} requirements for ` +
        `“${data.tender_info.purchase_item}”.` + addedCore + unverified +
        ' Vendors pick a Vendor Status (Compliant / Partially Compliant / ' +
        'Non-Compliant / Not Applicable) from the dropdown and explain in ' +
        'Vendor Remarks. The “Review & Approval” sheet tallies their ' +
        'submission live (including mandatory non-compliant rows) for your ' +
        'sign-off. Review the sheets before sending anything to vendors; ' +
        'the guideline itself must not be shared externally.';
    const a = document.createElement('a');
    a.className = 'dl';
    a.href = data.download;
    a.textContent = '⬇ ' + data.file;
    note.parentElement.appendChild(a);
    announce('Checklist ready: ' + data.count + ' requirements.');
  } catch (err) {
    note.innerHTML = (err.name === 'AbortError' || ac.signal.aborted)
      ? 'Checklist generation stopped.'
      : '<span class="warn">Checklist generation failed: ' +
        err.message.replace(/</g, '&lt;') + '</span>';
  } finally {
    endTender();
    setBusy(false);
    box.focus();
  }
}

// ---- input plumbing ------------------------------------------------------
function autoresize() {
  box.style.height = 'auto';
  box.style.height = Math.min(box.scrollHeight, 170) + 'px';
}

function submit() {
  const text = box.value.trim();
  if (!text || busy) return;
  box.value = '';
  autoresize();
  if (tender) { tenderInput(text); return; }
  if (text === '/tender') { startTender(); return; }
  chat(text);
}

sendBtn.addEventListener('click', () => { if (busy) stopRequest(); else submit(); });
tenderBtn.addEventListener('click', startTender);
box.addEventListener('input', autoresize);
box.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
  else if (e.key === 'Escape' && busy) { e.preventDefault(); stopRequest(); }
});
</script>
</body>
</html>
"""
