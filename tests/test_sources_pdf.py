"""
Tests for PDF validation, broken PDF handling, and 'Ask about this file' chat context.
"""
import base64
import json
import pathlib
import re
import threading
import urllib.error
import urllib.request
import pytest

from ui_source import ui_all

REPO = pathlib.Path(__file__).resolve().parent.parent


def read_html() -> str:
    """index.html + stylesheets + scripts (ui_source.py)."""
    return ui_all()


@pytest.fixture
def server(home, monkeypatch):
    """The real handler on an ephemeral port, in this process."""
    from http.server import ThreadingHTTPServer
    import serve

    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post(base, path, body, project):
    req = urllib.request.Request(
        f"{base}{path}{chr(38) if chr(63) in path else chr(63)}project={project}", method="POST",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_upload_broken_pdf_rejected(server, lte):
    # Upload broken PDF that does not start with %PDF-
    broken_bytes = b"NOT_A_REAL_PDF_DATA_HERE"
    payload = {
        "name": "broken_doc.pdf",
        "data_b64": base64.b64encode(broken_bytes).decode("ascii"),
    }
    code, body = post(server, "/api/upload", payload, lte)
    assert code == 400
    expected_msg = "This file is not a valid PDF (it may be empty or damaged). Upload it again."
    assert body.get("error") == expected_msg


def test_upload_valid_pdf_accepted(server, lte):
    # Upload valid PDF starting with %PDF-
    valid_pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    payload = {
        "name": "valid_doc.pdf",
        "data_b64": base64.b64encode(valid_pdf_bytes).decode("ascii"),
    }
    code, body = post(server, "/api/upload", payload, lte)
    assert code == 200
    assert any(s["name"] == "valid_doc.pdf" for s in body.get("sources", []))


def test_checks_upload_broken_pdf_rejected(server, lte):
    broken_bytes = b"MALFORMED_DFM_REPORT_TEXT"
    payload = {
        "name": "dfm_broken.pdf",
        "data_b64": base64.b64encode(broken_bytes).decode("ascii"),
        "kind": "pcb",
    }
    code, body = post(server, "/api/checks/upload", payload, lte)
    assert code == 400
    expected_msg = "This file is not a valid PDF (it may be empty or damaged). Upload it again."
    assert body.get("error") == expected_msg


VIEWER_JS = (REPO / "ui" / "js" / "viewer.js").read_text(encoding="utf-8")
PAGES_JS = (REPO / "ui" / "js" / "views" / "pages.js").read_text(encoding="utf-8")


def test_viewer_pdf_validation_static_ui():
    # The viewer checks the first bytes for %PDF- before it embeds the iframe, and says why when it is not a PDF
    assert "%PDF-" in VIEWER_JS
    expected_msg = "This file is not a valid PDF (it may be empty or damaged). Upload it again."
    assert expected_msg in VIEWER_JS
    check = VIEWER_JS.index("startsWith('%PDF-')")
    frame = VIEWER_JS.index("<iframe")
    assert check < frame, "the PDF is checked before the iframe is built"
    assert "errorLine('open this PDF'" in VIEWER_JS, "a bad PDF is an error line, not an empty frame"


def test_viewer_header_asks_about_the_file():
    # One Ask icon in the document header: an icon-only button needs its title, and the handler goes through askAbout
    assert "Ask about this file" in VIEWER_JS
    assert "act: 'ask-file'" in VIEWER_JS
    handler = re.search(r"onAct\('ask-file'.*?\n\}\);", VIEWER_JS, re.S)
    assert handler and "askAbout({kind: 'file'" in handler.group(0)
    # the chat owns its own context chip: the viewer must not set it behind the chat's back
    assert not re.search(r"activeFileChip\s*=", VIEWER_JS)


def test_viewer_has_no_legacy_viewer_left():
    # The old fixed-position viewer (closeViewer, the viewer overlay, the file-badge table) was dead code; it stays gone
    for dead in ("closeViewer", "closeviewer", "FILE_BADGES", "viewer-overlay", "fname-btn", "ext-lnk", "prompt("):
        assert dead not in VIEWER_JS, dead
    for state in ("loadingLine(", "errorLine(", "emptyState("):
        assert state in VIEWER_JS, f"the viewer needs its {state} state"


def test_ask_about_file_chat_integration(server, lte, monkeypatch):
    # The engine is stubbed: this checks what the server hands it, not the model.
    import agent
    seen = {}

    def fake_respond(m, ask, hist, backend=None, timeout=None, **_kw):
        seen["ask"] = ask
        return {"reply": "500 mA.", "actions": []}
    monkeypatch.setattr(agent, "respond", fake_respond)
    # 1. The composer holds the context chip (one chip for part, net, file, ...) and its x clears it;
    #    the viewer's Ask icon hands the file to it through askAbout
    content = read_html()
    assert 'id="chat-chip"' in content
    assert 'data-act="clear-chip"' in content
    assert "askAbout({kind: 'file'" in content

    # 2. Upload a valid text or pdf source to ask about
    sample_text = "Operating Voltage: 3.3V, Maximum Current: 500mA."
    text_payload = {
        "name": "power_specs.txt",
        "data_b64": base64.b64encode(sample_text.encode("utf-8")).decode("ascii"),
    }
    code, _ = post(server, "/api/upload", text_payload, lte)
    assert code == 200

    # 3. Send a message to /api/chat with file context
    chat_payload = {
        "text": "What is the maximum operating current?",
        "file": "power_specs.txt",
    }
    code, body = post(server, "/api/chat", chat_payload, lte)
    assert code == 200
    chat = body.get("chat", [])
    assert chat, "Chat history should contain message"

    # User message retains the source attribution
    user_msg = next((m for m in chat if m.get("role") == "user" and m.get("text") == chat_payload["text"]), None)
    assert user_msg is not None
    assert user_msg.get("source") == "power_specs.txt"
    # The engine was given the file's content, not just its name
    assert "power_specs.txt" in seen["ask"]
    assert "Maximum Current: 500mA" in seen["ask"]
