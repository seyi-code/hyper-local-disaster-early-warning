"""Basic unit test for CUSUM detector."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detectors.cusum import CusumDetector, CusumConfig

def test_detects_upward_shift():
    cfg = CusumConfig(k=0.5, h=4.0, baseline_window=20, min_samples=10, cooldown_seconds=0)
    det = CusumDetector(cfg)

    for _ in range(25):
        triggered, direction, _ = det.update(40.0)
        assert not triggered

    triggered = False
    for i in range(15):
        t, d, score = det.update(55.0 + i * 0.5)
        if t:
            triggered = True
            assert d == "up"
            break
    assert triggered, "CUSUM should have detected the upward shift"

if __name__ == "__main__":
    test_detects_upward_shift()
    print("CUSUM test passed")
