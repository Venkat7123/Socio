import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from evaluate import percentile, wer, wilson  # noqa: E402


def test_wilson_interval_is_wide_for_small_samples():
    lo, hi = wilson(0, 12)  # 0 false passes out of 12 bad fixes is NOT "0% error" with certainty
    assert lo == 0 and 0.2 < hi < 0.3
    lo, hi = wilson(18, 18)
    assert 0.8 < lo < 0.85 and hi == 1.0
    lo, hi = wilson(9, 18)
    assert 0.28 < lo < 0.30 and 0.70 < hi < 0.72
    assert wilson(0, 0) == (0.0, 0.0)


def test_word_error_rate():
    assert wer("the pipe is leaking", "The pipe is leaking!") == 0
    assert wer("the pipe is leaking", "the pipe leaking") == 0.25  # one deletion in four words
    assert wer("a b c d", "a x c d") == 0.25  # one substitution
    assert wer("a b", "") == 1.0


def test_percentile():
    assert percentile([1, 2, 3, 4, 5], 0.5) == 3 and percentile([], 0.5) == 0.0
