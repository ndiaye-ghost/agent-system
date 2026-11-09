"""End-to-end test of the HTTP client and the CLI against a fake OpenAI-compatible server."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from safety_agent.cli import main
from safety_agent.llm import LLMClient, LLMConfig, LLMError

EX = Path(__file__).parent.parent / "examples"


@pytest.fixture
def server():
    received, replies = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append({"path": self.path, "body": body})
            msg = replies.pop(0) if replies else {"role": "assistant", "content": "ok"}
            data = json.dumps({"choices": [{"message": msg}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}/v1", received, replies
    httpd.shutdown()


def test_client_posts_and_audits(server, tmp_path):
    url, received, _ = server
    audit = tmp_path / "audit.jsonl"
    client = LLMClient(LLMConfig(base_url=url, model="m", audit_log=str(audit)))
    assert client.chat([{"role": "user", "content": "x"}])["content"] == "ok"
    assert received[0]["path"] == "/v1/chat/completions"
    assert received[0]["body"]["temperature"] == 0.0
    record = json.loads(audit.read_text().splitlines()[0])
    assert record["model"] == "m" and record["response"]["content"] == "ok"


def test_unreachable_server_gives_clear_error():
    client = LLMClient(LLMConfig(base_url="http://127.0.0.1:9/v1", audit_log="", timeout=2))
    with pytest.raises(LLMError, match="injoignable"):
        client.chat([{"role": "user", "content": "x"}])


def test_cli_chat_end_to_end(server, tmp_path, monkeypatch):
    url, received, replies = server
    monkeypatch.chdir(tmp_path)
    replies += [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "type": "function", "function": {
            "name": "list_fmea_rows", "arguments": json.dumps({"min_severity": 9})}}]},
        {"role": "assistant", "content": "4 lignes ont une gravité ≥ 9."},
    ]
    code = main(["chat", "--reqs", str(EX / "bms_exigences.csv"), "--fmea", str(EX / "bms_amdec.csv"),
                 "--base-url", url, "--model", "test", "-q", "Lignes critiques ?"])
    assert code == 0
    assert received[0]["body"]["tools"]  # tools were offered to the model
    assert received[1]["body"]["messages"][-1]["role"] == "tool"
    assert (tmp_path / "safety_agent_audit.jsonl").exists()


def test_cli_check_fail_on_error(capsys):
    assert main(["check", "--reqs", str(EX / "bms_exigences.csv"), "--fmea", str(EX / "bms_amdec.csv"),
                 "--fail-on", "error", "--format", "json"]) == 1
    assert json.loads(capsys.readouterr().out)[0]["level"] == "error"
