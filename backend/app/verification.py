"""Verification agent: decides whether a field crew's after-photo proves the issue is fixed.

Two checks, both must pass:
  1. GPS: the crew's coordinates are within VERIFY_RADIUS_M of the case location (deterministic, no model).
  2. Vision (Groq, Llama vision): is the after-photo the same spot as the citizen's before-photos, and is the issue resolved.
If GPS fails the model is not called.
"""
import math
import os

from pydantic import BaseModel

from .llm import Fetch, GroqLLM, Image, fetch_media
from .models import Case, VerifyRequest

RADIUS_M = float(os.environ.get("VERIFY_RADIUS_M", "50"))

SYSTEM = """You verify civic repair work. A citizen reported a problem, and a field crew has submitted an AFTER photo \
claiming it is fixed. You may also get the citizen's BEFORE photos of the same problem.

Work in this order.
1. before_landmarks and after_landmarks: list the distinctive fixed features of the SURROUNDINGS you can see in each (buildings with their colours and positions, signs and poles, kerb and markings, trees, walls). Do not list the reported problem itself.
2. mismatches: list every surrounding feature that is clearly present in one set of photos but absent or different in the AFTER photo (a different building, another colour, a sign or pole in another place). Never list the reported problem or its repair: the defect being gone, litter removed, a patched or cleaned surface and repair equipment are expected changes. A change of camera angle, distance, zoom or lighting is also not a mismatch. Leave the list empty when the surroundings agree.
3. same_spot: true only if the AFTER photo shows the same place, meaning no mismatches and at least two matching surrounding features. Two different streets can look alike, so do not assume; compare the features. If no BEFORE photos are provided, set same_spot to true, leave both landmark lists empty and say so in the reason; location is then checked by GPS only.
4. resolved: is the reported problem actually fixed in the AFTER photo? False when the problem is still visible, only \
partly repaired, the photo is too blurry or dark to tell, or the photo shows something unrelated (a selfie, a different \
street, a screenshot, a close-up of paper).
reason: one or two plain sentences citing what you see, for the citizen and the dashboard."""


class VisionAssessment(BaseModel):
    before_landmarks: list[str] = []
    after_landmarks: list[str] = []
    mismatches: list[str] = []
    same_spot: bool
    resolved: bool
    reason: str


class Verdict(BaseModel):
    gps_ok: bool
    distance_m: float
    vision_same_spot: bool
    vision_resolved: bool
    reason: str

    @property
    def passed(self) -> bool:
        return self.gps_ok and self.vision_same_spot and self.vision_resolved


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class VerificationAgent:
    def __init__(self, llm: GroqLLM | None = None, radius_m: float = RADIUS_M, fetch: Fetch = fetch_media):
        self.llm = llm or GroqLLM()
        self.radius_m = radius_m
        self.fetch = fetch

    def verify(self, case: Case, req: VerifyRequest) -> Verdict:
        dist = distance_m(case.location.lat, case.location.lng, req.lat, req.lng)
        if dist > self.radius_m:
            return Verdict(
                gps_ok=False, distance_m=round(dist, 1), vision_same_spot=False, vision_resolved=False,
                reason=f"Photo was taken {dist:.0f} m from the reported location; the limit is {self.radius_m:.0f} m.",
            )
        v = self._assess(case, req)
        return Verdict(gps_ok=True, distance_m=round(dist, 1), vision_same_spot=v.same_spot,
                       vision_resolved=v.resolved, reason=v.reason)

    def _assess(self, case: Case, req: VerifyRequest) -> VisionAssessment:
        parts: list = []
        befores = [m.url for m in case.media if m.kind == "photo"][:3]
        for i, url in enumerate(befores, 1):
            data, mime = self.fetch(url)
            parts += [f"BEFORE photo {i}:", Image(data, mime)]
        data, mime = self.fetch(req.after_photo_url)
        parts += ["AFTER photo:", Image(data, mime)]
        parts.append(f"Reported problem: {case.category.value} - {case.description}\nBefore photos provided: {len(befores)}")
        v = VisionAssessment.model_validate(self.llm.json(SYSTEM, parts, VisionAssessment, temperature=0.1))
        if befores and v.mismatches:
            # The model's own observations override its verdict: any listed mismatch means a different place.
            v = v.model_copy(update={
                "same_spot": False,
                "reason": "The after photo does not appear to be the original spot: " + "; ".join(v.mismatches) + ".",
            })
        return v
