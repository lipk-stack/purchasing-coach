"""Minimal local web UI on the stdlib http.server — no extra packages.

Serves a single-page chat interface for the same Coach used by the CLI:
free-form questions about the guideline plus the tender-checklist wizard.
The server binds to 127.0.0.1 only; generated workbooks are written to the
out dir and offered as downloads.
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
        except Exception as exc:
            self._chunk(f"\n[error: {exc}]".encode("utf-8"))
        self._chunk(b"")  # terminating chunk

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
<title>Purchasing Coach</title>
<style>
  :root { --bg:#f4f5f7; --panel:#fff; --ink:#1c2733; --muted:#69788a;
          --accent:#1f4e78; --accent2:#2e75b6; --me:#e8f0fa; }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
         background:var(--bg); color:var(--ink); display:flex;
         flex-direction:column; height:100vh; }
  header { background:var(--accent); color:#fff; padding:10px 18px;
           display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }
  header h1 { font-size:17px; margin:0; }
  header .meta { font-size:12.5px; opacity:.85; }
  #log { flex:1; overflow-y:auto; padding:18px; }
  .msg { max-width:780px; margin:0 auto 12px; padding:10px 14px;
         border-radius:10px; background:var(--panel); white-space:pre-wrap;
         overflow-wrap:break-word; box-shadow:0 1px 2px rgba(0,0,0,.06); }
  .msg.me { background:var(--me); }
  .msg .who { font-size:11.5px; font-weight:600; color:var(--muted);
              text-transform:uppercase; letter-spacing:.04em;
              margin-bottom:2px; white-space:normal; }
  .msg.sys { background:#fdf6e3; }
  .msg a.dl { display:inline-block; margin-top:6px; padding:7px 14px;
              background:var(--accent2); color:#fff; border-radius:6px;
              text-decoration:none; font-weight:600; }
  footer { padding:12px 18px 16px; }
  .bar { max-width:780px; margin:0 auto; display:flex; gap:8px; }
  textarea { flex:1; resize:none; padding:10px 12px; border-radius:10px;
             border:1px solid #c8d1db; font:inherit; height:46px; }
  textarea:focus { outline:2px solid var(--accent2); border-color:transparent; }
  button { padding:0 18px; border:0; border-radius:10px; font:inherit;
           font-weight:600; cursor:pointer; }
  #send { background:var(--accent); color:#fff; }
  #tender { background:#fff; border:1px solid #c8d1db; color:var(--accent); }
  button:disabled { opacity:.5; cursor:default; }
  .hint { max-width:780px; margin:6px auto 0; font-size:12px;
          color:var(--muted); }
</style>
</head>
<body>
<header>
  <h1>Purchasing Coach</h1>
  <span class="meta" id="meta">connecting…</span>
</header>
<div id="log"></div>
<footer>
  <div class="bar">
    <textarea id="box" placeholder="Ask about the guideline…" autofocus></textarea>
    <button id="send">Send</button>
    <button id="tender">Tender checklist</button>
  </div>
  <div class="hint">Enter to send, Shift+Enter for a new line. “Tender
  checklist” (or typing /tender) starts a short interview and produces an
  Excel checklist from your template.</div>
</footer>
<script>
const log = document.getElementById('log');
const box = document.getElementById('box');
const sendBtn = document.getElementById('send');
const tenderBtn = document.getElementById('tender');
let history = [];           // chat turns sent to the model
let tender = null;          // active interview state, or null
let busy = false;

fetch('/api/meta').then(r => r.json()).then(m => {
  document.getElementById('meta').textContent =
    `${m.guideline} · ${m.backend} (${m.model})`;
}).catch(() => {});

function add(who, cls, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  const tag = document.createElement('div');
  tag.className = 'who';
  tag.textContent = who;
  const body = document.createElement('span');
  body.textContent = text;
  div.append(tag, body);
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return body;
}

function setBusy(b) {
  busy = b;
  sendBtn.disabled = b;
  tenderBtn.disabled = b;
}

add('coach', 'sys',
    'Hello! Ask me anything about the purchasing guideline, or click ' +
    '“Tender checklist” to prepare a tender for something you want to buy.');

async function chat(text) {
  add('you', 'me', text);
  history.push({role: 'user', content: text});
  const body = add('coach', '', '…');
  setBusy(true);
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({messages: history}),
    });
    if (!resp.ok) throw new Error((await resp.json()).error || resp.status);
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let full = '';
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      full += dec.decode(value, {stream: true});
      body.textContent = full;
      log.scrollTop = log.scrollHeight;
    }
    history.push({role: 'assistant', content: full});
  } catch (err) {
    body.textContent = 'Request failed: ' + err.message;
    history.pop();
  } finally {
    setBusy(false);
    box.focus();
  }
}

function startTender() {
  if (busy || tender) return;
  tender = {stage: 'item', item: '', questions: [], answers: []};
  add('coach', 'sys', 'Tender checklist — what do you want to buy? ' +
      'Describe the item or solution in one or two sentences. ' +
      '(Type “cancel” to abort.)');
  box.placeholder = 'e.g. 200 laptops for the sales team';
  box.focus();
}

function askNext() {
  const i = tender.answers.length;
  add('coach', 'sys',
      `[${i + 1}/${tender.questions.length}] ${tender.questions[i].question}`);
}

async function tenderInput(text) {
  if (text.toLowerCase() === 'cancel') {
    tender = null;
    box.placeholder = 'Ask about the guideline…';
    add('coach', 'sys', 'Tender flow cancelled.');
    return;
  }
  add('you', 'me', text);
  if (tender.stage === 'item') {
    tender.item = text;
    tender.stage = 'questions';
    const note = add('coach', 'sys',
                     'Thinking about the right questions for this purchase…');
    setBusy(true);
    try {
      const resp = await fetch('/api/tender/start', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({item: tender.item}),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || resp.status);
      tender.questions = data.questions;
      note.textContent = `I have ${data.questions.length} questions. ` +
                         'Answer briefly; reply “TBC” if you don’t know yet.';
      askNext();
    } catch (err) {
      note.textContent = 'Could not plan the interview: ' + err.message;
      tender = null;
      box.placeholder = 'Ask about the guideline…';
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
  try {
    const resp = await fetch('/api/tender/finish', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({item: tender.item, answers: tender.answers}),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.status);
    note.textContent = `Done — ${data.count} requirements for ` +
        `“${data.tender_info.purchase_item}”. Review both sheets before ` +
        'sending anything to vendors; the guideline itself must not be ' +
        'shared externally.';
    const a = document.createElement('a');
    a.className = 'dl';
    a.href = data.download;
    a.textContent = '⬇ ' + data.file;
    note.parentElement.appendChild(a);
  } catch (err) {
    note.textContent = 'Checklist generation failed: ' + err.message;
  } finally {
    tender = null;
    box.placeholder = 'Ask about the guideline…';
    setBusy(false);
    box.focus();
  }
}

function submit() {
  const text = box.value.trim();
  if (!text || busy) return;
  box.value = '';
  if (tender) { tenderInput(text); return; }
  if (text === '/tender') { startTender(); return; }
  chat(text);
}

sendBtn.addEventListener('click', submit);
tenderBtn.addEventListener('click', startTender);
box.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
});
</script>
</body>
</html>
"""
