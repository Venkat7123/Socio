"""Stand-ins for the Groq wrapper used by the agent tests."""
from app.llm import ModelUnavailable


class FakeLLM:
    """Replaces GroqLLM: returns a canned JSON dict and a canned transcript, recording what it was sent."""

    def __init__(self, payload=None, transcript="", fail=False):
        self.payload = payload or {}
        self.transcript = transcript
        self.fail = fail
        self.json_calls = []
        self.transcribe_calls = []

    def json(self, system, parts, schema, temperature=0.1):
        self.json_calls.append({"system": system, "parts": parts, "schema": schema})
        if self.fail:
            raise ModelUnavailable("down")
        return self.payload

    def transcribe(self, data, mime):
        self.transcribe_calls.append((data, mime))
        if self.fail:
            raise ModelUnavailable("down")
        return self.transcript
