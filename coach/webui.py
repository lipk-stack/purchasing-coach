"""Enterprise web UI with multi-backend support, session persistence,
analytics dashboard, interactive checklist viewer, and premium design.

Serves a single-page application for the Purchasing Coach: free-form
questions about the guideline, the tender-checklist wizard, dashboard
analytics, and session management.  The server binds to 127.0.0.1 only;
generated workbooks are written to the out dir and offered as downloads.

The page is one self-contained HTML document (inline CSS + JS, system
fonts, no CDN) so it works on locked-down, offline corporate machines.
"""

import json
import logging
import re
import threading
import uuid
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from .excel import write_checklist
from .llm import Coach
from .models import (
    AnalyticsSnapshot,
    TenderChecklist,
    RequirementRow,
)
from .tender import output_name

SESSIONS_DIR = Path.home() / ".purchasing-coach" / "sessions"

# Session ids are used as filenames, so constrain them to a safe charset to
# prevent path traversal outside SESSIONS_DIR.
_SAFE_SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")

# Cap request bodies so a bogus Content-Length can't exhaust memory.
MAX_BODY_BYTES = 8 * 1024 * 1024

# The server binds to 127.0.0.1, but a malicious web page the user has open can
# still reach it via DNS rebinding (resolving an attacker-controlled hostname to
# 127.0.0.1). Pinning the accepted Host header to loopback names blocks that:
# a rebound request arrives with the attacker's hostname in Host and is rejected.
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", "::1"})

log = logging.getLogger("coach.webui")


class WebUI:
    def __init__(self, coach: Coach, backend, guideline_path: str,
                 template_path=None, out_dir="."):
        self.coach = coach
        self.backend = backend
        self.guideline_path = str(guideline_path)
        self.template_path = template_path
        self.out_dir = Path(out_dir)
        self.generated: set[str] = set()
        self._last_checklist: list[RequirementRow] | None = None
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # -- session persistence --------------------------------------------------
    def _session_path(self, sid: str) -> Path | None:
        """Map a session id to its file, or None if the id is unsafe.

        Session ids come from the URL/JSON body, so they are constrained to a
        safe charset to prevent path traversal (e.g. ``../../etc/foo``) outside
        the sessions directory.
        """
        if not _SAFE_SESSION_ID.match(sid or ""):
            return None
        return SESSIONS_DIR / f"{sid}.json"

    def list_sessions(self) -> list[dict]:
        sessions = []
        for p in sorted(SESSIONS_DIR.glob("*.json"), reverse=True):
            try:
                data = json.loads(p.read_text("utf-8"))
                sessions.append({
                    "id": data.get("id", p.stem),
                    "title": data.get("title", "New session"),
                    "updated_at": data.get("updated_at", ""),
                    "message_count": len(data.get("messages", [])),
                })
            except (json.JSONDecodeError, OSError):
                continue
        return sessions

    def load_session(self, sid: str) -> dict | None:
        p = self._session_path(sid)
        if p is None or not p.exists():
            return None
        try:
            return json.loads(p.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def save_session(self, data: dict) -> str:
        # Honour a caller-supplied id only if it is safe; otherwise mint one.
        sid = data.get("id") or ""
        if not _SAFE_SESSION_ID.match(sid):
            sid = str(uuid.uuid4())[:12]
        data["id"] = sid
        data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        if not data.get("created_at"):
            data["created_at"] = data["updated_at"]
        self._session_path(sid).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        return sid

    def delete_session(self, sid: str) -> bool:
        p = self._session_path(sid)
        if p is not None and p.exists():
            p.unlink()
            return True
        return False

    # -- API operations -------------------------------------------------------
    def meta(self) -> dict:
        return {
            "backend": self.backend.name,
            "model": getattr(self.backend, "model", "N/A"),
            "guideline": Path(self.guideline_path).name,
            "version": __version__,
            "requires_model": getattr(self.backend, "requires_model", True),
        }

    def health(self) -> dict:
        return self.backend.health_check()

    def available_backends(self) -> list[dict]:
        from .backends import list_backends
        return [{"name": b} for b in list_backends() if b != "auto"]

    def analytics(self) -> dict:
        if not self._last_checklist:
            return AnalyticsSnapshot().to_dict()
        return AnalyticsSnapshot.from_checklist(
            self._last_checklist,
            total_clauses=len(self.coach.clauses),
        ).to_dict()

    def tender_start(self, item: str) -> dict:
        plan = self.coach.plan_interview(item)
        return {"questions": [{"key": q.key, "question": q.question}
                              for q in plan.questions]}

    def tender_finish(self, item: str, answers: list) -> dict:
        interview = [(str(q), str(a)) for q, a in answers]
        checklist: TenderChecklist = self.coach.build_checklist(item, interview)
        name = output_name(checklist.tender_info.purchase_item)
        write_checklist(checklist.tender_info, checklist.requirements,
                        self.out_dir / name, self.template_path,
                        interview=interview)
        self.generated.add(name)
        self._last_checklist = checklist.requirements
        return {
            "file": name,
            "download": f"/api/download/{name}",
            "count": len(checklist.requirements),
            "mandatory": sum(1 for r in checklist.requirements
                             if r.mandatory == "M"),
            "unverified": checklist.unverified_refs,
            "added_core": checklist.added_core_sections,
            "tender_info": checklist.tender_info.__dict__,
            "requirements": [
                {"ref": r.ref, "section": r.section,
                 "requirement": r.requirement, "mandatory": r.mandatory}
                for r in checklist.requirements
            ],
        }

    def export_csv(self) -> str:
        if not self._last_checklist:
            return ""
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Ref", "Section", "Requirement", "M/O"])
        for r in self._last_checklist:
            w.writerow([r.ref, r.section, r.requirement, r.mandatory])
        return buf.getvalue()

    def export_json(self) -> list[dict]:
        if not self._last_checklist:
            return []
        return [
            {"ref": r.ref, "section": r.section,
             "requirement": r.requirement, "mandatory": r.mandatory}
            for r in self._last_checklist
        ]

    # -- server ---------------------------------------------------------------
    def serve(self, port: int = 8765, open_browser: bool = True) -> None:
        server = self.make_server(port)
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        print(f"Purchasing Coach v{__version__}  {url}  (Ctrl+C to stop)")
        print(f"  Backend:  {self.backend.name} ({getattr(self.backend, 'model', 'N/A')})")
        print(f"  Guideline: {Path(self.guideline_path).name}")
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
    webui: WebUI
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _host_allowed(self) -> bool:
        """Reject requests whose Host header is not a loopback name.

        Defends against DNS-rebinding: the listening socket is loopback-only,
        but a browser tricked into rebinding an attacker hostname to 127.0.0.1
        would send that hostname here. The port is stripped before comparison.
        """
        host = self.headers.get("Host", "")
        # Strip the port, but not the colons inside a bracketed IPv6 literal.
        if host.startswith("["):
            hostname = host.split("]")[0] + "]"
        else:
            hostname = host.rsplit(":", 1)[0] if ":" in host else host
        return hostname.lower() in _ALLOWED_HOSTS

    def _reject_foreign_host(self) -> bool:
        """Send 403 and return True when the Host header is not loopback."""
        if self._host_allowed():
            return False
        self._json(403, {"error": "forbidden host"})
        return True

    # -- routing --------------------------------------------------------------
    def do_GET(self):
        if self._reject_foreign_host():
            return
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            self._respond(200, "text/html; charset=utf-8", body)
        elif path == "/api/meta":
            self._json(200, self.webui.meta())
        elif path == "/api/health":
            self._json(200, self.webui.health())
        elif path == "/api/backends":
            self._json(200, self.webui.available_backends())
        elif path == "/api/sessions":
            self._json(200, self.webui.list_sessions())
        elif path.startswith("/api/sessions/"):
            sid = path[len("/api/sessions/"):]
            data = self.webui.load_session(sid)
            if data:
                self._json(200, data)
            else:
                self._json(404, {"error": "session not found"})
        elif path == "/api/analytics":
            self._json(200, self.webui.analytics())
        elif path == "/api/export/csv":
            csv_text = self.webui.export_csv()
            self._respond(200, "text/csv; charset=utf-8",
                          csv_text.encode("utf-8"))
        elif path == "/api/export/json":
            self._json(200, self.webui.export_json())
        elif path.startswith("/api/download/"):
            self._download(path[len("/api/download/"):])
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self._reject_foreign_host():
            return
        path = self.path.split("?")[0]
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._json(400, {"error": "invalid Content-Length"})
            return
        if length < 0:
            self._json(400, {"error": "invalid Content-Length"})
            return
        if length > MAX_BODY_BYTES:
            self._json(413, {"error": "request body too large"})
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "invalid JSON body"})
            return
        try:
            if path == "/api/chat":
                self._chat(payload)
            elif path == "/api/tender/start":
                item = str(payload.get("item") or "").strip()
                if not item:
                    self._json(400, {"error": "item description is required"})
                else:
                    self._json(200, self.webui.tender_start(item))
            elif path == "/api/tender/finish":
                item = str(payload.get("item") or "").strip()
                answers = payload.get("answers") or []
                if not item or not isinstance(answers, list):
                    self._json(400, {"error": "item and answers are required"})
                else:
                    self._json(200, self.webui.tender_finish(item, answers))
            elif path == "/api/sessions":
                sid = self.webui.save_session(payload)
                self._json(200, {"id": sid})
            else:
                self._json(404, {"error": "not found"})
        except Exception as exc:
            log.exception("POST %s failed", path)
            self._json(500, {"error": str(exc)})

    def do_DELETE(self):
        if self._reject_foreign_host():
            return
        path = self.path.split("?")[0]
        if path.startswith("/api/sessions/"):
            sid = path[len("/api/sessions/"):]
            ok = self.webui.delete_session(sid)
            self._json(200 if ok else 404, {"ok": ok})
        else:
            self._json(404, {"error": "not found"})

    # -- handlers -------------------------------------------------------------
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
        except BrokenPipeError:
            return
        except Exception as exc:
            log.exception("chat stream failed")
            try:
                self._chunk(f"\n[error: {exc}]".encode())
            except BrokenPipeError:
                return
        try:
            self._chunk(b"")
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

    # -- plumbing -------------------------------------------------------------
    def _respond(self, status: int, ctype: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data):
        self._respond(status, "application/json; charset=utf-8",
                      json.dumps(data, ensure_ascii=False).encode("utf-8"))


# =============================================================================
# SINGLE-PAGE APPLICATION
# =============================================================================
PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>Purchasing Coach</title>
<script>
(function(){
  try{var t=localStorage.getItem('pc-theme');
  if(!t)t=matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';
  document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme='dark';}
})();
</script>
<style>
/* ===== DESIGN TOKENS ===== */
:root{
  --bg-0:#080b0d;--bg-1:#0f1417;--bg-2:#151c20;--bg-3:#1d272c;--bg-4:#263238;
  --panel:#11171b;--panel-2:#172027;--panel-3:#202a31;
  --tx-0:#f2f5f2;--tx-1:#c4ccc4;--tx-2:#8f9b95;--tx-3:#59665f;
  --ac:#21c6a8;--ac-2:#3f7df4;--ac-ink:#05261f;--ac-bg:rgba(33,198,168,.14);
  --green:#35d07f;--green-bg:rgba(53,208,127,.13);
  --amber:#f3b340;--amber-bg:rgba(243,179,64,.13);
  --red:#ff6b6b;--red-bg:rgba(255,107,107,.14);
  --border:rgba(228,238,232,.09);--border-2:rgba(228,238,232,.16);
  --shadow:0 10px 28px rgba(0,0,0,.26);--shadow-lg:0 18px 48px rgba(0,0,0,.36);
  --r-sm:4px;--r-md:6px;--r-lg:8px;--r-xl:8px;
  --sp-1:4px;--sp-2:8px;--sp-3:12px;--sp-4:16px;--sp-5:24px;--sp-6:32px;--sp-7:44px;
  --font:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  --mono:ui-monospace,'SF Mono','Cascadia Code','Fira Code',Consolas,monospace;
  --tr-fast:150ms cubic-bezier(.4,0,.2,1);--tr-norm:250ms cubic-bezier(.4,0,.2,1);
  --sidebar-w:268px;--topbar-h:64px;
}
[data-theme="light"]{
  --bg-0:#eef2f0;--bg-1:#f7f9f8;--bg-2:#ffffff;--bg-3:#edf2f0;--bg-4:#dce5e1;
  --panel:#ffffff;--panel-2:#f6f8f7;--panel-3:#eaf0ed;
  --tx-0:#17211c;--tx-1:#3d4a44;--tx-2:#65726c;--tx-3:#9aa8a1;
  --ac:#087f6c;--ac-2:#2e66d2;--ac-ink:#f4fffb;--ac-bg:rgba(8,127,108,.1);
  --green:#087a47;--green-bg:rgba(8,122,71,.1);
  --amber:#a65f00;--amber-bg:rgba(166,95,0,.1);
  --red:#c73535;--red-bg:rgba(199,53,53,.1);
  --border:rgba(16,31,24,.09);--border-2:rgba(16,31,24,.16);
  --shadow:0 10px 24px rgba(23,33,28,.08);--shadow-lg:0 18px 48px rgba(23,33,28,.12);
}
/* ===== RESET & BASE ===== */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
html,body{height:100%;overflow:hidden;}
body{font:14px/1.6 var(--font);color:var(--tx-0);background:var(--bg-0);
  -webkit-font-smoothing:antialiased;display:flex;flex-direction:column;}
button{font:inherit;cursor:pointer;border:0;background:0;color:inherit;}
input,textarea,select{font:inherit;color:inherit;background:0;border:0;outline:0;}
a{color:var(--ac);text-decoration:none;}
/* Visible keyboard focus for every interactive element (WCAG 2.4.7/2.4.11) */
:focus-visible{outline:2px solid var(--ac);outline-offset:2px;}
a:focus-visible,button:focus-visible,[tabindex]:focus-visible,input:focus-visible,
textarea:focus-visible,select:focus-visible,[contenteditable=true]:focus-visible{
  outline:2px solid var(--ac);outline-offset:2px;border-radius:var(--r-sm);}
/* Skip-to-content link, revealed on keyboard focus (WCAG 2.4.1) */
.skip-link{position:absolute;left:var(--sp-3);top:-100px;z-index:100;background:var(--ac);
  color:#fff;padding:var(--sp-2) var(--sp-4);border-radius:var(--r-md);font-weight:600;
  box-shadow:var(--shadow-lg);transition:top var(--tr-fast);}
.skip-link:focus{top:var(--sp-3);}
::-webkit-scrollbar{width:6px;height:6px;}
::-webkit-scrollbar-track{background:0 0;}
::-webkit-scrollbar-thumb{background:var(--border-2);border-radius:3px;}
::-webkit-scrollbar-thumb:hover{background:var(--tx-3);}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;
  overflow:hidden;clip:rect(0,0,0,0);border:0;}
/* ===== LAYOUT ===== */
.app{display:flex;flex:1;overflow:hidden;background:
  linear-gradient(180deg,var(--bg-0) 0%,var(--bg-1) 100%);}
.sidebar{width:var(--sidebar-w);background:var(--panel);border-right:1px solid var(--border);
  display:flex;flex-direction:column;transition:width var(--tr-norm);flex-shrink:0;overflow:hidden;z-index:10;}
.sidebar.collapsed{width:68px;}
.sidebar.collapsed .nav-label,.sidebar.collapsed .session-list,.sidebar.collapsed .sidebar-header span{display:none;}
.sidebar.collapsed .sidebar-header{justify-content:center;}
.sidebar.collapsed .nav-item{justify-content:center;padding:var(--sp-3);width:44px;margin:4px auto;}
.main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0;}
/* ===== TOPBAR ===== */
.topbar{height:var(--topbar-h);background:color-mix(in srgb,var(--panel) 86%,transparent);
  border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 var(--sp-5);
  gap:var(--sp-3);flex-shrink:0;}
.topbar .menu-btn{width:40px;height:40px;border-radius:var(--r-md);display:grid;place-items:center;
  font-size:18px;transition:background var(--tr-fast),transform var(--tr-fast);}
.topbar .menu-btn:hover{background:var(--bg-3);}
.topbar .menu-btn:active{transform:translateY(1px);}
.topbar .brand{display:flex;align-items:center;gap:var(--sp-3);font-weight:750;font-size:15px;}
.topbar .brand .logo,.brand-mark{width:34px;height:34px;border-radius:var(--r-md);
  background:linear-gradient(135deg,var(--ac) 0%,var(--ac-2) 100%);color:#fff;
  display:grid;place-items:center;font-size:13px;font-weight:850;letter-spacing:.04em;}
.brand-stack{display:flex;flex-direction:column;line-height:1.15;}
.brand-stack small{color:var(--tx-2);font-size:11px;font-weight:600;letter-spacing:.02em;}
.pill{display:inline-flex;align-items:center;gap:var(--sp-1);padding:3px 10px;
  border-radius:999px;font-size:11px;font-weight:700;letter-spacing:.02em;border:1px solid transparent;}
.pill.ok{background:var(--green-bg);color:var(--green);}
.pill.err{background:var(--red-bg);color:var(--red);}
.pill.info{background:var(--ac-bg);color:var(--ac);}
.pill .dot{width:6px;height:6px;border-radius:50%;background:currentColor;}
#guidelinePill{max-width:360px;}
#guidelineLabel{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.topbar .spacer{flex:1;}
/* ===== SIDEBAR NAV ===== */
.sidebar-header{padding:var(--sp-5) var(--sp-4) var(--sp-4);display:flex;align-items:center;gap:var(--sp-3);
  font-weight:800;font-size:12px;color:var(--tx-1);text-transform:uppercase;letter-spacing:.08em;}
.nav-item{display:flex;align-items:center;gap:var(--sp-3);padding:var(--sp-3) var(--sp-4);
  margin:4px var(--sp-3);width:calc(100% - 24px);text-align:left;border-radius:var(--r-md);
  color:var(--tx-1);font-size:13px;font-weight:700;transition:all var(--tr-fast);cursor:pointer;
  min-height:44px;border:1px solid transparent;}
.nav-item:hover{background:var(--bg-3);color:var(--tx-0);}
.nav-item.active,.nav-item[aria-current=page]{background:var(--ac-bg);color:var(--ac);border-color:color-mix(in srgb,var(--ac) 30%,transparent);}
.nav-item .icon{width:22px;text-align:center;font-size:15px;flex-shrink:0;}
.session-list{flex:1;overflow-y:auto;padding:var(--sp-3) 0;border-top:1px solid var(--border);margin-top:var(--sp-3);}
.session-item{display:flex;align-items:center;gap:var(--sp-2);padding:var(--sp-1) var(--sp-3);
  margin:1px var(--sp-2);width:calc(100% - var(--sp-4));text-align:left;border-radius:var(--r-sm);
  color:var(--tx-2);font-size:12px;cursor:pointer;transition:background var(--tr-fast);}
.session-item:hover{background:var(--bg-3);color:var(--tx-0);}
.session-open{flex:1;display:flex;align-items:center;gap:var(--sp-2);color:inherit;
  font-size:12px;text-align:left;overflow:hidden;padding:var(--sp-2) 0;border-radius:var(--r-sm);min-width:0;min-height:36px;}
.session-item .title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.session-item .count{font-size:10px;color:var(--tx-2);flex-shrink:0;}
.session-item .del{opacity:0;font-size:16px;color:var(--red);transition:opacity var(--tr-fast);
  width:32px;height:32px;border-radius:var(--r-sm);display:grid;place-items:center;flex-shrink:0;}
.session-item:hover .del,.session-item:focus-within .del,.session-item .del:focus-visible{opacity:1;}
/* ===== CONTENT VIEWS ===== */
.view{display:none;flex:1;overflow-y:auto;padding:var(--sp-6);}
.view.active{display:flex;flex-direction:column;}
.view-head{display:flex;align-items:flex-end;justify-content:space-between;gap:var(--sp-4);margin-bottom:var(--sp-5);}
.view-title{font-size:28px;font-weight:850;letter-spacing:-.02em;color:var(--tx-0);line-height:1.05;margin:0;}
.view-subtitle{max-width:760px;color:var(--tx-2);font-size:14px;margin-top:var(--sp-2);}
.view-actions{display:flex;gap:var(--sp-2);flex-wrap:wrap;align-items:center;}
/* ===== DASHBOARD ===== */
.dashboard-hero{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(280px,.8fr);gap:var(--sp-4);
  align-items:stretch;margin-bottom:var(--sp-5);}
.hero-panel{background:linear-gradient(135deg,var(--panel) 0%,var(--panel-2) 58%,color-mix(in srgb,var(--ac) 18%,var(--panel)) 100%);
  border:1px solid var(--border);border-radius:var(--r-lg);padding:var(--sp-6);
  box-shadow:var(--shadow);position:relative;overflow:hidden;}
.hero-panel::after{content:"";position:absolute;left:0;right:0;bottom:0;height:4px;
  background:linear-gradient(90deg,var(--ac),var(--amber),var(--ac-2));}
.kicker{display:inline-flex;align-items:center;gap:var(--sp-2);font-size:11px;font-weight:850;
  letter-spacing:.12em;text-transform:uppercase;color:var(--ac);margin-bottom:var(--sp-3);}
.hero-panel h3{font-size:32px;line-height:1.05;letter-spacing:-.03em;max-width:760px;margin:0 0 var(--sp-3);}
.hero-panel p{max-width:760px;color:var(--tx-1);font-size:15px;margin-bottom:var(--sp-5);}
.quick-grid{display:grid;grid-template-columns:1fr;gap:var(--sp-3);}
.quick-card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r-lg);
  padding:var(--sp-4);display:flex;flex-direction:column;justify-content:space-between;gap:var(--sp-3);min-height:126px;}
.quick-card strong{font-size:14px;color:var(--tx-0);}
.quick-card span{font-size:12px;color:var(--tx-2);}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:var(--sp-3);margin-bottom:var(--sp-5);}
.metric-card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r-lg);
  padding:var(--sp-4);display:flex;flex-direction:column;gap:var(--sp-1);min-height:118px;}
.metric-card .label{font-size:11px;font-weight:800;color:var(--tx-2);text-transform:uppercase;letter-spacing:.08em;}
.metric-card .value{font-size:34px;font-weight:850;color:var(--tx-0);line-height:1.05;letter-spacing:-.03em;}
.metric-card .sub{font-size:12px;color:var(--tx-2);}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-4);}
.chart-card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r-lg);padding:var(--sp-5);}
.chart-card h3{font-size:14px;font-weight:750;color:var(--tx-1);margin-bottom:var(--sp-3);}
.chart-card canvas{width:100%;max-height:260px;}
.empty-state{text-align:center;padding:var(--sp-7);color:var(--tx-2);font-size:14px;background:var(--panel);
  border:1px dashed var(--border-2);border-radius:var(--r-lg);margin-top:var(--sp-4);}
.empty-state .icon{font-size:42px;margin-bottom:var(--sp-3);opacity:.55;}
.empty-state p{margin:0 auto var(--sp-4);max-width:520px;}
/* ===== CHAT ===== */
.chat-view{padding:0 !important;display:none;flex-direction:column;overflow:hidden;}
.chat-view.active{display:flex;}
.chat-log{flex:1;overflow-y:auto;padding:var(--sp-5);scroll-behavior:smooth;}
.chat-start,.chat-thread{max-width:920px;margin:0 auto;}
.chat-start{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:var(--sp-4);align-items:center;
  padding:var(--sp-5);border:1px solid var(--border);border-radius:var(--r-lg);background:var(--panel);
  margin-bottom:var(--sp-4);}
.chat-start h2{font-size:24px;line-height:1.1;letter-spacing:-.02em;margin:0 0 var(--sp-2);}
.chat-start p{color:var(--tx-2);margin:0;max-width:640px;}
.chat-thread{display:flex;flex-direction:column;gap:var(--sp-3);}
.msg{padding:var(--sp-4);border-radius:var(--r-lg);background:var(--panel);
  border:1px solid var(--border);max-width:86%;overflow-wrap:anywhere;box-shadow:0 1px 0 rgba(255,255,255,.02);}
.msg.me{background:var(--ac-bg);border-color:color-mix(in srgb,var(--ac) 28%,transparent);align-self:flex-end;}
.msg.sys{background:var(--amber-bg);border-color:color-mix(in srgb,var(--amber) 26%,transparent);}
.msg .who{display:flex;align-items:center;gap:var(--sp-2);margin-bottom:var(--sp-1);}
.msg .av{width:26px;height:26px;border-radius:var(--r-md);display:grid;place-items:center;
  font-size:11px;font-weight:700;color:#fff;background:var(--ac);flex-shrink:0;}
.msg.me .av{background:var(--ac-2);}
.msg.sys .av{background:var(--amber);color:var(--bg-0);}
.msg .name{font-size:11px;font-weight:700;color:var(--tx-2);text-transform:uppercase;letter-spacing:.04em;}
.msg .copy{margin-left:auto;border:0;background:transparent;color:var(--tx-2);
  cursor:pointer;font-size:11px;padding:2px 8px;border-radius:var(--r-sm);transition:all var(--tr-fast);}
.msg .copy:hover{background:var(--bg-3);color:var(--tx-0);}
.msg .body{font-size:14px;line-height:1.6;}
.msg .body.md{white-space:normal;}
.msg .body.streaming::after{content:"";display:inline-block;width:2px;height:1em;
  background:var(--ac);margin-left:2px;animation:blink .8s steps(2) infinite;vertical-align:text-bottom;}
@keyframes blink{50%{opacity:0;}}
.msg .toolbar{display:flex;gap:var(--sp-1);margin-top:var(--sp-2);opacity:0;transition:opacity var(--tr-fast);}
.msg:hover .toolbar{opacity:1;}
.msg .toolbar button{padding:2px 8px;border-radius:var(--r-sm);font-size:11px;color:var(--tx-2);transition:all var(--tr-fast);}
.msg .toolbar button:hover{background:var(--bg-3);color:var(--tx-0);}
/* Markdown in messages */
.md p{margin:0 0 8px;}.md p:last-child{margin:0;}
.md ul,.md ol{margin:0 0 8px;padding-left:20px;}.md li{margin:2px 0;}
.md .h{font-weight:700;color:var(--ac);margin:10px 0 4px;font-size:14px;}
.md code{background:var(--bg-3);border-radius:4px;padding:1px 5px;font:12px/1.4 var(--mono);}
.md pre{background:var(--bg-3);border:1px solid var(--border);border-radius:var(--r-md);
  padding:var(--sp-3);overflow-x:auto;margin:0 0 8px;font:12px/1.5 var(--mono);}
.md table{border-collapse:collapse;margin:4px 0 8px;font-size:13px;display:block;overflow-x:auto;}
.md th,.md td{border:1px solid var(--border);padding:5px 10px;text-align:left;vertical-align:top;}
.md th{background:var(--ac);color:#fff;font-weight:600;}
.md tr:nth-child(even) td{background:var(--bg-3);}
a.dl{display:inline-flex;align-items:center;gap:var(--sp-2);margin-top:var(--sp-2);
  padding:var(--sp-2) var(--sp-4);background:var(--ac);color:#fff;border-radius:var(--r-md);
  font-weight:600;font-size:13px;box-shadow:var(--shadow);transition:background var(--tr-fast);}
a.dl:hover{background:var(--ac-2);}
.warn{color:var(--red);font-weight:600;}
.stopnote{color:var(--tx-2);font-size:12px;margin-top:var(--sp-1);font-style:italic;}
/* Chat input */
.chat-footer{padding:var(--sp-4) var(--sp-5) calc(var(--sp-4) + env(safe-area-inset-bottom));
  background:var(--panel);border-top:1px solid var(--border);}
.chat-bar{max-width:920px;margin:0 auto;display:flex;gap:var(--sp-3);align-items:flex-end;}
.chat-bar textarea{flex:1;resize:none;padding:var(--sp-3) var(--sp-4);border-radius:var(--r-lg);
  border:1px solid var(--border);background:var(--bg-2);color:var(--tx-0);
  min-height:48px;max-height:160px;overflow-y:auto;transition:border-color var(--tr-fast),box-shadow var(--tr-fast);}
.chat-bar textarea:focus{border-color:var(--ac);outline:none;}
.chat-bar .btns{display:flex;gap:var(--sp-2);}
.btn{font:inherit;font-weight:600;cursor:pointer;border-radius:var(--r-md);
  min-height:44px;padding:0 var(--sp-4);border:1px solid transparent;
  transition:all var(--tr-fast);font-size:13px;display:inline-flex;align-items:center;justify-content:center;gap:var(--sp-2);}
.btn:active{transform:translateY(1px);}
.btn-primary{background:var(--ac);color:var(--ac-ink);}
.btn-primary:hover{background:var(--ac-2);}
.btn-primary.stop{background:var(--red);}
.btn-ghost{background:var(--bg-2);color:var(--tx-1);border-color:var(--border);}
.btn-ghost:hover{border-color:var(--ac);color:var(--ac);}
.btn-line{background:transparent;border-color:var(--border-2);color:var(--tx-1);}
.btn-line:hover{background:var(--bg-3);color:var(--tx-0);}
.btn:disabled{opacity:.45;cursor:default;transform:none;}
.chat-hint{max-width:820px;margin:var(--sp-1) auto 0;font-size:11px;color:var(--tx-2);text-align:center;}
.chat-hint kbd{font:11px/1 var(--mono);background:var(--bg-3);border:1px solid var(--border-2);
  border-radius:4px;padding:1px 5px;color:var(--tx-1);}
/* Interview progress */
.interview-progress{max-width:820px;margin:0 auto var(--sp-3);padding:var(--sp-3) 0;display:none;}
.interview-progress.active{display:block;}
.progress-bar{display:flex;align-items:center;gap:0;overflow-x:auto;padding:0 var(--sp-2);}
.progress-step{display:flex;flex-direction:column;align-items:center;gap:2px;min-width:32px;}
.progress-step .dot{width:10px;height:10px;border-radius:50%;background:var(--bg-4);
  border:2px solid var(--border-2);transition:all var(--tr-fast);}
.progress-step.done .dot{background:var(--green);border-color:var(--green);}
.progress-step.current .dot{background:var(--ac);border-color:var(--ac);animation:pulse 1.5s ease-in-out infinite;}
.progress-step .num{font-size:9px;color:var(--tx-2);}
.progress-line{flex:1;height:2px;background:var(--border);min-width:8px;}
.progress-line.done{background:var(--green);}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(79,143,247,.4);}50%{box-shadow:0 0 0 6px rgba(79,143,247,0);}}
/* ===== CHECKLIST VIEWER ===== */
.checklist-view{padding:0 !important;overflow:hidden;}
.cl-toolbar{display:flex;gap:var(--sp-3);padding:var(--sp-4) var(--sp-5);
  border-bottom:1px solid var(--border);flex-wrap:wrap;align-items:center;flex-shrink:0;background:var(--panel);}
.cl-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:var(--sp-4);
  padding:var(--sp-6) var(--sp-5) var(--sp-4);background:var(--bg-1);border-bottom:1px solid var(--border);}
.cl-toolbar select,.cl-toolbar input[type=text]{padding:var(--sp-2) var(--sp-3);
  border-radius:var(--r-md);border:1px solid var(--border);background:var(--bg-2);
  color:var(--tx-0);font-size:13px;min-width:160px;min-height:40px;}
.cl-toolbar select:focus,.cl-toolbar input[type=text]:focus{border-color:var(--ac);outline:none;}
.cl-table-wrap{flex:1;overflow:auto;}
.cl-table{width:100%;border-collapse:collapse;font-size:13px;}
.cl-table th{position:sticky;top:0;background:var(--bg-1);border-bottom:2px solid var(--border-2);
  padding:var(--sp-2) var(--sp-3);text-align:left;font-weight:700;font-size:11px;
  text-transform:uppercase;letter-spacing:.04em;color:var(--tx-2);z-index:2;white-space:nowrap;}
.cl-table td{padding:var(--sp-2) var(--sp-3);border-bottom:1px solid var(--border);
  vertical-align:top;max-width:500px;}
.cl-table tr:hover td{background:var(--bg-3);}
.cl-table .badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;}
.cl-table .badge.m{background:var(--red-bg);color:var(--red);}
.cl-table .badge.o{background:var(--green-bg);color:var(--green);}
.cl-table .drag-handle{cursor:grab;color:var(--tx-2);user-select:none;font-size:14px;
  padding:2px 6px;border-radius:var(--r-sm);line-height:1;}
.cl-table .drag-handle:hover{background:var(--bg-4);color:var(--tx-0);}
.cl-table .drag-handle:active{cursor:grabbing;}
.cl-table [contenteditable=true]{outline:1px solid var(--ac);border-radius:3px;padding:1px 3px;background:var(--ac-bg);}
/* ===== SETTINGS ===== */
.settings-grid{display:grid;gap:var(--sp-4);max-width:760px;}
.setting-group{background:var(--panel);border:1px solid var(--border);border-radius:var(--r-lg);padding:var(--sp-5);}
.setting-group h3{font-size:14px;font-weight:700;margin-bottom:var(--sp-3);color:var(--tx-0);}
.setting-row{display:flex;align-items:center;gap:var(--sp-3);margin-bottom:var(--sp-3);}
.setting-row:last-child{margin-bottom:0;}
.setting-row label{font-size:13px;color:var(--tx-1);min-width:120px;}
.setting-row select,.setting-row input{padding:var(--sp-2) var(--sp-3);border-radius:var(--r-sm);
  border:1px solid var(--border);background:var(--bg-3);color:var(--tx-0);font-size:13px;flex:1;max-width:300px;}
.setting-row select:focus,.setting-row input:focus{border-color:var(--ac);outline:none;}
/* ===== RESPONSIVE ===== */
@media(max-width:768px){
  .sidebar{position:fixed;left:0;top:0;bottom:0;z-index:20;box-shadow:var(--shadow-lg);}
  .sidebar.collapsed{width:0;border:0;}
  .view{padding:var(--sp-4);}
  .view-head,.dashboard-hero,.chat-start{grid-template-columns:1fr;align-items:start;}
  .view-head,.cl-heading{flex-direction:column;align-items:flex-start;}
  .charts{grid-template-columns:1fr;}
  .metrics{grid-template-columns:1fr 1fr;}
  .topbar{padding:0 var(--sp-3);}
  .topbar .brand .brand-stack{display:none;}
  #guidelinePill{display:none;}
}
@media(max-width:480px){
  .metrics{grid-template-columns:1fr;}
  .chat-bar .btns{flex-direction:column;}
  .chat-bar{flex-direction:column;align-items:stretch;}
  .msg{max-width:100%;}
  .hero-panel h3{font-size:26px;}
}
@media(prefers-reduced-motion:reduce){
  *{scroll-behavior:auto!important;animation:none!important;transition:none!important;}
}
/* Honour OS high-contrast requests (WCAG 1.4.6/1.4.11) */
@media(prefers-contrast:more){
  :root{--border:rgba(255,255,255,.3);--border-2:rgba(255,255,255,.45);
    --tx-1:#d7dceb;--tx-2:#aeb6cc;}
  [data-theme="light"]{--border:rgba(0,0,0,.3);--border-2:rgba(0,0,0,.45);
    --tx-1:#2a3050;--tx-2:#3f476a;}
  .msg,.metric-card,.chart-card,.setting-group,.hero-panel,.quick-card{border-width:1px;}
}
/* Windows High Contrast / forced-colors: keep focus + active state visible */
@media(forced-colors:active){
  :focus-visible{outline:2px solid Highlight;}
  .nav-item[aria-current=page],.nav-item.active{outline:1px solid Highlight;}
  .pill,.badge{border:1px solid currentColor;}
}
</style>
</head>
<body>
<a class="skip-link" href="#main">Skip to main content</a>
<h1 class="sr-only">Purchasing Coach — IT procurement assistant</h1>
<div class="app">
<!-- SIDEBAR -->
<aside class="sidebar" id="sidebar" aria-label="Sidebar">
  <div class="sidebar-header">
    <div class="brand-mark" aria-hidden="true">PC</div>
    <span>Purchasing Coach</span>
  </div>
  <nav aria-label="Primary">
    <button type="button" class="nav-item active" data-view="dashboard" aria-current="page" onclick="switchView('dashboard')">
      <span class="icon" aria-hidden="true">&#9636;</span><span class="nav-label">Overview</span>
    </button>
    <button type="button" class="nav-item" data-view="chat" onclick="switchView('chat')">
      <span class="icon" aria-hidden="true">&#128172;</span><span class="nav-label">Chat</span>
    </button>
    <button type="button" class="nav-item" data-view="checklist" onclick="switchView('checklist')">
      <span class="icon" aria-hidden="true">&#9745;</span><span class="nav-label">Checklist</span>
    </button>
    <button type="button" class="nav-item" data-view="settings" onclick="switchView('settings')">
      <span class="icon" aria-hidden="true">&#9881;</span><span class="nav-label">Settings</span>
    </button>
  </nav>
  <nav class="session-list" id="sessionList" aria-label="Saved sessions"></nav>
</aside>
<!-- MAIN -->
<main class="main" id="main" tabindex="-1">
  <!-- TOPBAR -->
  <header class="topbar">
    <button type="button" class="menu-btn" onclick="toggleSidebar()" id="menuBtn"
            aria-label="Collapse sidebar" aria-expanded="true" aria-controls="sidebar">&#9776;</button>
    <div class="brand">
      <span class="logo" aria-hidden="true">PC</span>
      <span class="brand-stack"><span>Purchasing Coach</span><small>Procurement compliance workbench</small></span>
    </div>
    <span class="pill ok" id="backendPill" title="AI backend status"><span class="dot" aria-hidden="true"></span><span id="backendLabel">connecting</span></span>
    <span class="pill info" id="guidelinePill" title="Loaded guideline"><span class="dot" aria-hidden="true"></span><span id="guidelineLabel">...</span></span>
    <span class="spacer"></span>
    <button type="button" class="menu-btn" onclick="toggleTheme()" id="themeBtn"
            aria-label="Switch to light theme" aria-pressed="false">&#9790;</button>
  </header>
  <!-- DASHBOARD -->
  <div class="view active" id="view-dashboard" role="region" aria-label="Dashboard">
    <div class="view-head">
      <div>
        <h2 class="view-title">Procurement cockpit</h2>
        <p class="view-subtitle">Generate guideline-grounded tender checklists, review coverage, and keep procurement decisions auditable from one local workspace.</p>
      </div>
      <div class="view-actions">
        <button type="button" class="btn btn-primary" onclick="switchView('chat');startTender()">Start checklist</button>
        <button type="button" class="btn btn-line" onclick="switchView('chat')">Ask guideline</button>
      </div>
    </div>
    <div class="dashboard-hero">
      <section class="hero-panel" aria-labelledby="heroTitle">
        <div class="kicker"><span aria-hidden="true">&#10003;</span> Local, auditable, vendor-ready</div>
        <h3 id="heroTitle">Turn purchasing policy into an actionable tender tracker.</h3>
        <p>Interview the buyer, pull in the right clauses, and export a workbook with vendor responses and approval checks ready for review.</p>
        <div class="view-actions">
          <button type="button" class="btn btn-primary" onclick="switchView('chat');startTender()">Build tender checklist</button>
          <button type="button" class="btn btn-line" onclick="switchView('settings')">Review setup</button>
        </div>
      </section>
      <aside class="quick-grid" aria-label="Quick actions">
        <div class="quick-card">
          <div><strong>Guideline chat</strong><br><span>Ask clause-specific procurement questions with citations.</span></div>
          <button type="button" class="btn btn-ghost" onclick="switchView('chat')">Open chat</button>
        </div>
        <div class="quick-card">
          <div><strong>Checklist review</strong><br><span>Filter, reorder, export, and audit requirements after generation.</span></div>
          <button type="button" class="btn btn-ghost" onclick="switchView('checklist')">Open checklist</button>
        </div>
      </aside>
    </div>
    <div class="metrics" id="metricsGrid">
      <div class="metric-card"><span class="label">Total Requirements</span><span class="value" id="mTotal">0</span><span class="sub">across all sections</span></div>
      <div class="metric-card"><span class="label">Mandatory</span><span class="value" id="mMand" style="color:var(--red)">0</span><span class="sub">must comply</span></div>
      <div class="metric-card"><span class="label">Optional</span><span class="value" id="mOpt" style="color:var(--green)">0</span><span class="sub">recommended</span></div>
      <div class="metric-card"><span class="label">Coverage</span><span class="value" id="mCov">0%</span><span class="sub">guideline sections</span></div>
    </div>
    <div class="charts">
      <div class="chart-card"><h3 id="pieTitle">Mandatory vs Optional</h3><canvas id="pieChart" height="220" role="img" aria-labelledby="pieTitle" aria-describedby="pieDesc"></canvas><p id="pieDesc" class="sr-only"></p></div>
      <div class="chart-card"><h3 id="barTitle">Requirements by Section</h3><canvas id="barChart" height="220" role="img" aria-labelledby="barTitle" aria-describedby="barDesc"></canvas><p id="barDesc" class="sr-only"></p></div>
    </div>
    <div class="empty-state" id="dashEmpty" style="display:none">
      <div class="icon">&#128203;</div>
      <p>No checklist generated yet. Start with a tender interview, then this dashboard will show mandatory coverage, optional items, and section distribution.</p>
      <button type="button" class="btn btn-primary" onclick="switchView('chat');startTender()">Start tender interview</button>
    </div>
  </div>
  <!-- CHAT -->
  <div class="view chat-view" id="view-chat" role="region" aria-label="Chat">
    <div class="chat-log" id="chatLog" role="log" aria-live="polite" aria-label="Conversation" tabindex="0">
      <div class="interview-progress" id="interviewProgress"></div>
      <section class="chat-start" aria-labelledby="chatStartTitle">
        <div>
          <div class="kicker"><span aria-hidden="true">&#9679;</span> Guideline assistant</div>
          <h2 id="chatStartTitle">Ask a question or start a tender interview.</h2>
          <p>Use natural language for clause lookups, or run the guided checklist flow when you are ready to prepare a vendor-facing workbook.</p>
        </div>
        <button type="button" class="btn btn-primary" onclick="startTender()">Tender Checklist</button>
      </section>
      <div class="chat-thread" id="chatThread"></div>
    </div>
    <div class="chat-footer">
      <div class="chat-bar">
        <label for="chatBox" class="sr-only">Ask about the guideline or type a command</label>
        <textarea id="chatBox" rows="1" autofocus placeholder="Ask about the guideline..."></textarea>
        <div class="btns">
          <button type="button" class="btn btn-primary" id="sendBtn" onclick="handleSend()">Send</button>
          <button type="button" class="btn btn-ghost" id="tenderBtn" onclick="startTender()">Tender Checklist</button>
        </div>
      </div>
      <div class="chat-hint"><kbd>Enter</kbd> to send &middot; <kbd>Shift</kbd>+<kbd>Enter</kbd> new line &middot; <kbd>Esc</kbd> stops reply &middot; <kbd>/tender</kbd> starts interview</div>
    </div>
  </div>
  <!-- CHECKLIST -->
  <div class="view checklist-view" id="view-checklist" role="region" aria-label="Checklist">
    <div class="cl-heading">
      <div>
        <h2 class="view-title">Checklist review</h2>
        <p class="view-subtitle">Search, filter, reorder, and export generated requirements before handing the workbook to vendors.</p>
      </div>
      <button type="button" class="btn btn-primary" onclick="switchView('chat');startTender()">New checklist</button>
    </div>
    <div class="cl-toolbar" role="search">
      <label for="clSearch" class="sr-only">Search requirements</label>
      <input type="text" id="clSearch" placeholder="Search requirements..." oninput="filterChecklist()">
      <label for="clSection" class="sr-only">Filter by section</label>
      <select id="clSection" onchange="filterChecklist()"><option value="">All Sections</option></select>
      <label for="clMO" class="sr-only">Filter by mandatory or optional</label>
      <select id="clMO" onchange="filterChecklist()">
        <option value="">M &amp; O</option><option value="M">Mandatory</option><option value="O">Optional</option>
      </select>
      <span style="flex:1"></span>
      <button type="button" class="btn btn-ghost" onclick="exportCSV()"><span aria-hidden="true">&#8681;</span> CSV</button>
      <button type="button" class="btn btn-ghost" onclick="exportJSON()"><span aria-hidden="true">&#8681;</span> JSON</button>
      <span id="clCount" role="status" aria-live="polite" style="font-size:12px;color:var(--tx-2)"></span>
    </div>
    <div class="cl-table-wrap">
      <table class="cl-table" id="clTable">
        <caption class="sr-only">Editable tender requirements. Use the reorder button in each row, then arrow keys, to change order.</caption>
        <thead><tr>
          <th style="width:36px"><span class="sr-only">Reorder</span></th><th>Ref</th><th>Section</th>
          <th>Requirement</th><th scope="col">M/O</th>
        </tr></thead>
        <tbody id="clBody"></tbody>
      </table>
      <div class="empty-state" id="clEmpty">
        <div class="icon">&#128203;</div>
        <p>No checklist generated yet. Generate one through the guided chat flow, then return here to inspect every requirement.</p>
        <button type="button" class="btn btn-primary" onclick="switchView('chat');startTender()">Generate checklist</button>
      </div>
    </div>
  </div>
  <!-- SETTINGS -->
  <div class="view" id="view-settings" role="region" aria-label="Settings">
    <div class="view-head">
      <div>
        <h2 class="view-title">Runtime settings</h2>
        <p class="view-subtitle">Confirm the active backend, loaded guideline, available models, and local operating mode before procurement work begins.</p>
      </div>
    </div>
    <div class="settings-grid">
      <div class="setting-group">
        <h3>Backend</h3>
        <div class="setting-row">
          <label>Active backend</label>
          <span id="setBackend" style="font-weight:600;color:var(--ac)"></span>
        </div>
        <div class="setting-row">
          <label>Model</label>
          <span id="setModel" style="color:var(--tx-1)"></span>
        </div>
        <div class="setting-row">
          <label>Requires model</label>
          <span id="setReqModel" style="color:var(--tx-1)"></span>
        </div>
      </div>
      <div class="setting-group">
        <h3>Guideline</h3>
        <div class="setting-row">
          <label>Document</label>
          <span id="setGuideline" style="color:var(--tx-1)"></span>
        </div>
      </div>
      <div class="setting-group">
        <h3>Available Backends</h3>
        <div id="setBackendList" style="font-size:13px;color:var(--tx-1);line-height:2"></div>
      </div>
      <div class="setting-group">
        <h3>About</h3>
        <div style="font-size:13px;color:var(--tx-1);line-height:1.8">
          <p>Purchasing Coach <span id="aboutVersion">v2.1</span> &mdash; An AI-powered procurement assistant that works with
          LLM backends (local or cloud) and built-in retrieval backends (keyword, BM25, template)
          for zero-dependency operation.</p>
          <p style="margin-top:8px">Supports any OpenAI-compatible API: OpenAI, Groq, Together AI,
          Google Gemini, LM Studio, Ollama, vLLM, and more.</p>
        </div>
      </div>
    </div>
  </div>
</main>
</div>
<div id="sr" class="sr-only" role="status" aria-live="assertive"></div>

<script>
/* ===== STATE ===== */
const S={
  view:'dashboard',sidebarOpen:true,theme:'dark',
  backend:{name:'',model:'',requires_model:true},
  guideline:'',history:[],tender:null,busy:false,aborter:null,
  checklist:null,sessions:[],currentSession:null,
};

/* ===== THEME ===== */
function applyThemeBtn(){
  const b=document.getElementById('themeBtn');
  b.textContent=S.theme==='dark'?'\u2600':'\u263E';
  b.setAttribute('aria-pressed',String(S.theme==='light'));
  b.setAttribute('aria-label',S.theme==='dark'?'Switch to light theme':'Switch to dark theme');
}
function initTheme(){
  S.theme=document.documentElement.dataset.theme||'dark';
  applyThemeBtn();
}
function toggleTheme(){
  S.theme=S.theme==='dark'?'light':'dark';
  document.documentElement.dataset.theme=S.theme;
  try{localStorage.setItem('pc-theme',S.theme);}catch(e){}
  applyThemeBtn();
  announce(S.theme==='dark'?'Dark theme':'Light theme');
  redrawCharts();
}

/* ===== SIDEBAR ===== */
function setSidebar(open){
  S.sidebarOpen=open;
  document.getElementById('sidebar').classList.toggle('collapsed',!open);
  const b=document.getElementById('menuBtn');
  b.setAttribute('aria-expanded',String(open));
  b.setAttribute('aria-label',open?'Collapse sidebar':'Expand sidebar');
}
function initSidebar(){
  setSidebar(!matchMedia('(max-width:768px)').matches);
}
function toggleSidebar(){
  setSidebar(!S.sidebarOpen);
}

/* ===== NAVIGATION ===== */
const VIEW_TITLES={dashboard:'Dashboard',chat:'Chat',checklist:'Checklist',settings:'Settings'};
function switchView(name){
  S.view=name;
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  const el=document.getElementById('view-'+name);
  if(el)el.classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n=>{
    const on=n.dataset.view===name;
    n.classList.toggle('active',on);
    if(on)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');
  });
  document.title=(VIEW_TITLES[name]||'Purchasing Coach')+' · Purchasing Coach';
  announce(VIEW_TITLES[name]+' view');
  if(matchMedia('(max-width:768px)').matches)setSidebar(false);
  if(name==='dashboard')refreshAnalytics();
  if(name==='chat')document.getElementById('chatBox').focus();
}
function announce(msg){const sr=document.getElementById('sr');if(sr)sr.textContent=msg;}

/* ===== META ===== */
async function loadMeta(){
  try{
    const r=await fetch('/api/meta');const m=await r.json();
    S.backend={name:m.backend,model:m.model,requires_model:m.requires_model};
    S.guideline=m.guideline;
    document.getElementById('backendLabel').textContent=m.backend;
    document.getElementById('guidelineLabel').textContent=m.guideline;
    document.getElementById('setBackend').textContent=m.backend;
    document.getElementById('setModel').textContent=m.model;
    document.getElementById('setReqModel').textContent=m.requires_model?'Yes':'No';
    document.getElementById('setGuideline').textContent=m.guideline;
    if(m.version){const av=document.getElementById('aboutVersion');if(av)av.textContent='v'+m.version;}
  }catch(e){
    document.getElementById('backendPill').className='pill err';
    document.getElementById('backendLabel').textContent='offline';
  }
  // Health check
  try{
    const h=await fetch('/api/health');const d=await h.json();
    const pill=document.getElementById('backendPill');
    pill.className='pill '+(d.status==='ok'?'ok':'err');
  }catch(e){}
  // Backends list
  try{
    const r=await fetch('/api/backends');const list=await r.json();
    document.getElementById('setBackendList').innerHTML=
      list.map(b=>'<span class="pill '+(b.name===S.backend.name?'ok':'info')+
        '" style="margin:2px">'+b.name+'</span>').join(' ');
  }catch(e){}
}

/* ===== SESSIONS ===== */
async function loadSessions(){
  try{
    const r=await fetch('/api/sessions');S.sessions=await r.json();
    const el=document.getElementById('sessionList');
    el.innerHTML=S.sessions.map(s=>
      `<div class="session-item">
        <button type="button" class="session-open" onclick="loadSession('${s.id}')"
                title="Open: ${esc(s.title)}">
          <span class="title">${esc(s.title)}</span>
          <span class="count" aria-label="${s.message_count||0} messages">${s.message_count||0}</span>
        </button>
        <button type="button" class="del" onclick="delSession('${s.id}')"
                aria-label="Delete session: ${esc(s.title)}" title="Delete">&times;</button>
      </div>`).join('');
  }catch(e){}
}
async function saveSession(){
  if(!S.history.length)return;
  const title=S.history.find(m=>m.role==='user')?.content.slice(0,40)||'Session';
  const data={id:S.currentSession,title,messages:S.history.map(m=>({
    role:m.role,content:m.content,timestamp:new Date().toISOString()})),
    backend:S.backend.name,guideline_path:S.guideline};
  try{const r=await fetch('/api/sessions',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(data)});const d=await r.json();S.currentSession=d.id;loadSessions();}catch(e){}
}
async function loadSession(id){
  try{const r=await fetch('/api/sessions/'+id);const d=await r.json();
    S.currentSession=id;S.history=d.messages||[];
    document.getElementById('chatThread').innerHTML='';
    S.history.forEach(m=>addMsg(m.role==='user'?'you':'coach',m.role==='user'?'me':'',m.content));
    switchView('chat');
  }catch(e){}
}
async function delSession(id){
  try{await fetch('/api/sessions/'+id,{method:'DELETE'});loadSessions();}catch(e){}
}

/* ===== MARKDOWN ===== */
function md(src){
  const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const inline=s=>esc(s).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
    .replace(/`([^`]+)`/g,'<code>$1</code>');
  let html='',list=null,table=false,fence=false,fenceBuf=[];
  const closeList=()=>{if(list){html+=`</${list}>`;list=null;}};
  const closeTable=()=>{if(table){html+='</table>';table=false;}};
  for(const line of src.split('\n')){
    if(fence){if(/^\s*```/.test(line)){html+='<pre>'+esc(fenceBuf.join('\n'))+'</pre>';fence=false;fenceBuf=[];}else fenceBuf.push(line);continue;}
    if(/^\s*```/.test(line)){closeList();closeTable();fence=true;continue;}
    if(/^\s*\|.*\|\s*$/.test(line)){closeList();if(/^\s*\|[\s:|-]+\|\s*$/.test(line))continue;
      const cells=line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(c=>inline(c.trim()));
      const tag=table?'td':'th';if(!table){html+='<table>';table=true;}
      html+='<tr>'+cells.map(c=>`<${tag}>${c}</${tag}>`).join('')+'</tr>';continue;}
    closeTable();
    const h=line.match(/^#{1,6}\s+(.*)/);const li=line.match(/^\s*[-*+]\s+(.*)/);const num=line.match(/^\s*\d+[.)]\s+(.*)/);
    if(h){closeList();html+='<div class="h">'+inline(h[1])+'</div>';}
    else if(li){if(list!=='ul'){closeList();html+='<ul>';list='ul';}html+='<li>'+inline(li[1])+'</li>';}
    else if(num){if(list!=='ol'){closeList();html+='<ol>';list='ol';}html+='<li>'+inline(num[1])+'</li>';}
    else if(!line.trim()){closeList();}
    else{closeList();html+='<p>'+inline(line)+'</p>';}
  }
  if(fence)html+='<pre>'+esc(fenceBuf.join('\n'))+'</pre>';
  closeList();closeTable();return html;
}

/* ===== CHAT ===== */
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
const chatLog=document.getElementById('chatLog');
const chatThread=document.getElementById('chatThread');
const chatBox=document.getElementById('chatBox');
const sendBtn=document.getElementById('sendBtn');
const tenderBtn=document.getElementById('tenderBtn');
const sr=document.getElementById('sr');

function nearBottom(){return chatLog.scrollHeight-chatLog.scrollTop-chatLog.clientHeight<80;}
function keepDown(s){if(s)chatLog.scrollTop=chatLog.scrollHeight;}

function addMsg(who,cls,text){
  const stick=nearBottom();
  const div=document.createElement('div');div.className='msg '+(cls||'');
  const head=document.createElement('div');head.className='who';
  const av=document.createElement('span');av.className='av';av.setAttribute('aria-hidden','true');
  av.textContent=who==='you'?'U':(who==='coach'?'PC':'i');
  const name=document.createElement('span');name.className='name';name.textContent=who;
  head.append(av,name);
  if(who==='coach'){
    const copy=document.createElement('button');copy.className='copy';copy.type='button';
    copy.textContent='Copy';copy.setAttribute('aria-label','Copy reply');head.appendChild(copy);
  }
  const body=document.createElement('div');body.className='body';body.textContent=text;
  div.append(head,body);chatThread.appendChild(div);keepDown(stick);
  // Attach copy
  const cpBtn=div.querySelector('.copy');
  if(cpBtn)cpBtn.addEventListener('click',()=>{
    const t=body.innerText;navigator.clipboard?.writeText(t).then(
      ()=>{cpBtn.textContent='Copied';setTimeout(()=>cpBtn.textContent='Copy',1200);},
      ()=>{cpBtn.textContent='Failed';setTimeout(()=>cpBtn.textContent='Copy',1200);});
  });
  return body;
}

function setBusy(b){
  S.busy=b;tenderBtn.disabled=b;
  if(b){sendBtn.textContent='Stop';sendBtn.classList.add('stop');}
  else{sendBtn.textContent='Send';sendBtn.classList.remove('stop');S.aborter=null;}
}

// Initial greeting
addMsg('coach','sys','Hello! Ask me anything about the purchasing guideline, or click "Tender Checklist" to prepare a compliant tender document. I work with any backend — no LLM required.');

async function chat(text){
  addMsg('you','me',text);
  S.history.push({role:'user',content:text});
  const body=addMsg('coach','','');body.classList.add('streaming');
  setBusy(true);const ac=S.aborter=new AbortController();
  let full='';
  try{
    const resp=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({messages:S.history}),signal:ac.signal});
    if(!resp.ok)throw new Error((await resp.json()).error||resp.status);
    const reader=resp.body.getReader();const dec=new TextDecoder();
    body.className='body md streaming';
    for(;;){const{done,value}=await reader.read();if(done)break;
      const stick=nearBottom();full+=dec.decode(value,{stream:true});
      body.innerHTML=md(full);keepDown(stick);}
    if(ac.signal.aborted)throw new DOMException('stopped','AbortError');
    S.history.push({role:'assistant',content:full});
    sr.textContent='Reply complete.';saveSession();
  }catch(err){
    if(err.name==='AbortError'||ac.signal.aborted){
      if(full){body.innerHTML=md(full)+'<div class="stopnote">stopped</div>';S.history.push({role:'assistant',content:full});}
      else body.innerHTML='<div class="stopnote">stopped</div>';
    }else{
      body.className='body';
      body.innerHTML='<span class="warn">Request failed: '+esc(err.message)+'</span>';
      S.history.pop();
    }
  }finally{body.classList.remove('streaming');setBusy(false);chatBox.focus();}
}

/* ===== TENDER INTERVIEW ===== */
function startTender(){
  if(S.busy)return;
  const restarting=S.tender!==null;
  S.tender={stage:'item',item:'',questions:[],answers:[]};
  tenderBtn.textContent='Restart Interview';
  addMsg('coach','sys',(restarting?'Interview restarted — what':'Tender checklist — what')+
    ' do you want to buy? Describe the item or solution. (Type "cancel" to abort.)');
  chatBox.placeholder='e.g. 200 laptops for the sales team';chatBox.focus();
}
function endTender(){
  S.tender=null;tenderBtn.textContent='Tender Checklist';
  chatBox.placeholder='Ask about the guideline...';
  document.getElementById('interviewProgress').classList.remove('active');
  document.getElementById('interviewProgress').innerHTML='';
}
function renderProgress(step,total){
  const el=document.getElementById('interviewProgress');
  el.classList.add('active');
  let html='<div class="progress-bar">';
  for(let i=0;i<total;i++){
    const cls=i<step?'done':(i===step?'current':'');
    html+=`<div class="progress-step ${cls}"><div class="dot"></div><div class="num">${i+1}</div></div>`;
    if(i<total-1)html+=`<div class="progress-line ${i<step?'done':''}"></div>`;
  }
  html+='</div>';el.innerHTML=html;
}
function askNext(){
  const i=S.tender.answers.length;
  renderProgress(i,S.tender.questions.length);
  addMsg('coach','sys',`[${i+1}/${S.tender.questions.length}] ${S.tender.questions[i].question}`);
}

async function tenderInput(text){
  const word=text.toLowerCase();
  if(word==='cancel'){endTender();addMsg('coach','sys','Tender flow cancelled.');return;}
  if(word==='restart'||word==='/tender'){startTender();return;}
  addMsg('you','me',text);
  if(S.tender.stage==='item'){
    S.tender.item=text;S.tender.stage='questions';
    const note=addMsg('coach','sys','Planning the right questions for this purchase...');
    setBusy(true);const ac=S.aborter=new AbortController();
    try{
      const resp=await fetch('/api/tender/start',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({item:S.tender.item}),signal:ac.signal});
      const data=await resp.json();if(!resp.ok)throw new Error(data.error||resp.status);
      S.tender.questions=data.questions;
      note.textContent=`I have ${data.questions.length} questions. Answer briefly; reply "TBC" if unsure.`;
      askNext();
    }catch(err){
      note.innerHTML=(err.name==='AbortError'||ac.signal.aborted)?'Interview stopped.':
        '<span class="warn">Could not plan interview: '+esc(err.message)+'</span>';
      endTender();
    }finally{setBusy(false);chatBox.focus();}
    return;
  }
  S.tender.answers.push([S.tender.questions[S.tender.answers.length].question,text||'TBC']);
  renderProgress(S.tender.answers.length,S.tender.questions.length);
  if(S.tender.answers.length<S.tender.questions.length){askNext();return;}
  const note=addMsg('coach','sys','Building the compliance checklist... this may take a moment.');
  setBusy(true);const ac=S.aborter=new AbortController();
  try{
    const resp=await fetch('/api/tender/finish',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({item:S.tender.item,answers:S.tender.answers}),signal:ac.signal});
    const data=await resp.json();if(!resp.ok)throw new Error(data.error||resp.status);
    S.checklist=data;
    const unv=(data.unverified||[]).length?` <span class="warn">${data.unverified.length} clause(s) could not be verified (${data.unverified.join(', ')}).</span>`:'';
    const added=(data.added_core||[]).length?` Sections ${data.added_core.join(', ')} added automatically for full coverage.`:'';
    const mand=data.mandatory?` (<strong>${data.mandatory}</strong> mandatory)`:'';
    note.innerHTML=`Done — <strong>${data.count}</strong> requirements${mand} for "${esc(data.tender_info.purchase_item)}".${added}${unv} The <strong>Review &amp; Approval</strong> sheet tallies the vendor's submission live (compliance rate and any mandatory non-compliant rows) for sign-off.`;
    const a=document.createElement('a');a.className='dl';a.href=data.download;
    a.textContent='\u2B07 '+data.file;note.parentElement.appendChild(a);
    sr.textContent='Checklist ready: '+data.count+' requirements.';
    renderChecklist(data.requirements);
    refreshAnalytics();saveSession();
  }catch(err){
    note.innerHTML=(err.name==='AbortError'||ac.signal.aborted)?'Checklist generation stopped.':
      '<span class="warn">Checklist generation failed: '+esc(err.message)+'</span>';
  }finally{endTender();setBusy(false);chatBox.focus();}
}

/* ===== CHECKLIST VIEWER ===== */
let clData=[];
function renderChecklist(reqs){
  clData=reqs||[];
  document.getElementById('clEmpty').style.display=clData.length?'none':'block';
  document.getElementById('clTable').style.display=clData.length?'':'none';
  // Populate section filter
  const sections=[...new Set(clData.map(r=>r.section))].sort();
  const sel=document.getElementById('clSection');
  sel.innerHTML='<option value="">All Sections</option>'+
    sections.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('');
  filterChecklist();
}
function filterChecklist(){
  const q=(document.getElementById('clSearch').value||'').toLowerCase();
  const sec=document.getElementById('clSection').value;
  const mo=document.getElementById('clMO').value;
  const filtered=clData.filter(r=>{
    if(sec&&r.section!==sec)return false;
    if(mo&&r.mandatory!==mo)return false;
    if(q&&!(r.ref+' '+r.section+' '+r.requirement).toLowerCase().includes(q))return false;
    return true;
  });
  const body=document.getElementById('clBody');
  body.innerHTML=filtered.map((r,i)=>
    `<tr draggable="true" data-idx="${i}">
      <td><button type="button" class="drag-handle" data-idx="${i}"
          aria-label="Reorder ${esc(r.ref)}. Press Arrow Up or Arrow Down to move."
          title="Drag, or focus and use arrow keys, to reorder">&#9776;</button></td>
      <td style="white-space:nowrap;font-weight:600">${esc(r.ref)}</td>
      <td>${esc(r.section)}</td>
      <td contenteditable="true" role="textbox" aria-label="Requirement text for ${esc(r.ref)}"
          data-field="requirement" data-idx="${i}"
          onblur="updateReq(${i},this.textContent)">${esc(r.requirement)}</td>
      <td><span class="badge ${r.mandatory==='M'?'m':'o'}">${r.mandatory==='M'?'Mandatory':'Optional'}</span></td>
    </tr>`).join('');
  document.getElementById('clCount').textContent=filtered.length+' of '+clData.length+' requirements';
  setupDragDrop();
}
function updateReq(idx,text){
  if(clData[idx])clData[idx].requirement=text.trim();
}
function moveRow(from,to){
  if(to<0||to>=clData.length||from===to)return;
  const [item]=clData.splice(from,1);clData.splice(to,0,item);filterChecklist();
  const b=document.querySelector('#clBody tr[data-idx="'+to+'"] .drag-handle');
  if(b)b.focus();
  announce(item.ref+' moved to position '+(to+1)+' of '+clData.length);
}
function setupDragDrop(){
  const body=document.getElementById('clBody');
  let dragRow=null;
  body.querySelectorAll('tr').forEach(row=>{
    row.addEventListener('dragstart',e=>{dragRow=row;row.style.opacity='0.4';});
    row.addEventListener('dragend',()=>{if(dragRow)dragRow.style.opacity='1';dragRow=null;});
    row.addEventListener('dragover',e=>{e.preventDefault();});
    row.addEventListener('drop',e=>{
      e.preventDefault();if(!dragRow||dragRow===row)return;
      moveRow(parseInt(dragRow.dataset.idx),parseInt(row.dataset.idx));
    });
  });
  // Keyboard alternative to drag-and-drop (WCAG 2.1.1).
  body.querySelectorAll('.drag-handle').forEach(h=>{
    h.addEventListener('keydown',e=>{
      const idx=parseInt(h.dataset.idx);
      if(e.key==='ArrowUp'){e.preventDefault();moveRow(idx,idx-1);}
      else if(e.key==='ArrowDown'){e.preventDefault();moveRow(idx,idx+1);}
    });
  });
}
async function exportCSV(){window.location='/api/export/csv';}
async function exportJSON(){
  try{const r=await fetch('/api/export/json');const d=await r.json();
    const blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob);const a=document.createElement('a');
    a.href=url;a.download='checklist.json';a.click();URL.revokeObjectURL(url);}catch(e){}
}

/* ===== ANALYTICS & CHARTS ===== */
async function refreshAnalytics(){
  try{
    const r=await fetch('/api/analytics');const d=await r.json();
    document.getElementById('mTotal').textContent=d.total_requirements;
    document.getElementById('mMand').textContent=d.mandatory_count;
    document.getElementById('mOpt').textContent=d.optional_count;
    document.getElementById('mCov').textContent=d.coverage_pct+'%';
    document.getElementById('dashEmpty').style.display=d.total_requirements?'none':'block';
    document.getElementById('metricsGrid').style.display=d.total_requirements?'':'none';
    document.querySelector('.charts').style.display=d.total_requirements?'':'none';
    if(d.total_requirements)drawCharts(d);
  }catch(e){}
}
function drawCharts(d){
  drawPie(d.mandatory_count,d.optional_count);
  drawBars(d.by_section);
}
function redrawCharts(){refreshAnalytics();}

function drawPie(mand,opt){
  const c=document.getElementById('pieChart');if(!c)return;
  const ctx=c.getContext('2d');const w=c.width=c.offsetWidth;const h=c.height=220;
  ctx.clearRect(0,0,w,h);
  const total=mand+opt;if(!total)return;
  const cx=w/2,cy=h/2,r=Math.min(w,h)/2-20;
  const data=[{v:mand,c:'#f87171',l:'Mandatory'},{v:opt,c:'#34d399',l:'Optional'}];
  const pd=document.getElementById('pieDesc');
  if(pd)pd.textContent=`${mand} mandatory and ${opt} optional requirements `
    +`(${Math.round(mand/total*100)}% mandatory).`;
  let start=-Math.PI/2;
  data.forEach(d=>{
    const angle=(d.v/total)*Math.PI*2;
    ctx.beginPath();ctx.moveTo(cx,cy);ctx.arc(cx,cy,r,start,start+angle);ctx.closePath();
    ctx.fillStyle=d.c;ctx.fill();
    // Label
    const mid=start+angle/2;const lx=cx+Math.cos(mid)*(r*0.6);const ly=cy+Math.sin(mid)*(r*0.6);
    ctx.fillStyle='#fff';ctx.font='bold 13px system-ui';ctx.textAlign='center';ctx.textBaseline='middle';
    ctx.fillText(d.v,lx,ly);
    start+=angle;
  });
  // Legend
  let lx=10,ly=h-10;
  data.forEach(d=>{
    ctx.fillStyle=d.c;ctx.fillRect(lx,ly-8,10,10);
    ctx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--tx-1');
    ctx.font='11px system-ui';ctx.textAlign='left';ctx.fillText(`${d.l} (${d.v})`,lx+14,ly);
    lx+=100;
  });
}
function drawBars(bySection){
  const c=document.getElementById('barChart');if(!c)return;
  const ctx=c.getContext('2d');const w=c.width=c.offsetWidth;
  const entries=Object.entries(bySection).sort((a,b)=>b[1]-a[1]).slice(0,10);
  const bd=document.getElementById('barDesc');
  if(bd)bd.textContent='Requirements by section — '
    +entries.map(([n,v])=>`${n}: ${v}`).join('; ')+'.';
  const maxVal=Math.max(...entries.map(e=>e[1]),1);
  const barH=22,gap=6,pad=140;
  const h=entries.length*(barH+gap)+20;
  c.height=Math.max(h,100);
  ctx.clearRect(0,0,w,c.height);
  const txtColor=getComputedStyle(document.documentElement).getPropertyValue('--tx-1');
  entries.forEach(([name,val],i)=>{
    const y=i*(barH+gap)+10;const barW=((w-pad-20)*val/maxVal);
    // Bar
    ctx.fillStyle='rgba(79,143,247,0.7)';
    ctx.beginPath();ctx.roundRect(pad,y,Math.max(barW,4),barH,4);ctx.fill();
    // Label
    ctx.fillStyle=txtColor;ctx.font='11px system-ui';ctx.textAlign='right';ctx.textBaseline='middle';
    ctx.fillText(name.length>18?name.slice(0,18)+'...':name,pad-8,y+barH/2);
    // Value
    ctx.fillStyle='#fff';ctx.textAlign='left';ctx.font='bold 11px system-ui';
    ctx.fillText(val,pad+barW+6,y+barH/2);
  });
}

/* ===== INPUT ===== */
function autoresize(){chatBox.style.height='auto';chatBox.style.height=Math.min(chatBox.scrollHeight,160)+'px';}
function submit(){
  const text=chatBox.value.trim();if(!text||S.busy)return;
  chatBox.value='';autoresize();
  if(S.tender){tenderInput(text);return;}
  if(text==='/tender'){startTender();return;}
  chat(text);
}
function handleSend(){if(S.busy){if(S.aborter)S.aborter.abort();}else submit();}
chatBox.addEventListener('input',autoresize);
chatBox.addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submit();}
  else if(e.key==='Escape'&&S.busy){e.preventDefault();if(S.aborter)S.aborter.abort();}
});

/* ===== INIT ===== */
initTheme();initSidebar();loadMeta();loadSessions();refreshAnalytics();
// Health check every 30s
setInterval(async()=>{try{const r=await fetch('/api/health');const d=await r.json();
  const pill=document.getElementById('backendPill');
  pill.className='pill '+(d.status==='ok'?'ok':'err');
  document.getElementById('backendLabel').textContent=S.backend.name;}catch(e){}},30000);
</script>
</body>
</html>
"""
