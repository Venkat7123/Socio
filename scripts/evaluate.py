"""Measure verification and voice-intake accuracy on a labeled test set, using the real agents and real Groq calls.

    python scripts/evaluate.py synthetic            # smoke set (NOT evidence of real-world accuracy)
    python scripts/evaluate.py real                 # the set that goes in the pitch
    python scripts/evaluate.py real --sleep 8 --limit 10

Results are cached in testset/<set>/results.jsonl so a run can resume after a rate limit or quota stop; items whose
model call failed are reported as unavailable (never as wrong) and retried on the next run. Needs GROQ_API_KEY.
"""
import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.intake import IntakeAgent, ModelUnavailable  # noqa: E402
from app.models import Case, CaseCreate, IntakeRequest, NeedInfo, VerifyRequest  # noqa: E402
from app.verification import VerificationAgent  # noqa: E402

LAT, LNG = 13.0835, 80.2720  # Track C ward W-12 scenario point P2 (Chennai)
MIMES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
         ".wav": "audio/wav", ".ogg": "audio/ogg", ".mp3": "audio/mp3", ".m4a": "audio/mp4"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for k successes out of n."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - m) / d), min(1.0, (c + m) / d))


def pct(k: int, n: int) -> str:
    if n == 0:
        return "n/a (0 evaluated)"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.0f}%  (95% CI {100 * lo:.0f}-{100 * hi:.0f}%)"


def words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", s.lower())


def wer(ref: str, hyp: str) -> float:
    r, h = words(ref), words(hyp)
    d = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        prev, d[0] = d[0], i
        for j, hw in enumerate(h, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (rw != hw))
    return d[len(h)] / max(len(r), 1)


def percentile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("set", help="folder under testset/ (synthetic or real)")
    ap.add_argument("--sleep", type=float, default=2, help="seconds between model calls (rate limits)")
    ap.add_argument("--limit", type=int, default=0, help="max new model calls this run (0 = no limit)")
    ap.add_argument("--redo", action="store_true", help="ignore cached results")
    ap.add_argument("--stop-after", type=int, default=3, help="stop after this many consecutive unavailable calls")
    args = ap.parse_args()

    base = ROOT / "testset" / args.set
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    cache_path = base / "results.jsonl"
    cache: dict[str, dict] = {}
    if cache_path.exists() and not args.redo:
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            cache[f"{r['kind']}:{r['id']}"] = r

    def fetch(rel: str):
        p = base / rel
        return p.read_bytes(), MIMES.get(p.suffix.lower(), "application/octet-stream")

    verifier, intake = VerificationAgent(fetch=fetch), IntakeAgent(fetch=fetch)
    heard = {"text": ""}  # last Whisper transcript, kept so word error rate also covers notes that ended in need_info
    _transcribe = intake.llm.transcribe

    def capture(data, mime):
        heard["text"] = _transcribe(data, mime)
        return heard["text"]

    intake.llm.transcribe = capture
    items = [("verify", v) for v in manifest.get("verify", [])] + [("voice", v) for v in manifest.get("voice", [])]
    calls = fails = 0
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    out = open(cache_path, "a", encoding="utf-8")

    for kind, it in items:
        key = f"{kind}:{it['id']}"
        if cache.get(key, {}).get("status") == "ok":
            continue
        if args.limit and calls >= args.limit:
            break
        if fails >= args.stop_after:
            print(f"\nStopping: {fails} consecutive model failures (quota or rate limit?). Rerun later to resume.")
            break
        rec = {"kind": kind, "id": it["id"]}
        for attempt in range(6):
            t0 = time.time()
            try:
                if kind == "verify":
                    case = Case.model_validate({
                        "id": it["id"], "status": "in_progress", "category": it["category"], "severity": "medium",
                        "description": it["description"], "location": {"lat": LAT, "lng": LNG},
                        "media": [{"kind": "photo", "url": it["before"]}], "citizen_ref": "eval", "hop_count": 0,
                        "rejected_by": [], "sla": {"due_at": "2030-01-01T00:00:00+00:00"},
                        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"})
                    v = verifier.verify(case, VerifyRequest(after_photo_url=it["after"], lat=LAT + 0.0002, lng=LNG))
                    rec.update(status="ok", label=it["label"], passed=v.passed, same_spot=v.vision_same_spot,
                               resolved=v.vision_resolved, reason=v.reason)
                else:
                    heard["text"] = ""
                    res = intake.process(IntakeRequest(citizen_ref="eval", voice_url=it["audio"], location={"lat": LAT, "lng": LNG}))
                    if isinstance(res, CaseCreate):
                        tr = next((m.transcript for m in res.media if m.kind == "voice"), "") or ""
                        rec.update(status="ok", result="case_created", category=res.category.value, severity=res.severity.value, transcript=tr)
                    else:
                        rec.update(status="ok", result="need_info", missing=res.missing, question=res.question, transcript=heard["text"])
                fails = 0
                break
            except ModelUnavailable as e:
                if e.retry_after and attempt < 5 and e.retry_after <= 120:
                    print(f"  {key}: rate limited, waiting {e.retry_after + 1:.0f}s then retrying")
                    time.sleep(e.retry_after + 3)
                    continue
                rec.update(status="unavailable", error=str(e)[:300])
                fails += 1
                break
        rec["seconds"] = round(time.time() - t0, 1)
        calls += 1
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out.flush()
        cache[key] = rec
        tag = rec["status"] if rec["status"] != "ok" else ("pass" if rec.get("passed") else rec.get("result", "fail"))
        print(f"  {key:12s} {tag:12s} {rec['seconds']:>5}s")
        time.sleep(args.sleep)
    out.close()

    # ------------------------------------------------------------------ report
    lines = []
    emit = lambda s="": (lines.append(s), print(s))
    emit(f"\n# Accuracy report: {args.set}")
    if manifest.get("note"):
        emit(f"> {manifest['note']}")
    vr = [cache.get(f"verify:{v['id']}") for v in manifest.get("verify", [])]
    ok = [r for r in vr if r and r["status"] == "ok"]
    emit(f"\n## Verification (after-photo)   evaluated {len(ok)} of {len(vr)} pairs")
    if ok:
        pos = [r for r in ok if r["label"] == "good_fix"]
        neg = [r for r in ok if r["label"] != "good_fix"]
        correct = sum(r["passed"] == (r["label"] == "good_fix") for r in ok)
        emit(f"- Overall accuracy (pass only good fixes): {pct(correct, len(ok))}")
        emit(f"- False pass (bad fix accepted, the dangerous error): {pct(sum(r['passed'] for r in neg), len(neg))}")
        emit(f"- False reject (good fix blocked): {pct(sum(not r['passed'] for r in pos), len(pos))}")
        for label in ["good_fix", "still_broken", "wrong_place"]:
            rs = [r for r in ok if r["label"] == label]
            if rs:
                emit(f"- {label:13s} handled correctly: {pct(sum(r['passed'] == (label == 'good_fix') for r in rs), len(rs))}")
        sb = [r for r in ok if r["label"] == "still_broken"]
        wp = [r for r in ok if r["label"] == "wrong_place"]
        if sb:
            emit(f"- still_broken blocked for the right reason (resolved=false): {pct(sum(not r['resolved'] for r in sb), len(sb))}")
        if wp:
            emit(f"- wrong_place blocked for the right reason (same_spot=false): {pct(sum(not r['same_spot'] for r in wp), len(wp))}")
        wrong = [r for r in ok if r["passed"] != (r["label"] == "good_fix")]
        for r in wrong:
            emit(f"  - MISS {r['id']} ({r['label']}): {r['reason']}")
    vo = [cache.get(f"voice:{v['id']}") for v in manifest.get("voice", [])]
    vok = [(v, cache[f"voice:{v['id']}"]) for v in manifest.get("voice", []) if cache.get(f"voice:{v['id']}", {}).get("status") == "ok"]
    emit(f"\n## Voice notes   evaluated {len(vok)} of {len(vo)} notes")
    if vok:
        emit(f"- Right outcome (case vs follow-up question): {pct(sum(r['result'] == v['expected_result'] for v, r in vok), len(vok))}")
        cat = [(v, r) for v, r in vok if v["expected_category"]]
        emit(f"- Category correct on clear notes: {pct(sum(r.get('category') == v['expected_category'] for v, r in cat), len(cat))}")
        wers = [wer(v["script"], r["transcript"]) for v, r in vok if r.get("transcript")]
        if wers:
            emit(f"- Transcript word error rate: mean {100 * sum(wers) / len(wers):.0f}% over {len(wers)} transcribed notes")
        for v, r in vok:
            if r["result"] != v["expected_result"] or (v["expected_category"] and r.get("category") != v["expected_category"]):
                emit(f"  - MISS {v['id']}: expected {v['expected_result']}/{v['expected_category']}, got {r['result']}/{r.get('category')}")
    secs = [r["seconds"] for r in cache.values() if r["status"] == "ok"]
    unavailable = sum(1 for r in cache.values() if r["status"] == "unavailable")
    emit(f"\n## Latency and availability")
    emit(f"- Model call latency: p50 {percentile(secs, .5):.1f}s, p95 {percentile(secs, .95):.1f}s over {len(secs)} successful calls")
    emit(f"- Calls that failed or timed out (excluded from accuracy): {unavailable}")
    (base / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    pending = len(items) - sum(1 for k, i in items if cache.get(f"{k}:{i['id']}", {}).get("status") == "ok")
    return 0 if pending == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
