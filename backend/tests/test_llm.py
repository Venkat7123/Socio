import base64
import io
import json
import time
from types import SimpleNamespace

import groq
import httpx
import pytest
from PIL import Image as PILImage

from app import llm as llm_mod
from app.llm import GroqLLM, Image, MediaFetchError, ModelUnavailable
from app.verification import VisionAssessment


def jpeg(w=3000, h=2000):
    buf = io.BytesIO()
    PILImage.new("RGB", (w, h), (120, 130, 140)).save(buf, "PNG")
    return buf.getvalue()


class FakeGroq:
    def __init__(self, reply=None, error=None, delay=0, transcript="hello there "):
        self.calls, self.audio_calls = [], []
        self.reply, self.error, self.delay, self.transcript = reply, error, delay, transcript
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._stt))

    def _chat(self, **kw):
        self.calls.append(kw)
        time.sleep(self.delay)
        if self.error:
            raise self.error
        msg = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    def _stt(self, **kw):
        self.audio_calls.append(kw)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.transcript)


OK = json.dumps({"same_spot": True, "resolved": False, "reason": "Hole remains."})


def test_json_request_shape_and_downscaled_images():
    fake = FakeGroq(reply=OK)
    out = GroqLLM(client=fake).json("SYS", ["BEFORE:", Image(jpeg(), "image/png"), "question"], VisionAssessment)
    assert out["same_spot"] is True and out["resolved"] is False and out["reason"] == "Hole remains."
    assert out["mismatches"] == []  # defaults fill the fields the reply left out
    kw = fake.calls[0]
    assert kw["messages"][0] == {"role": "system", "content": "SYS"}
    content = kw["messages"][1]["content"]
    assert [c["type"] for c in content] == ["text", "image_url", "text"]
    uri = content[1]["image_url"]["url"]
    assert uri.startswith("data:image/jpeg;base64,")
    im = PILImage.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
    assert max(im.size) == llm_mod.MAX_IMAGE_SIDE == 768  # 3000x2000 shrunk to keep token cost down
    rf = kw["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["schema"]["additionalProperties"] is False
    assert set(rf["json_schema"]["schema"]["required"]) == {"before_landmarks", "after_landmarks", "mismatches", "same_spot", "resolved", "reason"}
    assert "tool_choice" not in kw


def test_invalid_image_is_media_error():
    with pytest.raises(MediaFetchError):
        GroqLLM(client=FakeGroq(reply=OK)).json("S", [Image(b"not an image", "image/jpeg")], VisionAssessment)


@pytest.mark.parametrize("reply", [None, "", "not json", json.dumps({"same_spot": "maybe"})])
def test_bad_model_output_is_unavailable(reply):
    with pytest.raises(ModelUnavailable):
        GroqLLM(client=FakeGroq(reply=reply)).json("S", ["q"], VisionAssessment)


def test_rate_limit_maps_to_unavailable():
    resp = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com/x"))
    err = groq.RateLimitError("rate limited", response=resp, body=None)
    with pytest.raises(ModelUnavailable) as e:
        GroqLLM(client=FakeGroq(error=err)).json("S", ["q"], VisionAssessment)
    assert "429" in str(e.value)


def test_rate_limit_carries_retry_after_from_headers():
    resp = httpx.Response(429, headers={"x-ratelimit-reset-tokens": "1m2.5s"}, request=httpx.Request("POST", "https://api.groq.com/x"))
    err = groq.RateLimitError("rate limited", response=resp, body=None)
    with pytest.raises(ModelUnavailable) as e:
        GroqLLM(client=FakeGroq(error=err)).json("S", ["q"], VisionAssessment)
    assert e.value.retry_after == 62.5
    resp = httpx.Response(429, headers={"retry-after": "7"}, request=httpx.Request("POST", "https://api.groq.com/x"))
    with pytest.raises(ModelUnavailable) as e:
        GroqLLM(client=FakeGroq(error=groq.RateLimitError("r", response=resp, body=None))).json("S", ["q"], VisionAssessment)
    assert e.value.retry_after == 7


def test_seconds_parser():
    assert llm_mod._seconds("44.977s") == pytest.approx(44.977)
    assert llm_mod._seconds("18m43.2s") == pytest.approx(1123.2)
    assert llm_mod._seconds("2") == 2 and llm_mod._seconds("") is None and llm_mod._seconds("soon") is None


def test_slow_call_times_out(monkeypatch):
    monkeypatch.setattr(llm_mod, "TIMEOUT_S", 0.3)
    t = time.time()
    with pytest.raises(ModelUnavailable) as e:
        GroqLLM(client=FakeGroq(reply=OK, delay=5)).json("S", ["q"], VisionAssessment)
    assert time.time() - t < 2 and "exceeded" in str(e.value)


def test_transcribe_sends_named_audio_file_and_strips_text():
    fake = FakeGroq(transcript="  ಇಲ್ಲಿ ನೀರು ಸೋರುತ್ತಿದೆ \n")
    assert GroqLLM(client=fake).transcribe(b"audio-bytes", "audio/ogg") == "ಇಲ್ಲಿ ನೀರು ಸೋರುತ್ತಿದೆ"
    kw = fake.audio_calls[0]
    assert kw["file"][0].endswith(".ogg") and kw["file"][1] == b"audio-bytes" and kw["model"] == "whisper-large-v3"


def test_transcribe_language_hint(monkeypatch):
    monkeypatch.setattr(llm_mod, "STT_LANGUAGE", "kn")
    fake = FakeGroq()
    GroqLLM(client=fake).transcribe(b"x", "audio/wav")
    assert fake.audio_calls[0]["language"] == "kn" and fake.audio_calls[0]["file"][0].endswith(".wav")


def test_transcribe_failure_is_unavailable():
    with pytest.raises(ModelUnavailable):
        GroqLLM(client=FakeGroq(error=RuntimeError("boom"))).transcribe(b"x", "audio/ogg")
