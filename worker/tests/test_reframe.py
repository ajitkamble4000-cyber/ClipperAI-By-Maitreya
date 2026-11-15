import numpy as np
from worker.clipper.reframe import smooth


def test_path_is_smooth_with_noisy_detections():
    rng = np.random.default_rng(1)
    t = np.arange(0, 20, 0.2)
    true = 0.5 + 0.25 * np.sin(2 * np.pi * t / 20)
    noisy = true + rng.normal(0, 0.03, len(t))
    samples = [(float(a), float(b)) for a, b in zip(t, noisy, strict=True)]
    samples[10] = (samples[10][0], 0.95)  # a false detection
    samples[30] = (samples[30][0], None)  # a missed frame
    path = smooth.camera_path(samples, duration=20, fps=30, crop_frac=0.316)
    w = 1920
    steps = np.abs(np.diff(path)) * w
    assert steps.max() < 10, f"max per-frame pan {steps.max():.1f}px (jitter)"
    # direction changes (jitter) should be rare: the path is a smooth wave
    signs = np.sign(np.diff(path)[np.abs(np.diff(path)) * w > 0.05])
    assert np.sum(signs[1:] != signs[:-1]) <= 4
    # follows the subject: within a third of the crop width most of the time
    ft = np.arange(len(path)) / 30
    err = np.abs(path - np.interp(ft, t, true))
    assert np.mean(err < 0.316 / 3) > 0.85


def test_no_detections_stays_centered():
    path = smooth.camera_path([(0.0, None), (1.0, None)], duration=2, fps=30)
    assert np.allclose(path, 0.5)
