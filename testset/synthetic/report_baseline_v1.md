
# Accuracy report: synthetic
> Synthetic images and English text-to-speech. Smoke test only; not evidence of real-world accuracy.

## Verification (after-photo)   evaluated 18 of 18 pairs
- Overall accuracy (pass only good fixes): 15/18 = 83%  (95% CI 61-94%)
- False pass (bad fix accepted, the dangerous error): 3/12 = 25%  (95% CI 9-53%)
- False reject (good fix blocked): 0/6 = 0%  (95% CI 0-39%)
- good_fix      handled correctly: 6/6 = 100%  (95% CI 61-100%)
- still_broken  handled correctly: 6/6 = 100%  (95% CI 61-100%)
- wrong_place   handled correctly: 3/6 = 50%  (95% CI 19-81%)
- still_broken blocked for the right reason (resolved=false): 6/6 = 100%  (95% CI 61-100%)
- wrong_place blocked for the right reason (same_spot=false): 3/6 = 50%  (95% CI 19-81%)
  - MISS p14 (wrong_place): The BEFORE photo shows a pile of garbage on the road, while the AFTER photo shows the same road area is clear of any debris. The background buildings and road markings are consistent, confirming the location.
  - MISS p17 (wrong_place): The BEFORE photo shows a pile of garbage in the middle of the road, while the AFTER photo shows the same road section (indicated by the dashed lines and background buildings) is now clear of any debris.
  - MISS p18 (wrong_place): The BEFORE photos show a large blue puddle on the road, indicating a water leak. The AFTER photo shows the same road area, but the puddle is gone and the road surface is dry. The buildings and landmarks in the background are consistent, confirming it is the same spot.

## Voice notes   evaluated 8 of 8 notes
- Right outcome (case vs follow-up question): 7/8 = 88%  (95% CI 53-98%)
- Category correct on clear notes: 5/6 = 83%  (95% CI 44-97%)
- Transcript word error rate: mean 0% over 5 transcribed notes
  - MISS v01: expected case_created/pothole, got need_info/None

## Latency and availability
- Model call latency: p50 0.9s, p95 1.1s over 26 successful calls
- Calls that failed or timed out (excluded from accuracy): 0
