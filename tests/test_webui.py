"""Web UI endpoints exercised over real HTTP with the fake LLM backend."""

import json
import threading
import urllib.error
import urllib.request

import pytest
from openpyxl import load_workbook

import coach.webui as webui_mod
from coach.llm import Coach
from coach.webui import WebUI
from tests.test_tender import CHECKLIST, FakeBackend


@pytest.fixture()
def server(tmp_path):
    ui = WebUI(Coach("guideline text", FakeBackend()), FakeBackend(),
               "guideline.docx", None, tmp_path)
    httpd = ui.make_server(port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, ui
    httpd.shutdown()


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.status, resp.headers, resp.read()


def _post(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read())


def test_index_and_meta(server):
    base, _ = server
    status, headers, body = _get(base + "/")
    assert status == 200 and b"Purchasing Coach" in body
    assert "text/html" in headers["Content-Type"]

    status, _, body = _get(base + "/api/meta")
    meta = json.loads(body)
    assert status == 200
    assert meta["backend"] == "fake"
    assert meta["model"] == "fake-model"
    assert meta["guideline"] == "guideline.docx"


def test_page_has_restart_interview_wiring(server):
    base, _ = server
    _, _, body = _get(base + "/")
    page = body.decode()
    # Mid-interview the tender button becomes a restart control, and the
    # typed "restart" / "/tender" inputs re-enter startTender().
    assert "Restart Interview" in page or "Restart interview" in page
    assert "function endTender()" in page
    assert "'restart'" in page and "'/tender'" in page


def test_chat_streams_reply(server):
    base, _ = server
    req = urllib.request.Request(
        base + "/api/chat",
        data=json.dumps({"messages": [{"role": "user",
                                       "content": "warranty?"}]}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
        text = resp.read().decode()
    assert text == "See clause 8.4 (Warranty)."


def test_tender_flow_over_http(server, tmp_path):
    base, ui = server
    status, plan = _post(base + "/api/tender/start", {"item": "Firewalls"})
    assert status == 200
    assert [q["question"] for q in plan["questions"]] == [
        "When is the submission deadline?",
        "Which department is requesting this?"]

    answers = [[q["question"], "answer"] for q in plan["questions"]]
    status, result = _post(base + "/api/tender/finish",
                           {"item": "Firewalls", "answers": answers})
    assert status == 200
    assert result["count"] == len(CHECKLIST["requirements"])
    assert result["file"].startswith("TENDER_CHECKLIST_Firewall_appliances")
    assert (ui.out_dir / result["file"]).exists()

    status, headers, body = _get(base + result["download"])
    assert status == 200
    assert "spreadsheetml" in headers["Content-Type"]
    download = tmp_path / "downloaded.xlsx"
    download.write_bytes(body)
    wb = load_workbook(download)
    assert "Compliance Tracker" in wb.sheetnames


def test_bad_requests(server):
    base, _ = server
    for url, payload in [(base + "/api/tender/start", {}),
                         (base + "/api/chat", {})]:
        with pytest.raises(urllib.error.HTTPError) as err:
            _post(url, payload)
        assert err.value.code == 400

    # Downloads are limited to files generated in this session.
    with pytest.raises(urllib.error.HTTPError) as err:
        _get(base + "/api/download/../../etc/passwd")
    assert err.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as err:
        _get(base + "/api/download/unknown.xlsx")
    assert err.value.code == 404


class _FailingBackend(FakeBackend):
    def complete_json(self, *a, **k):
        raise RuntimeError("boom")


def test_post_error_returns_500_and_is_logged(tmp_path, caplog):
    ui = WebUI(Coach("guideline text", _FailingBackend()), _FailingBackend(),
               "g.docx", None, tmp_path)
    httpd = ui.make_server(port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with caplog.at_level("ERROR", logger="coach.webui"):
            with pytest.raises(urllib.error.HTTPError) as err:
                _post(base + "/api/tender/start", {"item": "x"})
            assert err.value.code == 500
        assert any("failed" in r.getMessage() for r in caplog.records)
    finally:
        httpd.shutdown()


def test_security_headers_present(server):
    base, _ = server
    _, headers, _ = _get(base + "/api/meta")
    assert headers.get("X-Content-Type-Options") == "nosniff"


def test_oversized_body_rejected(server, monkeypatch):
    base, _ = server
    monkeypatch.setattr(webui_mod, "MAX_BODY_BYTES", 8)
    with pytest.raises(urllib.error.HTTPError) as err:
        _post(base + "/api/chat",
              {"messages": [{"role": "user", "content": "hello world"}]})
    assert err.value.code == 413


def test_session_id_traversal_is_neutralised(tmp_path, monkeypatch):
    sdir = tmp_path / "sessions"
    sdir.mkdir()
    monkeypatch.setattr(webui_mod, "SESSIONS_DIR", sdir)
    ui = WebUI(Coach("g", FakeBackend()), FakeBackend(), "g.docx", None, tmp_path)

    # A malicious id is not honoured — a safe id is minted and the file stays
    # inside the sessions directory.
    sid = ui.save_session({"id": "../../evil", "title": "x"})
    assert sid != "../../evil"
    assert (sdir / f"{sid}.json").exists()
    assert not (tmp_path / "evil.json").exists()

    # Reads/deletes with traversal ids are safe no-ops.
    assert ui._session_path("../bad") is None
    assert ui.load_session("../../evil") is None
    assert ui.delete_session("../../etc/passwd") is False
