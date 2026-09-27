"""Ollama-backed provider. Raises OllamaUnavailableError for every failure
mode (not configured, connection refused, timeout, non-JSON output,
unparseable/unexpected JSON, out-of-taxonomy label) — the caller
(app.services.classification) always catches this and falls back to
DeterministicProvider. Never invents a result on failure.
"""
import json

import httpx

from app.config import settings
from app.providers.base import AIProvider, ClassificationOutcome, LitigationOutcome
from app.taxonomy import DOCUMENT_CLASSES, LITIGATION_SIGNALS


class OllamaUnavailableError(Exception):
    pass


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float | None = None):
        self.base_url = base_url if base_url is not None else settings.ollama_base_url
        self.model = model or settings.ollama_model
        self.timeout = timeout or settings.ollama_timeout_seconds

    def _generate_json(self, prompt: str) -> dict:
        if not self.base_url:
            raise OllamaUnavailableError("OLLAMA_BASE_URL not configured")
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False, "format": "json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            raw = response.json()["response"]
            return json.loads(raw)
        except (httpx.HTTPError, KeyError, json.JSONDecodeError, ValueError) as exc:
            raise OllamaUnavailableError(str(exc)) from exc

    def classify_document(self, text: str) -> ClassificationOutcome:
        prompt = (
            "You are classifying an insurance claim document. Choose exactly one label from this list: "
            f"{DOCUMENT_CLASSES}. Respond with strict JSON only, no other text: "
            '{"classification": "<label>", "confidence": <number between 0.0 and 1.0>}.\n\n'
            f"Document text:\n{text}"
        )
        data = self._generate_json(prompt)
        try:
            classification = str(data["classification"])
            confidence = float(data["confidence"])
        except (KeyError, TypeError, ValueError) as exc:
            raise OllamaUnavailableError(f"malformed response: {data!r}") from exc
        if classification not in DOCUMENT_CLASSES:
            raise OllamaUnavailableError(f"model returned unknown label: {classification!r}")
        return ClassificationOutcome(classification=classification, confidence=confidence)

    def detect_litigation_signal(self, text: str) -> LitigationOutcome:
        prompt = (
            "You are screening an insurance claim document for litigation signals. Choose exactly one label "
            f"from this list: {LITIGATION_SIGNALS}. Respond with strict JSON only, no other text: "
            '{"signal": "<label>", "confidence": <number between 0.0 and 1.0>}.\n\n'
            f"Document text:\n{text}"
        )
        data = self._generate_json(prompt)
        try:
            signal = str(data["signal"])
            confidence = float(data["confidence"])
        except (KeyError, TypeError, ValueError) as exc:
            raise OllamaUnavailableError(f"malformed response: {data!r}") from exc
        if signal not in LITIGATION_SIGNALS:
            raise OllamaUnavailableError(f"model returned unknown signal: {signal!r}")
        return LitigationOutcome(signal=signal, confidence=confidence)
