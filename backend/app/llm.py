"""Groq client wrapper shared by the intake and verification agents.

Two operations: `json()` (a vision-capable chat model that returns JSON matching a Pydantic schema) and `transcribe()`
(Whisper speech to text). Every failure (timeout, rate limit, API error, unparseable output) becomes ModelUnavailable
so callers can fall back instead of hanging; no call blocks longer than TIMEOUT_S.
"""
import base64
import io
import json
import mimetypes
import os
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Callable, NamedTuple, Protocol

import groq
import httpx
from PIL import Image as PILImage
from pydantic import BaseModel

VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
STT_MODEL = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3")
STT_LANGUAGE = os.environ.get("WHISPER_LANGUAGE") or None  # ISO code such as "kn" or "hi"; unset = auto-detect
TIMEOUT_S = float(os.environ.get("MODEL_TIMEOUT_S", "15"))  # per model call; a slower call is abandoned
JSON_MODE = os.environ.get("GROQ_JSON_MODE", "json_schema")  # or "json_object" for models without schema support
MAX_MEDIA_BYTES = 15 * 1024 * 1024
# Image tokens count against Groq's tokens-per-minute limit (8000 on the free Qwen tier), so photos are kept small.
MAX_IMAGE_SIDE = int(os.environ.get("IMAGE_MAX_SIDE", "768"))
RETRY_MESSAGE = "Sorry, I could not process that just now. Please send it again in a minute."


class IntakeUnavailable(Exception):
    """The request could not be completed (see the two subclasses)."""


class MediaFetchError(IntakeUnavailable):
    """A photo or voice URL could not be fetched or is not a valid image. The caller's problem, not the model's."""


class ModelUnavailable(IntakeUnavailable):
    """The model timed out, errored, was rate limited, or returned nothing usable. Safe to retry later.
    `retry_after` is the number of seconds Groq asked us to wait, when it rate limited the call."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def _seconds(text: str) -> float | None:
    """Parse '44.977s', '1m2.5s' or '2' into seconds."""
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)(?:s|ms)?)?", text.strip())
    if not m or not any(m.groups()):
        return None
    h, mi, s = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)


def _retry_after(e: "groq.APIStatusError") -> float | None:
    if e.status_code != 429:
        return None
    headers = e.response.headers
    return _seconds(headers.get("retry-after") or headers.get("x-ratelimit-reset-tokens") or "")


class Image(NamedTuple):
    data: bytes
    mime: str


class JSONResult(NamedTuple):
    data: dict  # validated against the requested schema
    backend: str  # what produced it, e.g. "groq:qwen/qwen3.8-27b"; copied onto every agent message as model_backend


class LLMProvider(Protocol):
    """What the agents depend on. Groq is the only implementation; another provider needs only these two methods.
    complete_json must return data valid for `schema`, or raise ModelUnavailable (timeout over TIMEOUT_S, rate limit,
    API error, unparseable output). It never returns a guess."""

    def complete_json(self, system: str, parts: "list[Part]", schema: type[BaseModel], temperature: float = 0.1) -> JSONResult: ...

    def transcribe(self, data: bytes, mime: str) -> str: ...


Part = str | Image
Fetch = Callable[[str], tuple[bytes, str]]

_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="model")


def fetch_media(url: str) -> tuple[bytes, str]:
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True, headers={"User-Agent": "civic-intake/0.1"})
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise MediaFetchError(f"could not fetch media {url}: {e}") from e
    if len(r.content) > MAX_MEDIA_BYTES:
        raise MediaFetchError(f"media too large: {url}")
    mime = r.headers.get("content-type", "").split(";")[0].strip()
    if not mime or mime == "application/octet-stream":
        mime = mimetypes.guess_type(url.split("?")[0])[0] or "application/octet-stream"
    return r.content, mime


def _data_uri(img: Image) -> str:
    """Downscale and re-encode as JPEG so the request stays well under Groq's 4 MB base64 image limit."""
    try:
        im = PILImage.open(io.BytesIO(img.data))
        im.load()
    except Exception as e:
        raise MediaFetchError(f"not a valid image ({img.mime})") from e
    im = im.convert("RGB")
    im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _guarded(fn, **kwargs):
    """Run a model call under a wall-clock limit, mapping every failure to ModelUnavailable."""
    future = _pool.submit(fn, **kwargs)
    try:
        return future.result(timeout=TIMEOUT_S + 1)
    except FutureTimeout as e:
        future.cancel()
        raise ModelUnavailable(f"model call exceeded {TIMEOUT_S:.0f} s") from e
    except groq.APIStatusError as e:
        raise ModelUnavailable(f"Groq API error {e.status_code}: {str(e.message)[:160]}", _retry_after(e)) from e
    except Exception as e:  # transport errors: timeouts, connection resets
        raise ModelUnavailable(f"model call failed: {type(e).__name__}") from e


def _strict_schema(model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    schema["additionalProperties"] = False
    schema["required"] = list(schema.get("properties", {}))  # fields with defaults are still demanded from the model
    return schema


class GroqLLM:
    def __init__(self, client: groq.Groq | None = None, model: str = VISION_MODEL, stt_model: str = STT_MODEL):
        # max_retries=0: the SDK's own retries multiply the wait; we fail fast and let the caller fall back.
        self.client = client or groq.Groq(timeout=TIMEOUT_S, max_retries=0)
        self.model = model
        self.stt_model = stt_model

    def complete_json(self, system: str, parts: list[Part], schema: type[BaseModel], temperature: float = 0.1) -> JSONResult:
        content: list[dict] = []
        for p in parts:
            if isinstance(p, Image):
                content.append({"type": "image_url", "image_url": {"url": _data_uri(p)}})
            else:
                content.append({"type": "text", "text": p})
        if JSON_MODE == "json_object":
            system += "\n\nReply with a single JSON object matching this JSON schema:\n" + json.dumps(schema.model_json_schema())
            response_format = {"type": "json_object"}
        else:
            response_format = {"type": "json_schema", "json_schema": {"name": schema.__name__, "schema": _strict_schema(schema)}}
        resp = _guarded(
            self.client.chat.completions.create,
            model=self.model, temperature=temperature, max_completion_tokens=700, response_format=response_format,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
        )
        text = resp.choices[0].message.content if resp.choices else None
        if not text:
            raise ModelUnavailable("empty model response")
        try:
            return JSONResult(schema.model_validate(json.loads(text)).model_dump(), f"groq:{self.model}")
        except ValueError as e:
            raise ModelUnavailable(f"unparseable model response: {e}") from e

    def transcribe(self, data: bytes, mime: str) -> str:
        ext = (mimetypes.guess_extension(mime) or ".ogg").replace(".oga", ".ogg")
        kwargs = dict(model=self.stt_model, file=(f"voice{ext}", data), temperature=0.0)
        if STT_LANGUAGE:
            kwargs["language"] = STT_LANGUAGE
        resp = _guarded(self.client.audio.transcriptions.create, **kwargs)
        return (getattr(resp, "text", "") or "").strip()
