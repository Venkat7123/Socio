"""Generate the SYNTHETIC smoke test set into testset/synthetic (images + English TTS voice notes + manifest.json).

Synthetic data checks that the harness and the agents work. It is NOT evidence of real-world accuracy:
do not quote numbers from it in a pitch. Real photos and real voice notes go in testset/real (see testset/README.md).
    python scripts/build_synthetic_testset.py
"""
import json
import os
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "testset" / "synthetic"
W, H = 640, 480


def scene(loc: int, defect: str, defect_on: bool, shift=(0, 0), bright=1.0, quality=80, blur=0.0, noise_seed=0) -> Image.Image:
    """A street scene. `loc` fixes the landmarks (buildings, sign, kerb) so two photos with the same loc show the same spot."""
    r = random.Random(loc)
    im = Image.new("RGB", (W + 80, H + 80), (92, 92, 96))
    d = ImageDraw.Draw(im)
    horizon = r.randrange(110, 170)
    d.rectangle((0, 0, W + 80, horizon), fill=(r.randrange(120, 200), r.randrange(150, 210), r.randrange(180, 235)))
    for _ in range(r.randrange(3, 6)):  # buildings
        x, w, h = r.randrange(0, W), r.randrange(60, 160), r.randrange(50, horizon)
        d.rectangle((x, horizon - h, x + w, horizon + 20), fill=tuple(r.randrange(60, 220) for _ in range(3)))
        for wx in range(x + 8, x + w - 12, 22):
            d.rectangle((wx, horizon - h + 10, wx + 10, horizon - h + 22), fill=(230, 230, 160))
    d.rectangle((0, horizon + 20, W + 80, horizon + 34), fill=(190, 190, 185))  # kerb
    px = r.randrange(60, W - 60)  # signpost with a location-specific colour
    d.rectangle((px, horizon - 60, px + 6, horizon + 22), fill=(70, 70, 70))
    d.rectangle((px - 24, horizon - 90, px + 30, horizon - 58), fill=tuple(r.randrange(40, 255) for _ in range(3)))
    for x in range(r.randrange(0, 60), W + 80, 130):  # lane dashes
        d.rectangle((x, horizon + 190, x + 60, horizon + 202), fill=(228, 228, 228))
    nr = random.Random(noise_seed + loc * 7)
    for _ in range(5000):  # asphalt grain
        x, y = nr.randrange(W + 80), nr.randrange(horizon + 36, H + 80)
        c = nr.randrange(70, 125)
        d.point((x, y), (c, c, c))
    if defect_on:
        cx, cy = r.randrange(200, 440), r.randrange(horizon + 80, horizon + 160)
        if defect == "pothole":
            d.ellipse((cx - 70, cy - 30, cx + 70, cy + 34), fill=(24, 21, 19))
            d.ellipse((cx - 56, cy - 20, cx + 56, cy + 24), fill=(44, 38, 33))
        elif defect == "garbage":
            for _ in range(38):
                x, y = cx + nr.randrange(-90, 90), cy + nr.randrange(-30, 30)
                s = nr.randrange(8, 22)
                d.rectangle((x, y, x + s, y + s), fill=tuple(nr.randrange(30, 255) for _ in range(3)))
        elif defect == "water_leak":
            d.ellipse((cx - 110, cy - 28, cx + 110, cy + 36), fill=(70, 110, 160))
            d.ellipse((cx - 90, cy - 16, cx + 90, cy + 22), fill=(110, 150, 195))
            d.rectangle((cx - 8, cy - 70, cx + 8, cy - 20), fill=(60, 70, 80))
    im = im.crop((40 + shift[0], 40 + shift[1], 40 + shift[0] + W, 40 + shift[1] + H))
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    im = ImageEnhance.Brightness(im).enhance(bright)
    return im


VOICE = [  # (id, voice, rate, script, expected_result, expected_category)
    ("v01", "Microsoft David Desktop", 0, "There is a huge pothole on the main road near the market. Two bikes slipped here this morning.", "case_created", "pothole"),
    ("v02", "Microsoft Zira Desktop", 0, "The street light outside my house has not been working for three days and the lane is completely dark.", "case_created", "streetlight"),
    ("v03", "Microsoft David Desktop", 1, "Garbage has not been collected in our lane for over a week. It is piling up and smells terrible.", "case_created", "garbage"),
    ("v04", "Microsoft Zira Desktop", -1, "Water is leaking from a broken pipe near the school gate and the road is flooded.", "case_created", "water_leak"),
    ("v05", "Microsoft David Desktop", 0, "The drain near the bus stop is blocked and dirty water is overflowing onto the road.", "case_created", "drainage"),
    ("v06", "Microsoft Zira Desktop", 2, "Hello. Please send someone to fix the road in front of the temple. There is a deep hole and cars are swerving.", "case_created", "pothole"),
    ("v07", "Microsoft David Desktop", 0, "Hello, there is a problem near my house. Please come and see.", "need_info", None),
    ("v08", "Microsoft Zira Desktop", 0, "Um, it is not good here. Somebody should do something about it.", "need_info", None),
]


def tts(text: str, voice: str, rate: int, path: Path) -> None:
    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          "$s.SelectVoice($env:TTS_VOICE); $s.Rate = [int]$env:TTS_RATE; $s.SetOutputToWaveFile($env:TTS_OUT); "
          "$s.Speak($env:TTS_TEXT); $s.Dispose()")
    env = {**os.environ, "TTS_VOICE": voice, "TTS_RATE": str(rate), "TTS_OUT": str(path), "TTS_TEXT": text}
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, env=env)


def main() -> None:
    (OUT / "photos").mkdir(parents=True, exist_ok=True)
    (OUT / "voice").mkdir(parents=True, exist_ok=True)
    rng = random.Random(2026)
    defects = ["pothole", "garbage", "water_leak"]
    verify = []
    n = 0
    for label in ["good_fix", "still_broken", "wrong_place"]:
        for k in range(6):
            n += 1
            loc, other = 100 + n, 900 + n
            defect = defects[k % 3]
            pid = f"p{n:02d}"
            shift = (rng.randrange(-30, 31), rng.randrange(-25, 26))
            bright = rng.choice([0.7, 0.85, 1.0, 1.15])
            q, bl = rng.choice([60, 75, 90]), rng.choice([0, 0, 0.8])
            before = scene(loc, defect, True, quality=90)
            if label == "good_fix":
                after = scene(loc, defect, False, shift, bright, q, bl, noise_seed=5)
            elif label == "still_broken":
                after = scene(loc, defect, True, shift, bright, q, bl, noise_seed=5)
            else:  # a clean scene at a different location: looks "fixed" but is the wrong place
                after = scene(other, defect, False, shift, bright, q, bl, noise_seed=5)
            before.save(OUT / "photos" / f"{pid}_before.jpg", quality=90)
            after.save(OUT / "photos" / f"{pid}_after.jpg", quality=q)
            verify.append({"id": pid, "before": f"photos/{pid}_before.jpg", "after": f"photos/{pid}_after.jpg",
                           "label": label, "category": defect, "description": f"{defect.replace('_', ' ')} reported on the road"})
    voice = []
    for vid, name, rate, script, expected, cat in VOICE:
        path = OUT / "voice" / f"{vid}.wav"
        tts(script, name, rate, path)
        voice.append({"id": vid, "audio": f"voice/{vid}.wav", "script": script, "expected_result": expected,
                      "expected_category": cat, "voice": name, "language": "en"})
    manifest = {"set": "synthetic", "note": "Synthetic images and English text-to-speech. Smoke test only; not evidence of real-world accuracy.",
                "verify": verify, "voice": voice}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(verify)} photo pairs and {len(voice)} voice notes to {OUT}")


if __name__ == "__main__":
    main()
