# Test sets for the accuracy number

| Folder | What it is | Use |
|---|---|---|
| `synthetic/` | Generated street scenes and English text-to-speech voice notes (`python scripts/build_synthetic_testset.py`) | Checks the harness and agents work. **Never quote its numbers in the pitch.** |
| `real/` | Photos and voice notes your team captures | The set the pitch number comes from |

Run: `python scripts/evaluate.py real` (needs `GROQ_API_KEY`). It writes `results.jsonl` (resumable) and `report.md`.

## Why the numbers need care

- With 18 photo pairs, 12 of them bad fixes, "0 false passes" only means the true false-pass rate is probably under about 24%
  (95% interval). The report prints this interval next to every figure; quote the interval, not just the point.
- A full run makes about 26 model calls (18 pairs + 8 voice notes, each voice note being a Whisper call plus a judgement call).
  If a rate limit or quota stops the run, rerun later: finished items are cached. Items that fail are never counted as wrong;
  they are listed as not evaluated and retried on the next run. Check your Groq plan's daily limits for the vision and Whisper models.

## Capturing the real set (about an hour with 3 phones)

Photo pairs, with GPS irrelevant (the harness scores the vision check; GPS is tested separately):

1. **good_fix (6+):** photograph a real defect (litter pile, damaged kerb, puddle, broken tile, graffiti, a pothole if you can
   find one). Fix or clean it, or stage the cleanup, then photograph the same spot again from a slightly different position.
2. **still_broken (6+):** photograph the defect, walk away, come back and photograph the same defect again from a different
   distance or angle. Include partial fixes (half the litter picked up).
3. **wrong_place (6+):** after-photo of a *clean* spot somewhere else, ideally a similar-looking street, kerb or wall.
4. Vary lighting, distance and phone. Include a few hard ones: shadows, wet ground, a photo taken from further away.

Voice notes (5 to 10): record people speaking the way citizens would, in the language you will demo, with background noise.
Include 2 vague ones ("there is a problem near my house") that should produce a follow-up question, not a case.

Name files like `p01_before.jpg`, `p01_after.jpg`, `v01.ogg` (WhatsApp OGG, WAV, MP3 and M4A all work) and add them to
`real/manifest.json`, using `synthetic/manifest.json` as the template:

```json
{"set": "real", "verify": [{"id": "p01", "before": "photos/p01_before.jpg", "after": "photos/p01_after.jpg",
   "label": "good_fix | still_broken | wrong_place", "category": "pothole | garbage | water_leak | ...", "description": "what the citizen reported"}],
 "voice": [{"id": "v01", "audio": "voice/v01.ogg", "script": "exact words spoken", "expected_result": "case_created | need_info",
   "expected_category": "pothole or null", "language": "kn"}]}
```

Label honestly. Do not drop photos the model gets wrong, and do not tune prompts on the same set you report: keep a few
pairs aside as a final check.

## What is scored

- **Verification:** pass or fail against the label (only `good_fix` should pass), plus false pass (the dangerous error: a bad fix
  accepted), false reject, and whether blocked cases were blocked for the right reason.
- **Voice:** right outcome (case vs follow-up question), category on clear notes, and transcript word error rate against `script`.
- **Latency:** p50 and p95 of successful model calls, and how many calls failed or timed out.
