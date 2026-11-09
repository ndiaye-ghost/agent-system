"""Client for a self-hosted LLM exposing the OpenAI-compatible chat API.

Works with Ollama (http://localhost:11434/v1), vLLM, llama.cpp server, LM Studio,
LocalAI and TGI. Uses only the standard library, so it runs on air-gapped hosts.

Every request/response is appended to an audit log (JSONL): this supports the
tool-confidence argument of ISO 26262-8 §11 and lets reviewers replay what the
model was asked and what it answered.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LLMConfig:
    base_url: str = field(default_factory=lambda: os.getenv("SAFETY_AGENT_BASE_URL", "http://localhost:11434/v1"))
    model: str = field(default_factory=lambda: os.getenv("SAFETY_AGENT_MODEL", "qwen2.5:14b"))
    api_key: str = field(default_factory=lambda: os.getenv("SAFETY_AGENT_API_KEY", "none"))
    temperature: float = 0.0  # reproducibility first
    timeout: float = 300.0
    audit_log: str = field(default_factory=lambda: os.getenv("SAFETY_AGENT_AUDIT_LOG", "safety_agent_audit.jsonl"))


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()

    def chat(self, messages: list[dict], tools: list[dict] | None = None, json_mode: bool = False) -> dict:
        """Send a chat request; return the assistant message dict (may contain `tool_calls`)."""
        payload: dict = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            self.config.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.config.api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise LLMError(f"Le serveur LLM a répondu {e.code} : {e.read().decode(errors='replace')[:500]}") from e
        except urllib.error.URLError as e:
            raise LLMError(
                f"Serveur LLM injoignable à {self.config.base_url} ({e.reason}). "
                "Vérifiez qu'Ollama/vLLM tourne et la variable SAFETY_AGENT_BASE_URL."
            ) from e
        message = body["choices"][0]["message"]
        self._audit(payload, message)
        return message

    def _audit(self, payload: dict, message: dict) -> None:
        if not self.config.audit_log:
            return
        record = {
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "model": self.config.model,
            "base_url": self.config.base_url,
            "request_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            "request": payload,
            "response": message,
        }
        with Path(self.config.audit_log).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def extract_json(text: str):
    """Parse JSON from a model answer, tolerating ```json fences and surrounding prose."""
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = text.find(open_c), text.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError(f"Réponse du modèle non exploitable en JSON : {text[:300]}")
