import time

import pytest
from fakes import FakeLLM

from app import llm as llm_mod
from app.intake import IntakeAgent
from app.llm import Image, MediaFetchError, ModelUnavailable
from app.main import app, get_intake_agent
from app.models import CaseCreate, IntakeRequest, NeedInfo

PIN = {"lat": 13.0835, "lng": 80.272, "ward": "W-12"}
BASE = dict(category="water_leak", severity="high", description="Water leaking from a pipe on the road.",
            address_hint="near the bus stop", photo_quality="ok", missing=[], question="")


def fake_fetch(url):
    return (b"bytes:" + url.encode(), "audio/ogg" if url.endswith(".ogg") else "image/jpeg")


def agent(payload=None, **kw):
    return IntakeAgent(llm=FakeLLM({**BASE, **(payload or {})}, **kw), fetch=fake_fetch)


def req(**kw):
    return IntakeRequest(citizen_ref="cit_1", **kw)


def test_complete_report_becomes_case():
    out = agent().process(req(text="Pipe leaking near bus stop", photo_urls=["https://h/a.jpg"], location=PIN))
    assert isinstance(out, CaseCreate)
    assert out.category.value == "water_leak" and out.location.lat == 13.0835
    assert out.location.address == "near the bus stop"
    assert [m.kind for m in out.media] == ["photo"]


def test_missing_location_returns_need_info_even_if_model_forgets():
    out = agent().process(req(text="Pipe leaking"))
    assert isinstance(out, NeedInfo) and out.missing == ["location"]
    assert "location pin" in out.question


def test_vague_text_asks_for_details():
    out = agent({"missing": ["details"], "question": "What is the problem?"}).process(req(text="problem here", location=PIN))
    assert isinstance(out, NeedInfo) and out.missing == ["details"] and out.question == "What is the problem?"


def test_blurry_photo_and_no_location_asks_for_both():
    a = agent({"photo_quality": "blurry", "missing": ["photo"], "question": "Send a clearer photo."})
    out = a.process(req(photo_urls=["https://h/a.jpg"]))
    assert isinstance(out, NeedInfo) and out.missing == ["photo", "location"]
    assert out.question.startswith("Send a clearer photo.") and "location pin" in out.question


def test_empty_request_never_calls_model():
    llm = FakeLLM(BASE)
    out = IntakeAgent(llm=llm, fetch=fake_fetch).process(req())
    assert isinstance(out, NeedInfo) and out.missing == ["details"] and llm.json_calls == [] and llm.transcribe_calls == []


def test_voice_is_transcribed_then_judged():
    llm = FakeLLM(BASE, transcript="ಇಲ್ಲಿ ನೀರು ಸೋರುತ್ತಿದೆ")
    out = IntakeAgent(llm=llm, fetch=fake_fetch).process(req(voice_url="https://h/v.ogg", location=PIN))
    assert isinstance(out, CaseCreate)
    assert out.media[0].kind == "voice" and out.media[0].transcript.startswith("ಇಲ್ಲಿ")
    assert llm.transcribe_calls == [(b"bytes:https://h/v.ogg", "audio/ogg")]
    assert "ಇಲ್ಲಿ ನೀರು" in llm.json_calls[0]["parts"][-1]


def test_given_transcript_skips_whisper():
    llm = FakeLLM(BASE)
    IntakeAgent(llm=llm, fetch=fake_fetch).process(req(voice_url="https://h/v.ogg", voice_transcript="pipe leaking", location=PIN))
    assert llm.transcribe_calls == [] and "pipe leaking" in llm.json_calls[0]["parts"][-1]


def test_silent_voice_note_asks_again_without_judging():
    llm = FakeLLM(BASE, transcript="")
    out = IntakeAgent(llm=llm, fetch=fake_fetch).process(req(voice_url="https://h/v.ogg", location=PIN))
    assert isinstance(out, NeedInfo) and out.missing == ["details"] and llm.json_calls == []


def test_photos_are_sent_as_images():
    llm = FakeLLM(BASE)
    IntakeAgent(llm=llm, fetch=fake_fetch).process(req(photo_urls=["https://h/a.jpg"], location=PIN))
    parts = llm.json_calls[0]["parts"]
    assert parts[0] == Image(b"bytes:https://h/a.jpg", "image/jpeg") and isinstance(parts[-1], str)


def test_model_failure_raises_unavailable():
    with pytest.raises(ModelUnavailable):
        IntakeAgent(llm=FakeLLM(BASE, fail=True), fetch=fake_fetch).process(req(text="x", location=PIN))


def test_media_fetch_failure_raises():
    def boom(url):
        raise MediaFetchError("down")
    with pytest.raises(MediaFetchError):
        IntakeAgent(llm=FakeLLM(BASE), fetch=boom).process(req(photo_urls=["https://h/a.jpg"], location=PIN))


def test_intake_endpoint_creates_case_and_need_info(client):
    app.dependency_overrides[get_intake_agent] = lambda: agent()
    try:
        r = client.post("/intake", json={"citizen_ref": "c", "text": "Pipe leaking", "location": PIN}).json()
        assert r["result"] == "case_created" and r["case"]["status"] == "new"
        assert client.get(f"/cases/{r['case']['id']}").status_code == 200
        n = client.post("/intake", json={"citizen_ref": "c", "text": "Pipe leaking"}).json()
        assert n["result"] == "need_info" and n["need_info"]["missing"] == ["location"] and n["case"] is None
        app.dependency_overrides[get_intake_agent] = lambda: IntakeAgent(llm=FakeLLM(fail=True), fetch=fake_fetch)
        r = client.post("/intake", json={"citizen_ref": "c", "text": "x", "location": PIN})
        assert r.status_code == 200 and r.json()["need_info"]["missing"] == ["retry"]
        assert "send it again" in r.json()["need_info"]["question"]
    finally:
        app.dependency_overrides.pop(get_intake_agent, None)


def test_slow_model_endpoint_returns_retry_need_info(client, monkeypatch):
    monkeypatch.setattr(llm_mod, "TIMEOUT_S", 0.3)
    slow = FakeLLM(BASE)
    slow.json = lambda *a, **k: llm_mod._guarded(lambda: time.sleep(5))
    app.dependency_overrides[get_intake_agent] = lambda: IntakeAgent(llm=slow, fetch=fake_fetch)
    try:
        t = time.time()
        r = client.post("/intake", json={"citizen_ref": "c", "text": "Pipe leaking", "location": PIN})
        assert time.time() - t < 2 and r.json()["need_info"]["missing"] == ["retry"]
        assert client.get("/cases").json() == []  # nothing was created
    finally:
        app.dependency_overrides.pop(get_intake_agent, None)


def test_media_fetch_failure_is_502_not_retry(client):
    def boom(url):
        raise MediaFetchError("down")
    app.dependency_overrides[get_intake_agent] = lambda: IntakeAgent(llm=FakeLLM(BASE), fetch=boom)
    try:
        assert client.post("/intake", json={"citizen_ref": "c", "photo_urls": ["https://h/a.jpg"], "location": PIN}).status_code == 502
    finally:
        app.dependency_overrides.pop(get_intake_agent, None)


def test_photo_is_never_required_when_none_was_sent():
    a = agent({"missing": ["photo"], "question": "Could you share a photo of the pothole?"})
    out = a.process(req(text="Deep pothole on the main road", location=PIN))
    assert isinstance(out, CaseCreate)  # the model asked for a photo, but a photo is optional


def test_dropped_photo_request_does_not_leak_into_location_question():
    a = agent({"missing": ["photo", "location"], "question": "Please send a photo and your location."})
    out = a.process(req(text="Deep pothole on the main road"))
    assert isinstance(out, NeedInfo) and out.missing == ["location"] and "photo" not in out.question


def test_bad_photo_is_still_requested_when_one_was_sent():
    a = agent({"photo_quality": "blurry", "missing": ["photo"], "question": "Send a clearer photo."})
    out = a.process(req(text="problem", photo_urls=["https://h/a.jpg"], location=PIN))
    assert isinstance(out, NeedInfo) and out.missing == ["photo"]
