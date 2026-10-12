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

REPO = pathlib.Path(__file__).resolve().parent.parent
HTML_PATH = REPO / "ui" / "index.html"


def read_html() -> str:
    assert HTML_PATH.is_file(), "ui/index.html must exist"
    return HTML_PATH.read_text(encoding="utf-8")


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


def test_viewer_pdf_validation_static_ui():
    content = read_html()

    # Viewer checks for %PDF- before embedding iframe
    assert "%PDF-" in content
    expected_msg = "This file is not a valid PDF (it may be empty or damaged). Upload it again."
    assert expected_msg in content

    # Viewer header contains 'Ask about this file' button
    assert "Ask about this file" in content
    assert 'data-act="ask-file"' in content


def test_ask_about_file_chat_integration(server, lte, monkeypatch):
    # The engine is stubbed: this checks what the server hands it, not the model.
    import agent
    seen = {}

    def fake_respond(m, ask, hist, backend=None, timeout=None):
        seen["ask"] = ask
        return {"reply": "500 mA.", "actions": []}
    monkeypatch.setattr(agent, "respond", fake_respond)
    # 1. Chat chip element in composer
    content = read_html()
    assert 'id="chat-chip"' in content
    assert 'data-act="clear-file-chip"' in content
    assert "activeFileChip" in content

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
